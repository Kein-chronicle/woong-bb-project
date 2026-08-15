#!/usr/bin/env python3
"""
shot_case_selector.py
상태별 허용 샷 케이스 프리셋에서 하나를 랜덤 선택해 image_prompt_plan.json을 갱신.
이미지 생성 직전에 호출해야 함.

Usage:
  python3 shot_case_selector.py           # 상태 자동 판단 후 케이스 선택
  python3 shot_case_selector.py --dry-run  # 선택만 하고 파일 저장 안 함
직접 요청 모드(--direct-request):
  python3 shot_case_selector.py --direct-request
  공간 앵커 강제 없이 집(원룸) 안에서 자유롭게 생성.
"""
import argparse
import json
import random
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/kein/Desktop/woong-bb")
PRESETS_PATH  = BASE / "state" / "shot_case_presets.json"
PROMPT_PATH   = BASE / "state" / "image_prompt_plan.json"
APPEARANCE    = BASE / "state" / "eunbi_appearance_state.json"
SHOT_HISTORY  = BASE / "state" / "image_shot_history.json"


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(p: Path, d: dict) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pick_group(appearance: dict, presets: dict) -> str | None:
    branch = appearance.get("appearance_branch", "")
    outfit = appearance.get("outfit_context", "")
    state_map = presets.get("state_to_group_map", {})

    branch_map = state_map.get("appearance_branch_map", {})
    for key, group in branch_map.items():
        if key in branch:
            return group

    outfit_map = state_map.get("outfit_context_map", {})
    for key, group in outfit_map.items():
        if key in outfit:
            return group

    return None


def recent_case_ids(shot_history: dict, limit: int = 3) -> list:
    """최근 발송된 케이스 id 목록 (반복 억제용)"""
    plans = shot_history.get("recent_plans", [])
    return [p.get("shot_case_id") for p in plans[-limit:] if p.get("shot_case_id")]


def recent_pose_ids(shot_history: dict, limit: int = 3) -> list:
    """최근 사용된 포즈 variant id 목록 (반복 억제용)"""
    plans = shot_history.get("recent_plans", [])
    return [p.get("pose_variant_id") for p in plans[-limit:] if p.get("pose_variant_id")]


def select_pose_variant(group_data: dict, exclude_ids: list) -> dict | None:
    """그룹의 pose_variants에서 최근 미사용 항목 선택"""
    variants = group_data.get("pose_variants", [])
    if not variants:
        return None
    fresh = [v for v in variants if v["id"] not in exclude_ids]
    pool = fresh if fresh else variants
    return random.choice(pool)


def select_case(group_id: str, presets: dict, exclude_ids: list) -> dict | None:
    group = presets.get("groups", {}).get(group_id)
    if not group:
        return None
    cases = group.get("cases", [])
    # 최근 3장 중복 제외
    fresh = [c for c in cases if c["id"] not in exclude_ids]
    pool = fresh if fresh else cases
    return random.choice(pool) if pool else None


