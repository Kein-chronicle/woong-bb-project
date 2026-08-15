#!/usr/bin/env python3
"""image_prompt_planner.py
이미지 프롬프트 생성 클러스터 — automation_worker.py 모놀리스에서 분리(리팩토링).
build_image_prompt_plan 및 헬퍼. 공유 헬퍼(summarize_current_scene/rotate_pick_recent)는
호출 시점 lazy import로 순환 방지. 동작 불변(golden master로 검증).
"""
import random
from typing import Optional
from datetime import datetime, timedelta

from automation.io import load_json, save_json, now_iso, now_local
from automation.paths import *  # noqa: F401,F403
from project_paths import ROOT, STATE

def load_recent_image_plans(limit: int = 4) -> list:
    history = load_json(IMAGE_SHOT_HISTORY_PATH, {})
    plans = history.get("recent_plans", [])
    if not isinstance(plans, list):
        return []
    return plans[:limit]


def save_recent_image_plan(plan: dict) -> None:
    history = load_json(IMAGE_SHOT_HISTORY_PATH, {})
    recent = history.get("recent_plans", [])
    if not isinstance(recent, list):
        recent = []
    compact = {
        "generated_at": plan.get("generated_at"),
        "image_type": plan.get("image_type"),
        "shot_type": plan.get("shot_type"),
        "camera_angle": plan.get("camera_angle"),
        "framing": plan.get("framing"),
        "pose": plan.get("pose"),
        "expression": plan.get("expression"),
        "selfie_capture_method": plan.get("selfie_capture_method"),
        "camera_visibility": plan.get("camera_visibility"),
        "space_anchor": plan.get("space_anchor"),
        "face_angle": plan.get("face_angle"),
        "gaze_direction": plan.get("gaze_direction"),
        "camera_height": plan.get("camera_height"),
        "lens_distance": plan.get("lens_distance"),
        "body_orientation": plan.get("body_orientation"),
        "expression_intensity": plan.get("expression_intensity"),
        "spontaneity": plan.get("spontaneity"),
        "activity": plan.get("activity"),
        "time_block": plan.get("time_block"),
    }
    deduped = [item for item in recent if item.get("generated_at") != compact.get("generated_at")]
    history.update(
        {
            "schema_version": 1,
            "managed_by": "share_priority_engine",
            "updated_at": now_iso(),
            "recent_plans": [compact] + deduped[:5],
            "notes": "최근 이미지 샷 메타데이터를 기록해 반복 구도를 피한다",
        }
    )
    save_json(IMAGE_SHOT_HISTORY_PATH, history)


def _build_text_prompt(plan: dict) -> str:
    base = "young Korean woman, long straight black hair, soft facial features, natural complexion, slim silhouette"

    shot_map = {
        "face_closeup": "extreme close-up face",
        "chest_up": "chest-up portrait",
        "half_body": "half-body shot",
        "waist_up": "waist-up framing",
        "mirror_half_body": "half-body mirror selfie",
        "table_portrait": "seated portrait at table",
        "full_body_candid": "full body candid",
        "window_side_portrait": "side portrait by window",
        "half_body_seated": "seated half-body",
    }
    angle_map = {
        "front_phone_selfie": "straight-on front camera selfie",
        "three_quarter_arm_length": "three-quarter angle arm-length selfie",
        "slight_high_angle": "slightly elevated angle",
        "top_down_phone_selfie": "top-down phone selfie",
        "pillow_level_three_quarter": "pillow-level three-quarter angle",
        "seated_three_quarter": "seated three-quarter angle",
        "low_table_angle": "low table angle",
    }
    method_map = {
        "front_camera_handheld": "handheld front camera",
        "mirror_selfie": "mirror selfie phone visible",
        "propped_phone_timer": "timer selfie phone propped",
    }
    expr_map = {
        "soft_smile": "soft gentle smile",
        "warm_smile": "warm natural smile",
        "bright_smile": "bright cheerful smile",
        "quiet_eye_contact": "calm direct eye contact",
        "mellow_relaxed": "mellow relaxed expression",
        "sleepy_soft_smile": "sleepy soft smile",
        "playful_grin": "playful grin",
        "content_relaxed": "content relaxed face",
        "tired_but_cute": "tired but cute expression",
        "small_pout": "slight pout",
        "closed_lip_smile": "closed-lip smile",
        "fond_look": "fond warm look",
        "reflective_gaze": "reflective thoughtful gaze",
    }
    face_map = {
        "front_facing": "facing directly at camera",
        "three_quarter_turn": "three-quarter face turn",
        "slight_profile": "slight profile view",
        "chin_tucked_down": "chin slightly lowered",
        "walking_turn_back": "turning back glance",
    }
    gaze_map = {
        "lens_eye_contact": "direct lens eye contact",
        "screen_preview_glance": "glancing at phone screen",
        "downward_relaxed": "gaze downward relaxed",
        "off_to_side_focus": "gaze off to the side",
        "laughing_away": "laughing gaze away",
    }
    space_map = {
        "bedside": "beside bed",
        "bedroom_mirror": "bedroom mirror",
        "desk_area": "computer desk, cool monitor glow",
        "kitchen_area": "home kitchen",
        "neutral_personal_space": "cozy home interior",
        "quiet_hallway": "home hallway",
        "room_walk": "home room interior",
        "vanity_corner": "vanity corner",
        "cafe_table": "home interior table",
        "cafe_counter": "home kitchen counter",
    }
    outfit_map = {
        "home_casual_work": "oversized white t-shirt or hoodie",
        "pajamas": "cozy pajamas or sleepwear",
        "post_shower": "white bathrobe or towel wrap",
        "home_relaxed": "comfortable home clothing",
        "night_home_casual": "comfortable home nightwear",
        "home_work": "casual home work outfit",
    }

    block = plan.get("time_block", "")
    if "night" in block or "sleep" in block:
        lighting = "warm amber mood lighting"
    elif "morning" in block:
        lighting = "soft morning indoor light"
    elif "lunch" in block:
        lighting = "natural indoor midday light"
    else:
        lighting = "natural indoor lighting"

    shot = shot_map.get(plan.get("shot_type", ""), "")
    angle = angle_map.get(plan.get("camera_angle", ""), "")
    method = method_map.get(plan.get("selfie_capture_method", ""), "")
    intensity = plan.get("expression_intensity", "").replace("_", " ")
    expr = expr_map.get(plan.get("expression", ""), plan.get("expression", "").replace("_", " "))
    expr_full = ("%s %s" % (intensity, expr)).strip() if intensity else expr
    face = face_map.get(plan.get("face_angle", ""), "")
    gaze = gaze_map.get(plan.get("gaze_direction", ""), "")
    outfit_ctx = plan.get("outfit_context", "") or plan.get("appearance_branch", "")
    outfit = outfit_map.get(outfit_ctx, "casual home clothing")
    space = space_map.get(plan.get("space_anchor", ""), "cozy home interior")

    components = [base, shot, angle, method, expr_full, face, gaze, outfit, space, lighting,
                  "photorealistic, indoor home setting, natural skin texture, candid selfie"]
    return ", ".join(c for c in components if c)