def apply_to_prompt(prompt: dict, case: dict, group_id: str, pose_variant: dict | None = None) -> dict:
    """선택된 케이스를 image_prompt_plan에 반영"""
    prompt["shot_case_group"] = group_id
    prompt["shot_case_id"] = case["id"]
    prompt["selfie_capture_method"] = case["selfie_method"]
    prompt["space_anchor"] = case["space_anchor"]
    prompt["framing"] = case.get("framing", prompt.get("framing", "chest_up"))
    prompt["camera_height"] = case.get("camera_height", "eye_level")
    prompt["lens_distance"] = case.get("lens_distance", "arm_length_standard")
    prompt["face_angle"] = case.get("face_angle", "front_facing")
    prompt["gaze_direction"] = case.get("gaze", "lens_eye_contact")
    prompt["shot_vibe"] = case.get("vibe", "")

    # composition_rules 앞에 케이스 고정 항목 주입
    existing = prompt.get("composition_rules", [])
    case_rules = [
        f"[shot_case] {case['id']} 기준으로 생성. 케이스 외 공간/의상/셀카방식 변주 금지.",
        f"셀카 방식: {case['selfie_method']}",
        f"공간 앵커: {case['space_anchor']}",
        f"프레이밍: {case.get('framing', '')} / 카메라 높이: {case.get('camera_height', '')}",
        f"얼굴 각도: {case.get('face_angle', '')} / 시선: {case.get('gaze', '')}",
        "제3자가 찍어준 것처럼 보이는 구도 절대 금지",
    ]
    # 기존 케이스/포즈 규칙 제거 후 재주입
    clean = [r for r in existing
             if not r.startswith("[shot_case]") and "셀카 방식:" not in r
             and not r.startswith("[pose_variant]") and "손/팔 동작:" not in r]

    if pose_variant:
        prompt["pose_variant_id"] = pose_variant["id"]
        prompt["pose"] = (
            f"{pose_variant['hand_action']}, {pose_variant['arm_position']}, "
            f"{pose_variant['torso_turn']}, {pose_variant['shoulder_shape']}"
        )
        pose_rules = [
            f"[pose_variant] {pose_variant['id']} — {pose_variant['vibe']}",
            f"손/팔 동작: {pose_variant['hand_action']} / 팔 위치: {pose_variant['arm_position']}",
            f"몸통 회전: {pose_variant['torso_turn']} / 어깨 형태: {pose_variant['shoulder_shape']}",
        ]
        prompt["composition_rules"] = case_rules + pose_rules + clean
    else:
        prompt["pose_variant_id"] = None
        prompt["composition_rules"] = case_rules + clean

    prompt["shot_case_selected_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return prompt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--direct-request", action="store_true",
                        help="오빠가 직접 사진 요청 — 공간 앵커 강제 없이 집 안 자유 생성")
    args = parser.parse_args()

    presets = load(PRESETS_PATH)
    appearance = load(APPEARANCE)
    prompt = load(PROMPT_PATH)
    shot_history = load(SHOT_HISTORY)

    # 직접 요청 모드: 공간 제약 없이 현재 의상/외형만 유지, 공간은 자유
    if args.direct_request:
        prompt["shot_case_id"] = "direct_request_free"
        prompt["shot_case_group"] = "direct_request"
        # 직접 요청은 장소가 불확정(집/통근/회사) — 거울샷은 실제 거울 있는 실내에서만
        # 성립하므로 여기선 제외. 전면카메라/타이머 셀카만 허용해 지하철·거리 거울샷 방지.
        prompt["selfie_capture_method"] = random.choice([
            "front_camera_handheld", "phone_propped_timer"
        ])
        # 공간 앵커를 현재 상태 기반으로 느슨하게 설정
        prompt["space_anchor"] = "any_personal_space"
        # composition_rules에서 공간 강제 제거, 집 안 자유 생성 명시
        existing = [r for r in prompt.get("composition_rules", [])
                    if not r.startswith("[shot_case]") and "셀카 방식:" not in r
                    and "공간 앵커:" not in r and "SP-0" not in r]
        prompt["composition_rules"] = [
            "[direct_request] 오빠가 직접 요청한 사진 — 공간 제약 없이 자유롭게 생성.",
            "배경은 현재 상황(집=원룸/통근=지하철·거리/회사=사무실·판교)에 맞게 프롬프트로 자유롭게 묘사. 배경 레퍼런스 없이 생성 가능(얼굴 레퍼런스는 유지).",
            f"셀카 방식: {prompt['selfie_capture_method']}",
            "거울샷 금지: 지하철·거리·야외·이동 중에는 거울샷이 성립하지 않음. 전면카메라 셀카로 처리.",
            "의상/외형은 appearance_state 기준 유지. 공간은 자연스러운 아무 공간.",
            "제3자가 찍어준 것처럼 보이는 구도 금지.",
        ] + existing
        prompt["shot_case_selected_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

        print(json.dumps({
            "mode": "direct_request_free",
            "selfie_method": prompt["selfie_capture_method"],
            "space_anchor": "free",
            "note": "집 안 자유 — 공간 앵커 없음",
            "dry_run": args.dry_run,
        }, ensure_ascii=False))

        if not args.dry_run:
            save(PROMPT_PATH, prompt)
            print("image_prompt_plan.json 갱신 완료 (직접 요청 자유 모드)")
        return

    group_id = pick_group(appearance, presets)
    if not group_id:
        print(f"상태 매핑 실패 — appearance_branch={appearance.get('appearance_branch')}, outfit={appearance.get('outfit_context')}")
        return

    group_data = presets.get("groups", {}).get(group_id, {})

    exclude_cases = recent_case_ids(shot_history)
    case = select_case(group_id, presets, exclude_cases)
    if not case:
        print(f"케이스 없음 — group={group_id}")
        return

    exclude_poses = recent_pose_ids(shot_history)
    pose_variant = select_pose_variant(group_data, exclude_poses)

    updated = apply_to_prompt(prompt, case, group_id, pose_variant)

    print(json.dumps({
        "group": group_id,
        "case": case["id"],
        "selfie_method": case["selfie_method"],
        "space_anchor": case["space_anchor"],
        "vibe": case.get("vibe", ""),
        "pose_variant": pose_variant["id"] if pose_variant else None,
        "pose_vibe": pose_variant["vibe"] if pose_variant else None,
        "dry_run": args.dry_run,
    }, ensure_ascii=False))

    if not args.dry_run:
        save(PROMPT_PATH, updated)
        print("image_prompt_plan.json 갱신 완료")


if __name__ == "__main__":
    main()