def _pick_reference_images(face_angle: str, shot_type: str, pose: str) -> dict:
    curated = ROOT / "characters" / "woongbbi" / "eunbi" / "references" / "curated"
    v2_outfits = ROOT / "working" / "eunbi" / "meta_references" / "generated" / "v2" / "outfits"
    v2_spaces = ROOT / "working" / "eunbi" / "meta_references" / "generated" / "v2" / "spaces"
    v2_faces = ROOT / "working" / "eunbi" / "meta_references" / "generated" / "v2" / "faces"
    result = {}

    now_h = now_local().hour

    # 얼굴: v2 생성 이미지 우선, 없으면 v1 curated fallback
    # 안경 낀 컷, 과한 미소 컷 제외. 핵심 2장만 사용.
    _face_exclude_keywords = {"glasses", "smile_glasses"}
    if v2_faces.exists():
        face_imgs = [
            f for f in v2_faces.iterdir()
            if f.suffix in {".png", ".jpg"} and not any(kw in f.name for kw in _face_exclude_keywords)
        ]
        face_imgs.sort(key=lambda f: f.name)
        result["face_front"] = [str(f) for f in face_imgs[:2]]
    else:
        face_dir = curated / "face_front_best"
        if face_dir.exists():
            img_exts = {".jpg", ".jpeg", ".png"}
            preferred = [f for f in face_dir.iterdir() if "__preferred_face" in f.name and f.suffix in img_exts]
            preferred.sort(key=lambda f: f.name)
            result["face_front"] = [str(f) for f in preferred[:2]]

    # 옆 각도 얼굴: v1 side profile — 핵심 1장만
    if face_angle in {"three_quarter_turn", "slight_profile", "chin_tucked_down", "walking_turn_back"}:
        side_dir = curated / "face_side_profile"
        if side_dir.exists():
            side_imgs = sorted(
                [f for f in side_dir.iterdir() if f.suffix in {".jpg", ".jpeg", ".png"}],
                key=lambda f: f.name,
            )
            result["face_side"] = [str(f) for f in side_imgs[:1]]

    # 착장: 시간대 기반 OC 필터링 (전신샷 + 셀피 모두 포함)
    if v2_outfits.exists() and shot_type not in {"hand_close_up", "face_only_extreme_close"}:
        all_oc = [f for f in v2_outfits.iterdir() if f.suffix == ".png"]
        # 시간대별 착장 우선순위
        if 5 <= now_h < 9:  # 이른 아침 — 잠옷/루즈핏
            preferred_prefixes = ("OC-06", "OC-07", "OC-08", "OC-09")
        elif 9 <= now_h < 18:  # 낮 — 기본 작업복
            preferred_prefixes = ("OC-01", "OC-02", "OC-03", "OC-06")
        elif 18 <= now_h < 22:  # 저녁 — 편한 홈웨어
            preferred_prefixes = ("OC-05", "OC-06", "OC-11", "OC-07")
        else:  # 심야 — 잠옷
            preferred_prefixes = ("OC-07", "OC-08", "OC-09")
        preferred = [f for f in all_oc if any(f.name.startswith(p) for p in preferred_prefixes)]
        others = [f for f in all_oc if f not in preferred]
        random.shuffle(preferred); random.shuffle(others)
        result["outfit"] = [str(f) for f in (preferred + others)[:2]]

    # 공간: 시간대/활동 기반 SP 필터링
    if v2_spaces.exists():
        all_sp = [f for f in v2_spaces.iterdir() if f.suffix == ".png"]
        # 시간대별 공간 우선순위
        if 5 <= now_h < 10:  # 아침 — 침대/기상
            preferred_sp = [f for f in all_sp if "bed" in f.name or "02" in f.name]
        elif 10 <= now_h < 13:  # 오전 작업
            preferred_sp = [f for f in all_sp if "desk" in f.name or "01" in f.name]
        elif 13 <= now_h < 19:  # 오후 — 책상/다이닝
            preferred_sp = [f for f in all_sp if "desk" in f.name or "dining" in f.name or "01" in f.name or "03" in f.name]
        else:  # 저녁/밤 — 침대/거실
            preferred_sp = [f for f in all_sp if "bed" in f.name or "02" in f.name or "04" in f.name]
        others_sp = [f for f in all_sp if f not in preferred_sp]
        random.shuffle(preferred_sp); random.shuffle(others_sp)
        result["space"] = [str(f) for f in (preferred_sp + others_sp)[:2]]

    # 손/소품: v1 curated
    if any(kw in pose for kw in ("cup", "phone", "hold", "prop", "spoon", "chopstick", "hair")):
        hands_dir = curated / "hands_props_gestures"
        if hands_dir.exists():
            hands_imgs = [f for f in hands_dir.iterdir() if f.suffix in {".jpg", ".jpeg", ".png"}]
            random.shuffle(hands_imgs)
            result["hands"] = [str(f) for f in hands_imgs[:2]]

    # 헤어: v1 curated
    if face_angle in {"three_quarter_turn", "slight_profile", "walking_turn_back"} or shot_type in {"mirror_half_body", "full_body_candid"}:
        hair_dir = curated / "hair_reference"
        if hair_dir.exists():
            hair_imgs = [f for f in hair_dir.iterdir() if f.suffix in {".jpg", ".jpeg", ".png"}]
            random.shuffle(hair_imgs)
            result["hair"] = [str(f) for f in hair_imgs[:2]]

    return result


def resolve_content_level(activity: str, image_settings: dict) -> int:
    override = image_settings.get("content_level_override")
    if isinstance(override, int):
        return override
    rules = image_settings.get("auto_level_rules", {})
    if activity in {"morning_prep", "evening_free"}:
        return int(rules.get("at_home_work", 2))
    # v2: all home activities → level 2 fixed
    return 2


def build_image_prompt_plan(reason: str) -> dict:
    # 공유 헬퍼는 순환 import 방지 위해 호출 시점에 lazy import
    from automation_worker import summarize_current_scene, rotate_pick_recent
    presence = load_json(PRESENCE_PATH, {})
    appearance = load_json(APPEARANCE_PATH, {})
    weather = load_json(WEATHER_PATH, {})
    continuity = load_json(STATE / "image_continuity_state.json", {})
    recent_plans = load_recent_image_plans()
    image_settings = load_json(IMAGE_SETTINGS_PATH, {})

    activity = presence.get("current_activity", "")
    block = presence.get("current_time_block", "")
    mood = presence.get("surface_mood", "")
    energy_level = int(presence.get("energy_level", 50) or 50)
    affection_level = int(presence.get("affection_level", 50) or 50)
    last_user_mood = str(presence.get("last_user_mood", "") or "")
    appearance_branch = appearance.get("appearance_branch", "")
    outfit_context = appearance.get("outfit_context", "")
    top = appearance.get("top")
    weather_summary = weather.get("summary")
    weather_mood = str(weather.get("mood_bias", "") or "")
    continuity_band = continuity.get("continuity_band", "none")
    context_summary = (summarize_current_scene() or {}).get("context_summary") or ""
    content_level = resolve_content_level(activity, image_settings)

    image_type = "soft_selfie_encouragement"
    shot_pool = ["chest_up"]
    angle_pool = ["front_phone_selfie"]
    expression_pool = ["soft_smile"]
    pose_pool = ["phone_in_hand_relaxed"]
    framing_pool = ["subject_centered"]
    capture_method_pool = ["front_camera_handheld"]
    space_anchor_pool = ["neutral_personal_space"]
    face_angle_pool = ["front_facing"]
    gaze_pool = ["lens_eye_contact"]
    camera_height_pool = ["eye_level"]
    lens_distance_pool = ["arm_length_standard"]
    body_orientation_pool = ["square_to_camera"]
    expression_intensity_pool = ["gentle"]
    spontaneity_pool = ["natural_planned"]
    scene_focus = "face_and_mood"

    if activity in {"night_wind_down"} or appearance_branch == "night_home_relaxed" or "night" in block:
        image_type = "night_home_relaxed_selfie"
        shot_pool = ["face_closeup", "chest_up", "waist_up", "mirror_half_body"]
        angle_pool = ["top_down_phone_selfie", "pillow_level_three_quarter", "mirror_half_body", "side_lamp_glance"]
        expression_pool = ["sleepy_soft_smile", "small_pout", "quiet_eye_contact", "mellow_relaxed"]
        pose_pool = ["phone_near_cheek", "one_hand_blanket_hold", "hair_tuck", "leaned_on_pillow"]
        framing_pool = ["subject_centered", "slight_off_center", "lamp_and_bedside_in_frame", "close_crop_face_bias"]
        capture_method_pool = ["front_camera_handheld", "mirror_selfie", "propped_phone_timer"]
        space_anchor_pool = ["bedside", "bedroom_mirror", "vanity_corner"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "slight_profile", "chin_tucked_down"]
        gaze_pool = ["lens_eye_contact", "screen_preview_glance", "downward_relaxed", "side_lamp_glance"]
        camera_height_pool = ["slight_above_eye_level", "pillow_level", "eye_level", "mirror_mid_height"]
        lens_distance_pool = ["very_close", "arm_length_standard", "waist_distance_mirror", "bedside_mid_distance"]
        body_orientation_pool = ["shoulders_square_soft", "angled_shoulders_inward", "half_side_curl", "reclined_twist"]
        expression_intensity_pool = ["very_soft", "gentle", "mellow", "sleepy_playful"]
        spontaneity_pool = ["private_candid", "half_prepared", "woke_up_and_sent", "soft_timer_setup"]
        scene_focus = "home_relaxed_mood"
    elif activity == "lunch_break":
        lunch_sub = presence.get("lunch_sub_phase", "eating_lunch")
        if lunch_sub in {"moving_to_lunch", "returning_from_lunch"}:
            image_type = "home_lunch_selfie"
            shot_pool = ["chest_up", "half_body", "waist_up"]
            angle_pool = ["front_phone_selfie", "three_quarter_arm_length", "slight_high_angle"]
            expression_pool = ["bright_smile", "tired_but_cute", "closed_lip_smile"]
            pose_pool = ["walking_glance", "bag_strap_hold", "hair_adjust"]
            framing_pool = ["subject_centered", "station_or_hallway_context"]
            capture_method_pool = ["front_camera_handheld"]
            space_anchor_pool = ["office_hallway", "pangyo_street", "office_lobby"]  # 점심=판교 회사/거리(프롬프트 묘사)
            face_angle_pool = ["front_facing", "three_quarter_turn", "walking_turn_back"]
            gaze_pool = ["lens_eye_contact", "walking_glance", "off_to_side_focus"]
            camera_height_pool = ["eye_level", "slight_high_angle", "collarbone_level"]
            lens_distance_pool = ["arm_length_standard", "quick_step_distance"]
            body_orientation_pool = ["square_to_camera", "walking_stride", "one_shoulder_forward"]
            expression_intensity_pool = ["gentle", "fresh_bright", "tired_soft"]
            spontaneity_pool = ["between_tasks", "quick_update", "caught_mid_motion"]
            scene_focus = "home_routine"
        elif lunch_sub == "getting_coffee":
            image_type = "lunch_coffee_selfie"
            shot_pool = ["chest_up", "half_body", "table_portrait"]
            angle_pool = ["front_phone_selfie", "seated_three_quarter", "slight_high_angle"]
            expression_pool = ["warm_smile", "playful_grin", "closed_lip_smile"]
            pose_pool = ["cup_near_face", "waiting_at_counter", "coffee_in_hand"]
            framing_pool = ["table_items_in_frame", "subject_centered", "environment_balanced"]
            capture_method_pool = ["front_camera_handheld"]
            space_anchor_pool = ["pangyo_cafe", "office_pantry", "cafe_counter"]  # 점심=판교 카페(프롬프트 묘사)
            face_angle_pool = ["front_facing", "three_quarter_turn", "chin_lift"]
            gaze_pool = ["lens_eye_contact", "drink_or_table_glance", "off_to_side_focus"]
            camera_height_pool = ["eye_level", "slight_above_eye_level", "table_height"]
            lens_distance_pool = ["arm_length_standard", "table_distance"]
            body_orientation_pool = ["square_to_camera", "leaning_to_table", "one_shoulder_forward"]
            expression_intensity_pool = ["gentle", "warm", "playful"]
            spontaneity_pool = ["casual_update", "table_pause", "between_tasks"]
            scene_focus = "lifestyle_space"
        elif lunch_sub == "waiting_for_food":
            # 음식 아직 안 온 상태 — food props 전면 금지
            image_type = "lunch_waiting_selfie"
            shot_pool = ["chest_up", "half_body", "waist_up"]
            angle_pool = ["front_phone_selfie", "three_quarter_arm_length", "slight_high_angle"]
            expression_pool = ["closed_lip_smile", "tired_but_cute", "content_relaxed"]
            pose_pool = ["chin_rest", "resting_on_table", "cup_near_face", "phone_in_hand_relaxed"]
            framing_pool = ["subject_centered", "environment_balanced"]  # food_and_face_combo 제외
            capture_method_pool = ["front_camera_handheld", "propped_phone_timer"]
            space_anchor_pool = ["pangyo_restaurant_table", "office_cafeteria", "restaurant_seat"]  # 점심=판교 식당(프롬프트 묘사)
            face_angle_pool = ["front_facing", "three_quarter_turn", "chin_lift"]
            gaze_pool = ["lens_eye_contact", "downward_relaxed", "off_to_side_focus"]
            camera_height_pool = ["eye_level", "slight_above_eye_level"]
            lens_distance_pool = ["arm_length_standard", "table_distance"]
            body_orientation_pool = ["seated_open", "leaning_to_table", "one_shoulder_forward"]
            expression_intensity_pool = ["gentle", "tired_soft", "warm"]
            spontaneity_pool = ["table_pause", "casual_update", "caught_mid_motion"]
            scene_focus = "lunch_waiting_mood"
        else:
            # eating_lunch / finishing_lunch / default — 음식 도착 후
            image_type = "lunch_eating_selfie"
            shot_pool = ["chest_up", "half_body", "table_portrait", "waist_up"]
            angle_pool = ["seated_three_quarter", "front_phone_selfie", "low_table_angle"]
            expression_pool = ["warm_smile", "tired_but_cute", "content_relaxed", "playful_grin"]
            pose_pool = ["cup_near_face", "spoon_or_chopstick_hold", "chin_rest", "resting_on_table"]
            framing_pool = ["table_items_in_frame", "subject_centered", "environment_balanced", "food_and_face_combo"]
            capture_method_pool = ["front_camera_handheld", "propped_phone_timer"]
            space_anchor_pool = ["pangyo_restaurant_table", "office_cafeteria", "restaurant_seat"]  # 점심=판교 식당(프롬프트 묘사)
            face_angle_pool = ["front_facing", "three_quarter_turn", "chin_lift", "slight_profile"]
            gaze_pool = ["lens_eye_contact", "drink_or_table_glance", "downward_relaxed", "laughing_away"]
            camera_height_pool = ["eye_level", "slight_above_eye_level", "table_height"]
            lens_distance_pool = ["arm_length_standard", "table_distance", "half_body_distance"]
            body_orientation_pool = ["seated_open", "leaning_to_table", "one_shoulder_forward"]
            expression_intensity_pool = ["gentle", "warm", "tired_soft", "playful"]
            spontaneity_pool = ["casual_update", "table_pause", "mid_conversation_candid", "caught_mid_motion"]
            scene_focus = "lunch_break_mood"
    elif activity in {"waking_up", "getting_ready"}:
        image_type = "morning_ready_selfie"
        shot_pool = ["chest_up", "half_body", "mirror_quick_check", "waist_up"]
        angle_pool = ["mirror_half_body", "front_phone_selfie", "slight_high_angle", "three_quarter_arm_length"]
        expression_pool = ["bright_smile", "closed_lip_smile", "focused_soft", "tired_but_cute"]
        pose_pool = ["hair_adjust", "bag_strap_hold", "outfit_check", "phone_in_hand_relaxed"]
        framing_pool = ["subject_centered", "torso_and_outfit_bias", "mirror_with_door_context"]
        capture_method_pool = ["mirror_selfie", "front_camera_handheld"]
        space_anchor_pool = ["home_entrance_mirror", "bedroom_mirror", "vanity_corner", "hallway_door"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "mirror_check_angle"]
        gaze_pool = ["lens_eye_contact", "quick_mirror_check", "downward_relaxed"]
        camera_height_pool = ["eye_level", "slight_above_eye_level", "mirror_mid_height"]
        lens_distance_pool = ["arm_length_standard", "mirror_mid_distance", "half_body_distance"]
        body_orientation_pool = ["square_to_camera", "one_shoulder_forward", "angled_shoulders_inward"]
        expression_intensity_pool = ["gentle", "fresh_bright", "contained"]
        spontaneity_pool = ["mirror_check_in", "quick_update", "between_tasks"]
        scene_focus = "morning_prep_home"
    elif activity in {"morning_commute", "evening_commute"}:
        image_type = "commute_selfie"
        shot_pool = ["chest_up", "half_body", "face_closeup"]
        angle_pool = ["front_phone_selfie", "three_quarter_arm_length", "window_side_angle"]
        expression_pool = ["closed_lip_smile", "tired_but_cute", "soft_smile", "sleepy_soft_smile"]
        pose_pool = ["bag_strap_hold", "phone_in_hand_relaxed", "hair_adjust", "leaning_window"]
        framing_pool = ["subject_centered", "station_or_hallway_context", "window_light_natural"]
        capture_method_pool = ["front_camera_handheld"]
        # 통근(신분당선) — 배경 레퍼런스 없이 프롬프트로 묘사
        space_anchor_pool = ["subway_train_interior", "station_platform", "pangyo_street", "subway_window_seat"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "slight_profile"]
        gaze_pool = ["lens_eye_contact", "off_to_side_focus", "window_glance"]
        camera_height_pool = ["eye_level", "slight_high_angle", "collarbone_level"]
        lens_distance_pool = ["arm_length_standard", "close_selfie"]
        body_orientation_pool = ["square_to_camera", "one_shoulder_forward", "angled_shoulders_inward"]
        expression_intensity_pool = ["gentle", "tired_soft", "contained"]
        spontaneity_pool = ["quick_update", "between_tasks", "caught_mid_motion"]
        scene_focus = "commute"
    elif activity in {"morning_work", "afternoon_work", "late_afternoon", "morning_prep", "evening_free"}:
        image_type = "work_selfie"
        shot_pool = ["chest_up", "half_body", "mirror_quick_check", "waist_up"]
        angle_pool = ["front_phone_selfie", "three_quarter_arm_length", "slight_high_angle", "mirror_half_body"]
        expression_pool = ["bright_smile", "tired_but_cute", "closed_lip_smile", "focused_soft"]
        pose_pool = ["coffee_in_hand", "chin_rest", "leaning_on_desk", "hair_adjust"]
        framing_pool = ["subject_centered", "room_context_behind", "window_light_natural", "torso_and_outfit_bias"]
        capture_method_pool = ["front_camera_handheld", "propped_phone_timer", "mirror_selfie"]
        if activity in {"morning_work", "afternoon_work", "late_afternoon"}:
            # 회사(판교) 근무 중 — 배경 레퍼런스 없이 프롬프트로 묘사(사무실 데스크/판교)
            space_anchor_pool = ["office_desk", "office_desk", "office_meeting_corner", "office_pantry", "office_window_view", "office_restroom_mirror"]
            scene_focus = "office_work"
        else:
            # morning_prep / evening_free — 집(원룸)
            space_anchor_pool = ["desk_area", "desk_area", "bathroom_mirror", "living_room_couch", "room_corner"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "slight_profile"]
        gaze_pool = ["lens_eye_contact", "off_to_side_focus", "quick_mirror_check"]
        camera_height_pool = ["eye_level", "slight_high_angle", "collarbone_level", "mirror_mid_height"]
        lens_distance_pool = ["arm_length_standard", "torso_distance", "mirror_mid_distance"]
        body_orientation_pool = ["square_to_camera", "one_shoulder_forward", "angled_shoulders_inward"]
        expression_intensity_pool = ["gentle", "fresh_bright", "contained", "tired_soft"]
        spontaneity_pool = ["between_tasks", "quick_update", "mirror_check_in", "caught_mid_motion"]
        scene_focus = "office_work" if activity in {"morning_work", "afternoon_work", "late_afternoon"} else "home_routine"
    elif activity in {"evening_home_work"}:
        # v2: 저녁 집 작업 — 샤워 후 잠옷 입고 컴퓨터 앞 (야외/카페 없음)
        image_type = "night_home_relaxed_selfie"
        shot_pool = ["half_body", "chest_up", "waist_up", "table_seated"]
        angle_pool = ["front_phone_selfie", "three_quarter_arm_length", "slight_high_angle"]
        expression_pool = ["mellow_relaxed", "warm_smile", "quiet_eye_contact", "content_relaxed"]
        pose_pool = ["phone_near_cheek", "hair_tuck", "chin_rest", "phone_in_hand_relaxed"]
        framing_pool = ["subject_centered", "subject_off_center", "lamp_and_bedside_in_frame"]
        capture_method_pool = ["front_camera_handheld", "propped_phone_timer"]
        space_anchor_pool = ["desk_area", "living_room_couch", "room_corner"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "chin_tucked_down"]
        gaze_pool = ["lens_eye_contact", "screen_preview_glance", "downward_relaxed"]
        camera_height_pool = ["eye_level", "slight_above_eye_level", "pillow_level"]
        lens_distance_pool = ["arm_length_standard", "portrait_distance", "half_body_distance"]
        body_orientation_pool = ["square_to_camera", "angled_shoulders_inward", "half_side_curl"]
        expression_intensity_pool = ["gentle", "mellow", "very_soft"]
        spontaneity_pool = ["private_candid", "casual_update", "soft_timer_setup"]
        scene_focus = "home_relaxed_mood"
    elif activity in {"dinner_deciding", "dinner_preparing", "dinner_eating", "dinner_or_cooking"} or "home" in outfit_context:
        image_type = "home_lifestyle_soft"
        shot_pool = ["waist_up", "half_body", "table_seated", "detail_plus_portrait"]
        angle_pool = ["kitchen_counter_angle", "seated_eye_level", "three_quarter_home_snap", "side_profile_home"]
        expression_pool = ["gentle_smile", "content_relaxed", "fond_eye_contact", "small_laugh"]
        pose_pool = ["holding_mug", "resting_on_table", "looking_back_over_shoulder", "hair_tuck"]
        framing_pool = ["table_or_mug_in_frame", "soft_room_context", "subject_centered", "home_detail_balance"]
        # 식사/주방/거실엔 거울이 없음 — 거울샷 제외(식탁 앞 거울샷 방지)
        capture_method_pool = ["front_camera_handheld", "propped_phone_timer"]
        if activity == "dinner_eating":
            # 식사 중 = 식탁/주방 고정. 욕실/화장대 금지.
            space_anchor_pool = ["dining_table", "kitchen_counter", "living_room_sofa"]
        else:
            space_anchor_pool = ["kitchen_counter", "dining_table", "living_room_corner"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "over_shoulder_turn", "side_profile_soft"]
        gaze_pool = ["lens_eye_contact", "table_item_glance", "over_shoulder_glance", "downward_relaxed"]
        camera_height_pool = ["eye_level", "counter_height", "slight_above_eye_level", "collarbone_level"]
        lens_distance_pool = ["arm_length_standard", "table_distance", "half_body_distance", "room_context_distance"]
        body_orientation_pool = ["square_to_camera", "seated_side_angle", "counter_lean", "turning_back_soft"]
        expression_intensity_pool = ["gentle", "warm", "fond", "content"]
        spontaneity_pool = ["domestic_candid", "sent_while_making_food", "soft_timer_setup", "table_pause"]
        scene_focus = "domestic_warmth"
    elif weather.get("current_condition") == "rain":
        image_type = "rainy_mood_portrait"
        shot_pool = ["face_closeup", "chest_up", "window_side_portrait", "waist_up"]
        angle_pool = ["window_reflection_angle", "three_quarter_soft", "profile_rain_glance", "slight_low_angle"]
        expression_pool = ["rain_soft_smile", "reflective_gaze", "warm_pout", "quiet_serene"]
        pose_pool = ["holding_umbrella", "resting_on_window", "hair_touch", "coat_or_cardigan_pull"]
        framing_pool = ["rain_window_context", "soft_bokeh_background", "subject_off_center", "weather_and_face_balance"]
        capture_method_pool = ["front_camera_handheld", "mirror_selfie", "propped_phone_timer"]
        space_anchor_pool = ["window_side", "building_entry_mirror", "umbrella_stop"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "slight_profile", "rain_profile"]
        gaze_pool = ["lens_eye_contact", "window_outside_glance", "downward_reflection", "side_glance"]
        camera_height_pool = ["eye_level", "slight_above_eye_level", "window_height", "slight_low_angle"]
        lens_distance_pool = ["very_close", "arm_length_standard", "portrait_distance", "weather_context_distance"]
        body_orientation_pool = ["square_to_camera", "window_side_lean", "shoulders_inward", "half_side_wrap"]
        expression_intensity_pool = ["very_soft", "gentle", "serene", "reflective"]
        spontaneity_pool = ["weather_pause", "window_candid", "soft_timer_setup", "umbrella_stop_snap"]
        scene_focus = "weather_mood"

    if energy_level <= 42 or "tired" in last_user_mood or "cozy" in mood:
        expression_pool = ["mellow_relaxed", "quiet_eye_contact"] + [item for item in expression_pool if item not in {"mellow_relaxed", "quiet_eye_contact"}]
        gaze_pool = ["downward_relaxed", "lens_eye_contact"] + [item for item in gaze_pool if item not in {"downward_relaxed", "lens_eye_contact"}]
        expression_intensity_pool = ["very_soft", "gentle"] + [item for item in expression_intensity_pool if item not in {"very_soft", "gentle"}]
        spontaneity_pool = ["private_candid", "soft_timer_setup"] + [item for item in spontaneity_pool if item not in {"private_candid", "soft_timer_setup"}]
    elif energy_level >= 72:
        expression_pool = ["playful_grin", "bright_smile"] + [item for item in expression_pool if item not in {"playful_grin", "bright_smile"}]
        gaze_pool = ["lens_eye_contact", "laughing_away"] + [item for item in gaze_pool if item not in {"lens_eye_contact", "laughing_away"}]
        expression_intensity_pool = ["playful", "sparked"] + [item for item in expression_intensity_pool if item not in {"playful", "sparked"}]
        spontaneity_pool = ["caught_mid_motion", "casual_update"] + [item for item in spontaneity_pool if item not in {"caught_mid_motion", "casual_update"}]

    if affection_level >= 78:
        expression_pool = ["fond_eye_contact", "warm_smile"] + [item for item in expression_pool if item not in {"fond_eye_contact", "warm_smile"}]
        gaze_pool = ["lens_eye_contact", "screen_preview_glance"] + [item for item in gaze_pool if item not in {"lens_eye_contact", "screen_preview_glance"}]
        body_orientation_pool = ["one_shoulder_forward", "angled_shoulders_inward"] + [item for item in body_orientation_pool if item not in {"one_shoulder_forward", "angled_shoulders_inward"}]

    if "soft" in weather_mood or weather.get("current_condition") in {"cloudy", "rain"}:
        framing_pool = ["subject_off_center", "soft_bokeh_background"] + [item for item in framing_pool if item not in {"subject_off_center", "soft_bokeh_background"}]
        lens_distance_pool = ["portrait_distance", "very_close"] + [item for item in lens_distance_pool if item not in {"portrait_distance", "very_close"}]

    if "mirror" in context_summary or "화장대" in context_summary or "세면대" in context_summary:
        capture_method_pool = ["mirror_selfie"] + [method for method in capture_method_pool if method != "mirror_selfie"]
    elif any(keyword in context_summary for keyword in ["출근길", "퇴근길", "길", "거리", "카페", "지하철", "플랫폼"]):
        capture_method_pool = ["front_camera_handheld"] + [method for method in capture_method_pool if method != "front_camera_handheld"]

    seed_base = "%s:%s:%s:%s:%s:%s" % (
        now_local().strftime("%Y-%m-%d:%H"),
        activity or block,
        mood,
        appearance_branch,
        top or "none",
        reason,
    )
    recent_shots = [item.get("shot_type") for item in recent_plans]
    recent_angles = [item.get("camera_angle") for item in recent_plans]
    recent_expressions = [item.get("expression") for item in recent_plans]
    recent_poses = [item.get("pose") for item in recent_plans]
    recent_framings = [item.get("framing") for item in recent_plans]
    recent_methods = [item.get("selfie_capture_method") for item in recent_plans]
    recent_spaces = [item.get("space_anchor") for item in recent_plans]
    recent_face_angles = [item.get("face_angle") for item in recent_plans]
    recent_gazes = [item.get("gaze_direction") for item in recent_plans]
    recent_camera_heights = [item.get("camera_height") for item in recent_plans]
    recent_lens_distances = [item.get("lens_distance") for item in recent_plans]
    recent_body_orientations = [item.get("body_orientation") for item in recent_plans]
    recent_expression_intensities = [item.get("expression_intensity") for item in recent_plans]
    recent_spontaneities = [item.get("spontaneity") for item in recent_plans]

    shot_type = rotate_pick_recent(shot_pool, seed_base + ":shot", recent_shots[:3])
    camera_angle = rotate_pick_recent(angle_pool, seed_base + ":angle", recent_angles[:3])
    expression = rotate_pick_recent(expression_pool, seed_base + ":expression", recent_expressions[:2])
    pose = rotate_pick_recent(pose_pool, seed_base + ":pose", recent_poses[:3])
    framing = rotate_pick_recent(framing_pool, seed_base + ":framing", recent_framings[:3])
    selfie_capture_method = rotate_pick_recent(capture_method_pool, seed_base + ":method", recent_methods[:3])
    space_anchor = rotate_pick_recent(space_anchor_pool, seed_base + ":space", recent_spaces[:3])
    face_angle = rotate_pick_recent(face_angle_pool, seed_base + ":face_angle", recent_face_angles[:3])
    gaze_direction = rotate_pick_recent(gaze_pool, seed_base + ":gaze", recent_gazes[:3])
    camera_height = rotate_pick_recent(camera_height_pool, seed_base + ":camera_height", recent_camera_heights[:3])
    lens_distance = rotate_pick_recent(lens_distance_pool, seed_base + ":lens_distance", recent_lens_distances[:3])
    body_orientation = rotate_pick_recent(body_orientation_pool, seed_base + ":body_orientation", recent_body_orientations[:3])
    expression_intensity = rotate_pick_recent(
        expression_intensity_pool, seed_base + ":expression_intensity", recent_expression_intensities[:3]
    )
    spontaneity = rotate_pick_recent(spontaneity_pool, seed_base + ":spontaneity", recent_spontaneities[:3])

    recent_combos = {
        (
            item.get("shot_type"),
            item.get("camera_angle"),
            item.get("framing"),
            item.get("selfie_capture_method"),
            item.get("space_anchor"),
            item.get("face_angle"),
            item.get("gaze_direction"),
            item.get("lens_distance"),
        )
        for item in recent_plans[:4]
    }
    for attempt in range(6):
        combo = (
            shot_type,
            camera_angle,
            framing,
            selfie_capture_method,
            space_anchor,
            face_angle,
            gaze_direction,
            lens_distance,
        )
        if combo not in recent_combos:
            break
        shot_type = rotate_pick_recent(shot_pool, seed_base + ":shot:%d" % attempt, recent_shots[:2])
        camera_angle = rotate_pick_recent(angle_pool, seed_base + ":angle:%d" % attempt, recent_angles[:2])
        framing = rotate_pick_recent(framing_pool, seed_base + ":framing:%d" % attempt, recent_framings[:2])
        selfie_capture_method = rotate_pick_recent(capture_method_pool, seed_base + ":method:%d" % attempt, recent_methods[:2])
        space_anchor = rotate_pick_recent(space_anchor_pool, seed_base + ":space:%d" % attempt, recent_spaces[:2])
        face_angle = rotate_pick_recent(face_angle_pool, seed_base + ":face_angle:%d" % attempt, recent_face_angles[:2])
        gaze_direction = rotate_pick_recent(gaze_pool, seed_base + ":gaze:%d" % attempt, recent_gazes[:2])
        lens_distance = rotate_pick_recent(
            lens_distance_pool, seed_base + ":lens_distance:%d" % attempt, recent_lens_distances[:2]
        )

    if selfie_capture_method == "mirror_selfie":
        if "mirror" not in shot_type:
            shot_type = rotate_pick_recent(
                [item for item in shot_pool if "mirror" in item] or ["mirror_half_body"],
                seed_base + ":mirror_shot",
                recent_shots[:2],
            )
        if "mirror" not in camera_angle:
            camera_angle = rotate_pick_recent(
                [item for item in angle_pool if "mirror" in item] or ["mirror_half_body"],
                seed_base + ":mirror_angle",
                recent_angles[:2],
            )
        if "mirror" not in space_anchor:
            space_anchor = rotate_pick_recent(
                [item for item in space_anchor_pool if "mirror" in item] or ["vanity_mirror"],
                seed_base + ":mirror_space",
                recent_spaces[:2],
            )
        camera_height = rotate_pick_recent(
            [item for item in camera_height_pool if "mirror" in item or item in {"mirror_mid_height", "eye_level"}]
            or ["mirror_mid_height"],
            seed_base + ":mirror_height",
            recent_camera_heights[:2],
        )
        lens_distance = rotate_pick_recent(
            [item for item in lens_distance_pool if "mirror" in item or "distance" in item or "waist" in item]
            or ["waist_distance_mirror"],
            seed_base + ":mirror_distance",
            recent_lens_distances[:2],
        )
    elif selfie_capture_method == "front_camera_handheld":
        if "mirror" in shot_type:
            shot_type = rotate_pick_recent(
                [item for item in shot_pool if "mirror" not in item] or ["chest_up"],
                seed_base + ":front_shot",
                recent_shots[:2],
            )
        if "mirror" in camera_angle:
            camera_angle = rotate_pick_recent(
                [item for item in angle_pool if "mirror" not in item] or ["front_phone_selfie"],
                seed_base + ":front_angle",
                recent_angles[:2],
            )
        if "mirror" in space_anchor:
            space_anchor = rotate_pick_recent(
                [item for item in space_anchor_pool if "mirror" not in item] or ["street_walk"],
                seed_base + ":front_space",
                recent_spaces[:2],
            )
        camera_height = rotate_pick_recent(
            [item for item in camera_height_pool if "mirror" not in item] or ["eye_level"],
            seed_base + ":front_height",
            recent_camera_heights[:2],
        )
    elif selfie_capture_method == "propped_phone_timer":
        if "mirror" in shot_type:
            shot_type = rotate_pick_recent(
                [item for item in shot_pool if "mirror" not in item] or ["waist_up"],
                seed_base + ":timer_shot",
                recent_shots[:2],
            )
        if "mirror" in camera_angle:
            camera_angle = rotate_pick_recent(
                [item for item in angle_pool if "mirror" not in item] or ["seated_eye_level"],
                seed_base + ":timer_angle",
                recent_angles[:2],
            )
        spontaneity = rotate_pick_recent(
            [item for item in spontaneity_pool if "timer" in item or "planned" in item] or ["soft_timer_setup"],
            seed_base + ":timer_spontaneity",
            recent_spontaneities[:2],
        )

    if shot_type in {"face_closeup", "window_side_portrait"}:
        lens_distance = rotate_pick_recent(
            [item for item in lens_distance_pool if item in {"very_close", "portrait_distance", "arm_length_standard"}]
            or ["very_close"],
            seed_base + ":close_lens",
            recent_lens_distances[:2],
        )
    elif shot_type in {"mirror_half_body", "half_body", "half_body_seated", "waist_up", "table_seated"}:
        lens_distance = rotate_pick_recent(
            [item for item in lens_distance_pool if item not in {"very_close"}] or ["half_body_distance"],
            seed_base + ":mid_lens",
            recent_lens_distances[:2],
        )

    if shot_type in {"full_body_candid", "full_body_umbrella_candid"}:
        crop_bias = "full_body"
    elif shot_type in {"half_body", "table_seated", "waist_up", "mirror_half_body", "half_body_seated"}:
        crop_bias = "half_body_to_waist"
    elif shot_type in {"face_closeup", "window_side_portrait"}:
        crop_bias = "closeup"
    else:
        crop_bias = "chest_up"

    if selfie_capture_method == "mirror_selfie":
        camera_visibility = "phone_visible_in_mirror"
        selfie_authenticity = "거울 반사 안에 폰이 자연스럽게 보여도 괜찮고, 셀피처럼 보여야 함"
    elif selfie_capture_method == "propped_phone_timer":
        camera_visibility = "phone_out_of_frame_timer_capture"
        selfie_authenticity = "혼자 폰을 기대두고 타이머로 찍은 자연스러운 셀프샷처럼 보여야 함"
    else:
        camera_visibility = "front_camera_phone_not_visible"
        selfie_authenticity = "전면 카메라로 직접 들고 찍은 셀카처럼 보여야 하고 남이 찍은 사진처럼 보이면 안 됨"

    composition_rules = []
    if continuity_band == "immediate_repeat":
        composition_rules.append("직전 사진과 공간, 착장, 얼굴 상태를 거의 유지")
    elif continuity_band == "same_outfit_window":
        composition_rules.append("착장과 얼굴 상태는 유지하되 구도와 배경은 바꿔도 됨")
    else:
        composition_rules.append("현재 상황에 맞는 새 공간과 구도 허용")
    composition_rules.append("최근 3~4장과 shot/angle/framing/method/space 조합이 겹치지 않게 할 것")
    composition_rules.append("표정, 얼굴 방향, 시선, 렌즈 거리감, 카메라 높이 중 최소 2개 이상은 최근 셀피와 다르게 가져갈 것")
    if weather_summary:
        composition_rules.append("날씨 기운: %s" % weather_summary)
    if top:
        composition_rules.append("복장 포인트: %s" % top)
    composition_rules.append("셀피 방식: %s" % selfie_capture_method)
    composition_rules.append("공간 앵커: %s" % space_anchor)
    composition_rules.append("얼굴 방향: %s / 시선: %s" % (face_angle, gaze_direction))
    composition_rules.append("카메라 높이: %s / 거리감: %s" % (camera_height, lens_distance))
    composition_rules.append("몸 방향: %s / 표정 강도: %s / 순간성: %s" % (body_orientation, expression_intensity, spontaneity))
    composition_rules.append(selfie_authenticity)

    prompt_fragments = [
        "이미지 타입: %s" % image_type,
        "샷 타입: %s" % shot_type,
        "카메라 각도: %s" % camera_angle,
        "셀피 촬영 방식: %s" % selfie_capture_method,
        "카메라 노출 방식: %s" % camera_visibility,
        "표정: %s" % expression,
        "표정 강도: %s" % expression_intensity,
        "얼굴 방향: %s" % face_angle,
        "시선 방향: %s" % gaze_direction,
        "포즈: %s" % pose,
        "몸 방향: %s" % body_orientation,
        "프레이밍: %s" % framing,
        "카메라 높이: %s" % camera_height,
        "렌즈 거리감: %s" % lens_distance,
        "순간성: %s" % spontaneity,
        "공간 기준점: %s" % space_anchor,
        "구도 우선: %s" % scene_focus,
        "크롭 성향: %s" % crop_bias,
    ]

    plan = {
        "schema_version": 1,
        "managed_by": "share_priority_engine",
        "generated_at": now_iso(),
        "reason": reason,
        "image_type": image_type,
        "shot_type": shot_type,
        "camera_angle": camera_angle,
        "selfie_capture_method": selfie_capture_method,
        "camera_visibility": camera_visibility,
        "expression": expression,
        "expression_intensity": expression_intensity,
        "pose": pose,
        "framing": framing,
        "crop_bias": crop_bias,
        "space_anchor": space_anchor,
        "face_angle": face_angle,
        "gaze_direction": gaze_direction,
        "camera_height": camera_height,
        "lens_distance": lens_distance,
        "body_orientation": body_orientation,
        "spontaneity": spontaneity,
        "scene_focus": scene_focus,
        "activity": activity,
        "time_block": block,
        "surface_mood": mood,
        "appearance_branch": appearance_branch,
        "outfit_context": outfit_context,
        "weather_summary": weather_summary,
        "continuity_band": continuity_band,
        "composition_rules": composition_rules,
        "prompt_fragments": prompt_fragments,
        "recent_avoid_keys": [
            "%s|%s|%s|%s|%s|%s|%s|%s"
            % (
                item.get("shot_type"),
                item.get("camera_angle"),
                item.get("framing"),
                item.get("selfie_capture_method"),
                item.get("space_anchor"),
                item.get("face_angle"),
                item.get("gaze_direction"),
                item.get("lens_distance"),
            )
            for item in recent_plans[:4]
        ],
        "notes": "다음 이미지 생성 시 셀피/라이프스타일 샷 구도 반복을 줄이기 위한 샷 플랜",
        "content_level": content_level,
        "reference_images": _pick_reference_images(face_angle, shot_type, pose),
    }

    plan["text_prompt"] = _build_text_prompt(plan)
    plan["negative_prompt"] = (
        "outdoor, beach, cafe exterior, park, street, gym, swimming pool, "
        "sports uniform, overexposed, blurry face, heavy filter, distorted features, "
        "extra limbs, cartoon, anime, illustration"
    )

    # 레벨2 + 이동 상황: 이너웨어 자연 노출 힌트 주입
    if content_level == 2 and activity in {"morning_prep", "evening_free"}:
        iw_type = appearance.get("innerwear_type") or (appearance.get("home_work_outfit") or {}).get("innerwear_type")
        iw_color = appearance.get("innerwear_color") or (appearance.get("home_work_outfit") or {}).get("innerwear_color")
        if iw_type:
            plan["innerwear_hint"] = {
                "visibility": "natural_show",
                "type": iw_type,
                "color": iw_color or "skin_beige",
                "instruction": "상의 네크라인이나 옷 사이로 이너웨어가 자연스럽게 살짝 보이는 구도. 강조 금지, 자연스럽게."
            }

    save_json(IMAGE_PROMPT_PLAN_PATH, plan)
    save_recent_image_plan(plan)
    return plan


