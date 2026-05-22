#!/usr/bin/env python3
import json
import random
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from automation.conversation_guard import compute_conversation_guard, load_message_events
from automation.diary import write_daily_diary
from automation.event_triggers import (
    derive_event_keys_for_transition,
    factual_status_for_activity,
    normalize_fact_expression,
    parse_event_trigger_command,
)
from automation.io import append_jsonl, load_json, now_iso, now_local, save_json
from automation.runtime_state import (
    CONTROL_PATH,
    LOCK_PATH,
    WORKER_STATE_PATH,
    acquire_lock,
    release_lock,
    stop_state,
    update_control_ready,
    update_runtime_state,
)
from automation.telegram_io import append_message_log, append_worker_note, send_telegram_text, send_telegram_voice_message
from project_paths import MESSAGES, ROOT, STATE, ensure_operational_dirs, log_path


MODE_PATH = STATE / "mode_state.json"
TIMERS_PATH = STATE / "timers.json"
RECALC_STATE_PATH = STATE / "share_priority_recalc_state.json"

PRESENCE_PATH = STATE / "eunbi_presence.json"
DAY_CONTEXT_PATH = STATE / "day_context.json"
RANDOM_EVENT_POOL_PATH = STATE / "random_event_pool.json"
APPEARANCE_PATH = STATE / "eunbi_appearance_state.json"
WEATHER_PATH = STATE / "weather_context.json"
MEDIA_PATH = STATE / "media_watch_context.json"
PROACTIVE_PATH = STATE / "proactive_messages.json"
SHARE_CONTEXT_PATH = STATE / "share_event_context.json"
SHARE_PRIORITY_PATH = STATE / "share_priority_state.json"
SHARE_FLOW_PATH = STATE / "share_event_flow_state.json"
VOICE_SHARE_CONTEXT_PATH = STATE / "voice_share_event_context.json"
MEDIA_CHOICE_PATH = STATE / "media_choice_by_intent.json"
IMAGE_SETTINGS_PATH = STATE / "image_generation_settings.json"
IMAGE_GUARD_PATH = STATE / "image_generation_guard.json"
IMAGE_PROMPT_PLAN_PATH = STATE / "image_prompt_plan.json"
IMAGE_SHOT_HISTORY_PATH = STATE / "image_shot_history.json"
REINFORCEMENT_STATE_PATH = STATE / "user_preference_reinforcement.json"
DAILY_DIARY_STATE_PATH = STATE / "daily_diary_state.json"
MEMORY_DECAY_PATH = STATE / "memory_decay_state.json"
MOOD_RESIDUE_PATH = STATE / "mood_residue_state.json"
SIGNATURE_PHRASES_PATH = STATE / "signature_phrases.json"
AMBIENT_EVENTS_PATH = STATE / "ambient_life_events_state.json"
REPLY_VARIANCE_PATH = STATE / "reply_variance_state.json"
TASTE_FRICTION_PATH = STATE / "taste_friction_state.json"
PHRASE_REPETITION_GUARD_PATH = STATE / "phrase_repetition_guard_state.json"
DAY_SATISFACTION_PATH = STATE / "day_satisfaction_state.json"
RESPONSE_DECISION_LOG_PATH = log_path("response_decision_log.jsonl")
MOOD_TIMELINE_PATH = STATE / "mood_timeline.json"
PROACTIVE_PATTERN_REPORT_PATH = STATE / "proactive_pattern_report.json"
VOICE_FEEDBACK_LOG_PATH = log_path("voice_feedback_log.jsonl")
REPETITION_REPORT_PATH = STATE / "repetition_report.json"
RELATIONSHIP_PROGRESS_NOTES_PATH = STATE / "relationship_progress_notes.json"
CHAT_RUNTIME_SNAPSHOT_PATH = STATE / "chat_runtime_snapshot.json"
CONVERSATION_PATTERN_STATE_PATH = STATE / "conversation_pattern_state.json"
CONVERSATION_PATTERN_CATALOG_PATH = STATE / "conversation_pattern_catalog.json"
EVENT_TRIGGER_PROMISES_PATH = STATE / "event_trigger_promises.json"

RUNNING = True
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def handle_signal(_signum, _frame):
    global RUNNING
    RUNNING = False


def append_response_decision_log(decision_type: str, payload: dict) -> None:
    entry = {
        "timestamp": now_iso(),
        "decision_type": decision_type,
        **payload,
    }
    append_jsonl(RESPONSE_DECISION_LOG_PATH, entry)


def default_event_trigger_state() -> dict:
    return {
        "schema_version": 1,
        "managed_by": "automation_worker",
        "processed_offsets": {},
        "active_promises": [],
        "history": [],
        "last_updated_at": None,
        "notes": "사용자 요청으로 등록한 이벤트 기반 1회성 톡 발송 약속",
    }


def snapshot_message_offsets() -> dict:
    offsets = {}
    for path in sorted(MESSAGES.glob("*.jsonl")):
        line_count = 0
        with path.open("r", encoding="utf-8") as fp:
            for line_count, _ in enumerate(fp, start=1):
                pass
        offsets[path.name] = line_count
    return offsets


def load_event_trigger_state() -> dict:
    state = load_json(EVENT_TRIGGER_PROMISES_PATH, {})
    if not state:
        fresh = default_event_trigger_state()
        fresh["processed_offsets"] = snapshot_message_offsets()
        return fresh
    merged = default_event_trigger_state()
    merged.update(state)
    merged["processed_offsets"] = state.get("processed_offsets", {})
    merged["active_promises"] = state.get("active_promises", [])
    merged["history"] = state.get("history", [])
    return merged


def save_event_trigger_state(state: dict) -> None:
    state["last_updated_at"] = now_iso()
    save_json(EVENT_TRIGGER_PROMISES_PATH, state)


def log_event_trigger_update(update_type: str, content: str) -> None:
    event = {
        "timestamp": now_iso(),
        "direction": "system_action",
        "telegram_user": "K8832353",
        "type": update_type,
        "content": content,
    }
    log_path = MESSAGES / ("%s.jsonl" % now_local().strftime("%Y-%m-%d"))
    append_jsonl(log_path, event)


def create_event_trigger_promise(state: dict, command: dict) -> None:
    promise = {
        "id": "promise_%s_%d" % (command["event_key"], int(time.time())),
        "event_key": command["event_key"],
        "event_label": command.get("label"),
        "message": command["message"],
        "source_text": command["source_text"],
        "created_at": now_iso(),
        "status": "active",
        "last_matched_at": None,
        "sent_at": None,
    }
    state["active_promises"].append(promise)
    state["history"].append({"timestamp": now_iso(), "action": "create", "promise": promise})
    state["history"] = state["history"][-100:]
    log_event_trigger_update(
        "event_trigger_promise_created",
        "%s 이벤트 때 `%s` 발송 약속 등록" % (command.get("label") or command["event_key"], command["message"]),
    )


def cancel_event_trigger_promises(state: dict, command: dict) -> None:
    target_event_key = command.get("event_key")
    canceled = []
    for promise in reversed(state.get("active_promises", [])):
        if promise.get("status") != "active":
            continue
        if target_event_key and promise.get("event_key") != target_event_key:
            continue
        promise["status"] = "canceled"
        promise["canceled_at"] = now_iso()
        canceled.append(promise)
        if target_event_key:
            break
    if not canceled and not target_event_key:
        for promise in reversed(state.get("active_promises", [])):
            if promise.get("status") != "active":
                continue
            promise["status"] = "canceled"
            promise["canceled_at"] = now_iso()
            canceled.append(promise)
            break
    if canceled:
        state["history"].append(
            {
                "timestamp": now_iso(),
                "action": "cancel",
                "event_key": target_event_key,
                "promise_ids": [item.get("id") for item in canceled],
                "source_text": command.get("source_text"),
            }
        )
        state["history"] = state["history"][-100:]
        log_event_trigger_update(
            "event_trigger_promise_canceled",
            "이벤트 기반 발송 약속 %d건 취소" % len(canceled),
        )


def process_event_trigger_messages() -> None:
    state_missing = not EVENT_TRIGGER_PROMISES_PATH.exists()
    state = load_event_trigger_state()
    offsets = dict(state.get("processed_offsets", {}))
    dirty = False
    for path in sorted(MESSAGES.glob("*.jsonl")):
        last_line = int(offsets.get(path.name, 0))
        current_line = 0
        with path.open("r", encoding="utf-8") as fp:
            for current_line, raw_line in enumerate(fp, start=1):
                if current_line <= last_line:
                    continue
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if event.get("direction") != "incoming" or event.get("type") not in {"text", "command"}:
                    continue
                command = parse_event_trigger_command(event.get("content", ""))
                if not command:
                    continue
                if command["action"] == "create":
                    create_event_trigger_promise(state, command)
                    dirty = True
                elif command["action"] == "cancel":
                    before = json.dumps(state.get("active_promises", []), ensure_ascii=False)
                    cancel_event_trigger_promises(state, command)
                    after = json.dumps(state.get("active_promises", []), ensure_ascii=False)
                    dirty = dirty or before != after
        if current_line:
            offsets[path.name] = current_line
    if offsets != state.get("processed_offsets", {}):
        state["processed_offsets"] = offsets
        dirty = True
    if dirty or state_missing:
        save_event_trigger_state(state)


def maybe_fire_event_trigger_promises(previous_activity: Optional[str], current_activity: Optional[str], reason: str) -> None:
    if not previous_activity or previous_activity == current_activity:
        return
    if any(token in reason for token in ["bootstrap", "date_refresh", "manual_force_recalc"]):
        return
    state = load_event_trigger_state()
    event_keys = derive_event_keys_for_transition(previous_activity, current_activity)
    if not event_keys:
        return
    dirty = False
    for promise in state.get("active_promises", []):
        if promise.get("status") != "active":
            continue
        if promise.get("event_key") not in event_keys:
            continue
        message = normalize_fact_expression(promise.get("message", ""))
        if not message:
            continue
        if send_telegram_text(message):
            append_message_log("outgoing", "text", message)
            promise["status"] = "sent"
            promise["sent_at"] = now_iso()
            promise["last_matched_at"] = now_iso()
            promise["matched_activity"] = current_activity
            dirty = True
            log_event_trigger_update(
                "event_trigger_promise_sent",
                "%s 이벤트로 `%s` 발송" % (promise.get("event_label") or promise.get("event_key"), message),
            )
    if dirty:
        state["history"].append(
            {
                "timestamp": now_iso(),
                "action": "fire",
                "event_keys": event_keys,
                "current_activity": current_activity,
            }
        )
        state["history"] = state["history"][-100:]
        save_event_trigger_state(state)


def refresh_mood_timeline() -> None:
    state = load_json(MOOD_TIMELINE_PATH, {})
    today = now_local().strftime("%Y-%m-%d")
    if state.get("current_date") != today:
        state = {
            "schema_version": 1,
            "managed_by": "automation_worker",
            "current_date": today,
            "entries": [],
            "last_updated_at": None,
        }
    presence = load_json(PRESENCE_PATH, {})
    entries = list(state.get("entries", []))
    entry = {
        "timestamp": now_iso(),
        "activity": presence.get("current_activity"),
        "time_block": presence.get("current_time_block"),
        "surface_mood": presence.get("surface_mood"),
        "energy_level": presence.get("energy_level"),
        "affection_level": presence.get("affection_level"),
        "care_bias": presence.get("care_bias"),
        "reply_tempo": presence.get("reply_tempo"),
    }
    if not entries or entries[-1].get("activity") != entry["activity"] or entries[-1].get("surface_mood") != entry["surface_mood"]:
        entries.append(entry)
    state["entries"] = entries[-40:]
    state["last_updated_at"] = now_iso()
    save_json(MOOD_TIMELINE_PATH, state)


def bump_proactive_pattern(candidate_type: Optional[str], status: str, reason: str, delivery_channel: Optional[str], scenario_id: Optional[str]) -> None:
    state = load_json(PROACTIVE_PATTERN_REPORT_PATH, {})
    today = now_local().strftime("%Y-%m-%d")
    if state.get("current_date") != today:
        state = {
            "schema_version": 1,
            "managed_by": "automation_worker",
            "current_date": today,
            "planned_attempts": 0,
            "sudden_attempts": 0,
            "sent_text_count": 0,
            "sent_voice_count": 0,
            "suppressed_reasons": {},
            "time_window_counts": {},
            "last_updated_at": None,
        }
    if candidate_type == "planned_proactive":
        state["planned_attempts"] = int(state.get("planned_attempts", 0)) + 1
    elif candidate_type == "sudden_impulse":
        state["sudden_attempts"] = int(state.get("sudden_attempts", 0)) + 1
    if status == "sent":
        if delivery_channel == "voice":
            state["sent_voice_count"] = int(state.get("sent_voice_count", 0)) + 1
        else:
            state["sent_text_count"] = int(state.get("sent_text_count", 0)) + 1
    elif status.startswith("suppressed") or status in {"skipped_not_woongbbi_mode", "deferred"}:
        reasons = dict(state.get("suppressed_reasons", {}))
        reasons[status] = int(reasons.get(status, 0)) + 1
        state["suppressed_reasons"] = reasons
    if scenario_id:
        window_counts = dict(state.get("time_window_counts", {}))
        window_counts[scenario_id] = int(window_counts.get(scenario_id, 0)) + 1
        state["time_window_counts"] = window_counts
    state["last_updated_at"] = now_iso()
    save_json(PROACTIVE_PATTERN_REPORT_PATH, state)


def refresh_repetition_report() -> None:
    events = load_message_events(limit_files=7)
    now_dt = now_local()
    phrase_counts_3 = {}
    phrase_counts_7 = {}
    question_counts_3 = {}
    question_counts_7 = {}

    def normalize_for_pattern(text: str) -> str:
        normalized = re.sub(r"[ㅋㅎㅠ~]+", "", text)
        normalized = re.sub(r"[!?.,]+", " ", normalized)
        normalized = re.sub(r"아아+", "아", normalized)
        normalized = re.sub(r"어어+", "어", normalized)
        normalized = re.sub(r"오오+", "오", normalized)
        normalized = re.sub(r"이이+", "이", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    for event in events:
        if event.get("direction") != "outgoing" or event.get("type") != "text":
            continue
        text = normalize_for_pattern((event.get("content") or "").strip())
        if not text:
            continue
        try:
            age_days = (now_dt.date() - datetime.fromisoformat(event.get("timestamp")).date()).days
        except Exception:
            age_days = 0
        target_phrase_counts = phrase_counts_7
        target_question_counts = question_counts_7
        if age_days <= 2:
            target_phrase_counts = phrase_counts_3
            target_question_counts = question_counts_3
        target_phrase_counts[text] = target_phrase_counts.get(text, 0) + 1
        if "뭐 " in text or text.endswith("어") or text.endswith("지"):
            target_question_counts[text] = target_question_counts.get(text, 0) + 1
        phrase_counts_7[text] = phrase_counts_7.get(text, 0) + 1
        if "뭐 " in text or text.endswith("어") or text.endswith("지"):
            question_counts_7[text] = question_counts_7.get(text, 0) + 1
    guard = load_json(PHRASE_REPETITION_GUARD_PATH, {})
    report = {
        "schema_version": 1,
        "managed_by": "automation_worker",
        "window_3d": {
            "top_phrases": sorted(phrase_counts_3.items(), key=lambda item: (-item[1], item[0]))[:10],
            "top_questions": sorted(question_counts_3.items(), key=lambda item: (-item[1], item[0]))[:10],
        },
        "window_7d": {
            "top_phrases": sorted(phrase_counts_7.items(), key=lambda item: (-item[1], item[0]))[:15],
            "top_questions": sorted(question_counts_7.items(), key=lambda item: (-item[1], item[0]))[:15],
        },
        "blocked_phrases": guard.get("blocked_phrases", []),
        "last_updated_at": now_iso(),
    }
    save_json(REPETITION_REPORT_PATH, report)


def refresh_relationship_progress_notes() -> None:
    memory = load_json(MEMORY_DECAY_PATH, {})
    reinforcement = load_json(REINFORCEMENT_STATE_PATH, {})
    state = load_json(RELATIONSHIP_PROGRESS_NOTES_PATH, {})
    milestones = []
    for item in memory.get("long_term_memory", [])[:5]:
        milestones.append({
            "key": item.get("key"),
            "strength": item.get("strength"),
            "example": (item.get("recent_examples") or [None])[0],
        })
    state.update(
        {
            "schema_version": 1,
            "managed_by": "automation_worker",
            "milestones": milestones,
            "effective_patterns": reinforcement.get("bias_summary", {}).get("prefer", []),
            "comfort_patterns": [
                key for key in reinforcement.get("action_scores", {}).keys()
                if "comfort" in key or "warm" in key
            ],
            "affection_patterns": [
                key for key in reinforcement.get("topic_scores", {}).keys()
                if "affection" in key or "romance" in key
            ],
            "last_updated_at": now_iso(),
        }
    )
    save_json(RELATIONSHIP_PROGRESS_NOTES_PATH, state)


def refresh_chat_runtime_snapshot() -> None:
    mode = load_json(MODE_PATH, {}).get("current_mode", "setting")
    presence = load_json(PRESENCE_PATH, {})
    variance = load_json(REPLY_VARIANCE_PATH, {})
    guard_state = compute_conversation_guard()
    memory = load_json(MEMORY_DECAY_PATH, {})
    image_settings = load_json(IMAGE_SETTINGS_PATH, {})
    image_guard = load_json(IMAGE_GUARD_PATH, {})
    voice_ctx = load_json(VOICE_SHARE_CONTEXT_PATH, {})
    media_ctx = load_json(MEDIA_PATH, {})
    blocked = load_json(PHRASE_REPETITION_GUARD_PATH, {}).get("blocked_phrases", [])
    conversation_pattern = load_json(CONVERSATION_PATTERN_STATE_PATH, {})
    conversation_catalog = load_json(CONVERSATION_PATTERN_CATALOG_PATH, {})

    available_voice = mode == "woongbbi" and not guard_state.get("waiting_reply") and not guard_state.get("outgoing_cooldown")
    last_voice_at = voice_ctx.get("runtime", {}).get("last_voice_sent_at")
    if last_voice_at:
        try:
            cooldown = int(voice_ctx.get("cooldowns", {}).get("proactive_voice_minutes", 15))
            if (now_local() - datetime.fromisoformat(last_voice_at)).total_seconds() <= cooldown * 60:
                available_voice = False
        except Exception:
            pass

    available_image = bool(image_settings.get("generation_enabled")) and not bool(image_guard.get("active"))
    available_link = bool(media_ctx.get("last_known_url"))
    top_memory_keys = [item.get("key") for item in memory.get("long_term_memory", [])[:3] if item.get("key")]
    scene = summarize_current_scene()
    active_event_promises = [
        {
            "event_key": item.get("event_key"),
            "event_label": item.get("event_label"),
            "message": item.get("message"),
        }
        for item in load_event_trigger_state().get("active_promises", [])
        if item.get("status") == "active"
    ]

    recommended_path = "full"
    recommended_reason = "setting_mode_default_full" if mode != "woongbbi" else "woongbbi_full_preferred_for_richer_expression"
    recipe_key = None
    if mode == "woongbbi":
        activity = presence.get("current_activity") or ""
        if activity in {"waking_up", "getting_ready", "commuting_to_work", "hospital_morning_shift"}:
            recipe_key = "morning_busy_checkin"
        elif activity in {"lunch_break", "midday_cafe", "midday_reset"}:
            recipe_key = "midday_soft_ping"
        elif activity in {"commuting_home", "post_work_dinner", "post_shift_decompress"}:
            recipe_key = "after_work_comfort"
        elif activity in {"night_wind_down", "lying_in_bed", "home_late_evening"}:
            recipe_key = "night_wind_down"
    suggested_recipe = (conversation_catalog.get("situation_recipes") or {}).get(recipe_key, {})
    blocked_categories = set(conversation_pattern.get("blocked_question_intents", [])) | set(
        conversation_pattern.get("blocked_opening_styles", [])
    )
    suggested_style_pools = build_suggested_style_pools(conversation_catalog, suggested_recipe, blocked_categories)
    length_guidance = build_length_guidance(conversation_catalog, recipe_key, suggested_recipe, guard_state)

    snapshot = {
        "schema_version": 1,
        "managed_by": "automation_worker",
        "current_mode": mode,
        "current_activity": presence.get("current_activity"),
        "current_time_block": presence.get("current_time_block"),
        "surface_mood": presence.get("surface_mood"),
        "energy_level": presence.get("energy_level"),
        "affection_level": presence.get("affection_level"),
        "care_bias": presence.get("care_bias"),
        "reply_variance_profile": variance.get("current_profile"),
        "blocked_phrases": blocked,
        "blocked_question_intents": conversation_pattern.get("blocked_question_intents", []),
        "blocked_opening_styles": conversation_pattern.get("blocked_opening_styles", []),
        "preferred_next_moves": conversation_pattern.get("preferred_next_moves", []),
        "conversation_guard_summary": {
            "conversation_active": guard_state.get("conversation_active"),
            "waiting_reply": guard_state.get("waiting_reply"),
            "outgoing_cooldown": guard_state.get("outgoing_cooldown"),
            "late_reply_ok": guard_state.get("late_reply_ok"),
        },
        "conversation_pattern_summary": {
            "recent_question_intents": conversation_pattern.get("recent_question_intents", []),
            "recent_opening_styles": conversation_pattern.get("recent_opening_styles", []),
        },
        "suggested_conversation_recipe": {
            "key": recipe_key,
            "when": suggested_recipe.get("when"),
            "shape": suggested_recipe.get("shape", []),
            "avoid_if_blocked": suggested_recipe.get("avoid_if_blocked", []),
        },
        "suggested_length_guidance": length_guidance,
        "suggested_style_pools": suggested_style_pools,
        "conversation_dataset_summary": conversation_catalog.get("dataset_summary", {}),
        "top_memory_keys": top_memory_keys,
        "current_context_summary": scene.get("context_summary"),
        "current_ambient_summary": scene.get("ambient_summary"),
        "weather_summary": scene.get("weather_summary"),
        "appearance_summary": scene.get("appearance_summary"),
        "current_fact_status": factual_status_for_activity(presence.get("current_activity")),
        "event_fact_language_rule": "상황이 이미 확정된 상태면 느낌/흐름/같아 대신 도착했어, 누웠어, 일어났어처럼 사실형으로 말한다.",
        "active_event_trigger_promises": active_event_promises,
        "available_rich_channels": {
            "text": True,
            "image": available_image,
            "voice": available_voice,
            "link": available_link,
        },
        "recommended_response_path": recommended_path,
        "recommended_response_reason": recommended_reason,
        "last_updated_at": now_iso(),
    }
    save_json(CHAT_RUNTIME_SNAPSHOT_PATH, snapshot)


def recent_outgoing_rich_share(minutes: int = 5) -> bool:
    now_dt = now_local()
    for event in reversed(load_message_events(limit_files=2)):
        event_type = event.get("type")
        direction = event.get("direction")
        if direction != "outgoing" and event_type != "voice_message_skill_send":
            continue
        if direction == "outgoing" and event_type not in {"image", "voice_message", "voice", "text"}:
            continue
        if event_type == "text":
            content = event.get("content", "")
            if not any(token in content for token in ["http://", "https://", "youtu", "릴스", "쇼츠"]):
                continue
        try:
            event_dt = datetime.fromisoformat(event.get("timestamp"))
        except Exception:
            continue
        if (now_dt - event_dt).total_seconds() <= minutes * 60:
            return True
        break
    return False


def run_reinforcement_engine() -> None:
    engine = ROOT / "tools" / "reinforcement_engine.py"
    if not engine.exists():
        append_worker_note("reinforcement_engine_missing")
        return
    result = subprocess.run(
        ["python3", str(engine)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 0:
        append_worker_note("reinforcement_engine_ok")
    else:
        append_worker_note("reinforcement_engine_error %s" % (result.stderr.strip() or result.stdout.strip()))


def current_day_name(now_dt: datetime) -> str:
    return DAY_NAMES[now_dt.weekday()]


def is_timer_due(timer: dict, now_dt: datetime, history: dict) -> bool:
    if not timer.get("enabled", True):
        return False
    if timer.get("type") == "periodic_tick":
        last_fired = history.get(timer["id"])
        if not last_fired:
            return True
        try:
            last_dt = datetime.fromisoformat(last_fired)
        except ValueError:
            return True
        interval = int(timer.get("interval_seconds", 60))
        return (now_dt - last_dt).total_seconds() >= interval
    if current_day_name(now_dt) not in timer.get("days", []):
        return False
    scheduled = timer.get("time")
    if not scheduled:
        return False
    if now_dt.strftime("%H:%M") != scheduled:
        return False
    last_fired = history.get(timer["id"])
    return not (last_fired and last_fired.startswith(now_dt.strftime("%Y-%m-%d")))


def deterministic_pick(items: list, seed_text: str) -> Optional[dict]:
    if not items:
        return None
    rng = random.Random(seed_text)
    return items[rng.randrange(0, len(items))]


def choose_signature_phrase(mode: str, mood: str, text: str) -> str:
    phrases = load_json(SIGNATURE_PHRASES_PATH, {})
    pools = phrases.get("pools", {})
    runtime = phrases.get("runtime", {})
    last_key = runtime.get("last_phrase_key")
    candidates = []
    if mode == "suffix":
        candidates.extend(pools.get("soft_suffix", []))
        if mood in {"cozy_and_open", "sleepy_soft", "homey_and_soft", "rain_softened"}:
            candidates.extend(pools.get("cozy_suffix", []))
        if mood in {"light_playful", "quietly_chatty", "open_and_curious"}:
            candidates.extend(pools.get("playful_suffix", []))
    elif mode == "interjection":
        candidates.extend(pools.get("small_interjections", []))
    if not candidates:
        return text
    rng = random.Random("%s:%s:%s" % (now_local().strftime("%Y-%m-%d"), mood, text))
    choice = candidates[rng.randrange(0, len(candidates))]
    if choice.get("key") == last_key and len(candidates) > 1:
        choice = candidates[(rng.randrange(0, len(candidates) - 1) + 1) % len(candidates)]
    runtime["last_phrase_key"] = choice.get("key")
    runtime["last_used_at"] = now_iso()
    phrases["runtime"] = runtime
    save_json(SIGNATURE_PHRASES_PATH, phrases)
    phrase = choice.get("text", "")
    if mode == "suffix":
        return "%s %s" % (text.rstrip(), phrase.strip())
    return "%s %s" % (phrase.strip(), text.lstrip())


def apply_signature_style(text: str) -> str:
    presence = load_json(PRESENCE_PATH, {})
    mood = presence.get("surface_mood", "cozy_and_open")
    styled = text
    if random.Random("%s:%s" % (now_local().strftime("%Y-%m-%d"), text)).random() < 0.55:
        styled = choose_signature_phrase("suffix", mood, styled)
    if mood in {"sleepy_soft", "rain_softened"} and random.Random("lead:%s" % text).random() < 0.22:
        styled = choose_signature_phrase("interjection", mood, styled)
    return styled.strip()


def refresh_reply_variance_state() -> None:
    presence = load_json(PRESENCE_PATH, {})
    state = load_json(REPLY_VARIANCE_PATH, {})
    mood = presence.get("surface_mood", "cozy_and_open")
    bandwidth = presence.get("social_bandwidth", "open")
    tempo = presence.get("reply_tempo", "comfortable")
    profile = "balanced"
    target_sentences = [2, 3]
    punctuation = "soft"
    if bandwidth in {"fragmented", "limited"} or mood in {"slightly_drained", "lightly_rushed", "busy_but_caring"}:
        profile = "brief"
        target_sentences = [1, 2]
        punctuation = "minimal"
    elif mood in {"cozy_and_open", "light_playful", "homey_and_soft"} and tempo == "comfortable":
        profile = "expanded"
        target_sentences = [2, 4]
        punctuation = "warm"
    elif mood == "sleepy_soft":
        profile = "sleepy_short"
        target_sentences = [1, 2]
        punctuation = "trailing"
    state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "current_date": now_local().strftime("%Y-%m-%d"),
            "current_profile": profile,
            "target_sentence_range": target_sentences,
            "punctuation_style": punctuation,
            "last_updated_at": now_iso(),
        }
    )
    save_json(REPLY_VARIANCE_PATH, state)


def refresh_taste_friction_state() -> None:
    state = load_json(TASTE_FRICTION_PATH, {})
    state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "last_updated_at": now_iso(),
            "soft_dislikes": [
                "너무 단 디저트는 몇 입 먹으면 금방 물린다",
                "사람이 너무 많은 카페는 금방 피곤해진다",
                "출근길 비는 감성보다 먼저 번거롭게 느껴진다",
                "하루가 너무 지쳤을 땐 긴 콘텐츠보다 짧은 영상으로 흐르기 쉽다"
            ],
            "mild_contradictions": [
                "운동 가기 전엔 늘 조금 귀찮아하지만 다녀오면 개운해한다",
                "집밥을 좋아하지만 피곤한 날은 간단히 때우고 싶어한다",
                "비 오는 날 분위기는 좋아하지만 머리 망가지는 건 싫어한다"
            ],
        }
    )
    save_json(TASTE_FRICTION_PATH, state)


def refresh_day_satisfaction_state() -> None:
    presence = load_json(PRESENCE_PATH, {})
    day_context = load_json(DAY_CONTEXT_PATH, {})
    memory = load_json(MEMORY_DECAY_PATH, {})
    energy = int(presence.get("energy_level", 50))
    affection = int(presence.get("affection_level", 80))
    selected_events = day_context.get("selected_events", [])
    positive_event_bonus = sum(1 for event in selected_events if event.get("tone") in {"positive", "romantic", "soft"})
    tiring_penalty = sum(1 for event in selected_events if event.get("tone") in {"slightly_tiring"})
    score = 50 + positive_event_bonus * 8 - tiring_penalty * 5 + max(-10, min(10, affection - 80)) + max(-12, min(12, energy - 50))
    if memory.get("long_term_memory"):
        top_key = memory["long_term_memory"][0].get("key")
        if top_key in {"warm_comfort", "romantic_closeness", "photo_affection"}:
            score += 5
    label = "neutral_day"
    if score >= 72:
        label = "good_day"
    elif score <= 42:
        label = "drained_day"
    state = load_json(DAY_SATISFACTION_PATH, {})
    state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "current_date": now_local().strftime("%Y-%m-%d"),
            "score": int(max(0, min(100, score))),
            "label": label,
            "last_updated_at": now_iso(),
        }
    )
    save_json(DAY_SATISFACTION_PATH, state)


def refresh_phrase_repetition_guard() -> None:
    events = load_message_events(limit_files=3)
    recent_outgoing = [event.get("content", "") for event in events if event.get("direction") == "outgoing" and event.get("type") == "text"]
    tracked_phrases = ["있었지", "그러니까아", "몽글", "말랑", "헤헤", "진짜아", "오빠는 지금 뭐 하고 있었어?"]
    counts = {phrase: 0 for phrase in tracked_phrases}
    for text in recent_outgoing[-20:]:
        for phrase in tracked_phrases:
            if phrase in text:
                counts[phrase] += 1
    state = load_json(PHRASE_REPETITION_GUARD_PATH, {})
    blocked = [phrase for phrase, count in counts.items() if count >= 2]
    state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "last_updated_at": now_iso(),
            "recent_phrase_counts": counts,
            "blocked_phrases": blocked,
        }
    )
    save_json(PHRASE_REPETITION_GUARD_PATH, state)


def classify_question_intent(text: str) -> Optional[str]:
    lowered = text.strip()
    if not lowered:
        return None
    intent_rules = [
        ("current_state_check", ["지금 뭐", "뭐하고", "뭐 해", "어디쯤", "어디야", "뭐했", "뭐하고 있었"]),
        ("meal_routine", ["밥", "점심", "저녁", "먹었어", "챙겨먹", "커피"]),
        ("emotion_check", ["힘들", "지쳤", "기분 어때", "괜찮아", "피곤", "오늘 어땠"]),
        ("commute_arrival", ["도착했", "가는 중", "언제쯤", "들어가", "퇴근길", "집 가는 길"]),
        ("photo_request", ["사진", "보여주", "찍어줘", "지금 모습", "보고싶어", "보고 싶어"]),
        ("appearance_imagination", ["어떻게 입", "누워", "상상", "옆에", "같이 있었으면"]),
        ("future_plan", ["이따", "나중에", "주말", "계획", "할거야", "하고싶어"]),
    ]
    for intent, needles in intent_rules:
        if any(needle in lowered for needle in needles):
            return intent
    return None


def classify_opening_style(text: str) -> Optional[str]:
    lowered = text.strip()
    if not lowered:
        return None
    opening_rules = [
        ("self_update", ["나 지금", "방금", "나는 지금", "나 이제", "지금은 나는"]),
        ("thought_of_you", ["오빠 생각", "문득", "갑자기 생각", "갑자기 보고싶", "갑자기 궁금"]),
        ("time_checkin", ["잘잤어", "출근", "점심", "퇴근", "저녁", "아직 가는중"]),
        ("weather_or_scene", ["오늘 공기", "비 오", "깜깜하네", "밤공기", "날씨"]),
        ("playful_tease", ["모야", "ㅋㅋ", "반칙", "왜케", "또 그러네"]),
    ]
    for style, needles in opening_rules:
        if any(needle in lowered for needle in needles):
            return style
    return None


def dedupe_keep_order(values: list) -> list:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def preferred_moves_from_blocks(blocked_question_intents: list, blocked_opening_styles: list) -> list:
    move_map = {
        "current_state_check": ["self_update", "soft_observation", "micro_topic_shift"],
        "meal_routine": ["self_update", "care_offer", "micro_topic_shift"],
        "emotion_check": ["soft_observation", "care_offer", "shared_image"],
        "commute_arrival": ["soft_observation", "self_update", "care_offer"],
        "photo_request": ["soft_observation", "shared_image", "playful_nudge"],
        "appearance_imagination": ["self_update", "shared_image", "playful_nudge"],
        "future_plan": ["self_update", "shared_image", "soft_observation"],
    }
    opening_map = {
        "self_update": ["soft_observation", "care_offer"],
        "thought_of_you": ["self_update", "weather_or_scene", "time_checkin"],
        "time_checkin": ["self_update", "thought_of_you", "weather_or_scene"],
        "weather_or_scene": ["thought_of_you", "self_update"],
        "playful_tease": ["soft_observation", "self_update"],
    }
    moves = []
    for intent in blocked_question_intents:
        moves.extend(move_map.get(intent, []))
    for style in blocked_opening_styles:
        moves.extend(opening_map.get(style, []))
    if not moves:
        moves = ["self_update", "soft_observation", "care_offer", "playful_nudge"]
    return dedupe_keep_order(moves)[:5]


def is_romantic_runtime_text(text: str) -> bool:
    lowered = (text or "").strip()
    if len(lowered) < 6 or len(lowered) > 140:
        return False
    blocked_needles = [
        "마스터",
        "/Users/",
        ".json",
        ".jsonl",
        ".md",
        "세팅모드",
        "설정파일",
        "폴더",
        "파일",
        "캘린더",
        "이미지 생성",
        "프로세스",
        "타이머",
        "시간대별",
        "생활 패턴",
        "설정",
        "대답할때 참조",
        "채팅은 할 수",
        "트리거",
        "기능 구성",
        "/웅삐온",
        "/설정온",
        "/세팅온",
    ]
    return not any(needle in lowered for needle in blocked_needles)


def build_suggested_style_pools(conversation_catalog: dict, recipe: dict, blocked_categories: set) -> dict:
    blueprints = conversation_catalog.get("move_blueprints") or {}
    pools = {}
    for move in recipe.get("shape", []) or []:
        blueprint = blueprints.get(move) or {}
        categories = [
            category for category in blueprint.get("categories", [])
            if category not in blocked_categories
        ]
        if not categories:
            continue
        deduped = dedupe_keep_order(blueprint.get("examples", []))[:5]
        if deduped:
            pools[move] = deduped
    return pools


def build_length_guidance(conversation_catalog: dict, recipe_key: Optional[str], suggested_recipe: dict, guard_state: dict) -> dict:
    recipe_profiles = conversation_catalog.get("recipe_length_profiles") or {}
    global_profile = (conversation_catalog.get("global_length_profile") or {}).get("woongbbi_outgoing", {})
    recipe_profile = recipe_profiles.get(recipe_key) or {}
    recommended_chars = recipe_profile.get("recommended_char_range") or [
        max(12, int(global_profile.get("char_p50", 28)) - 8),
        max(28, int(global_profile.get("char_p75", 52)) + 8),
    ]
    recommended_sentences = recipe_profile.get("recommended_sentence_range") or [1, 2]
    max_questions = 0 if guard_state.get("waiting_reply") else 1
    if "current_state_check" not in (suggested_recipe.get("avoid_if_blocked") or []):
        max_questions = min(1, max_questions + 1)
    return {
        "recommended_char_range": recommended_chars,
        "recommended_sentence_range": recommended_sentences,
        "max_question_count": max_questions,
        "question_density_hint": recipe_profile.get("question_density_hint") or "질문은 많아도 1개",
        "reply_length_mode": "brief" if recommended_chars[1] <= 45 else "medium",
    }


def refresh_conversation_pattern_state() -> None:
    events = load_message_events(limit_files=3)
    outgoing = [
        (event.get("content", "") or "").strip()
        for event in events
        if event.get("direction") == "outgoing" and event.get("type") == "text" and is_romantic_runtime_text(event.get("content", ""))
    ]
    recent = outgoing[-12:]
    recent_question_intents = []
    recent_opening_styles = []
    question_counts = {}
    opening_counts = {}

    for text in recent:
        question_intent = classify_question_intent(text)
        opening_style = classify_opening_style(text)
        if question_intent:
            recent_question_intents.append(question_intent)
            question_counts[question_intent] = question_counts.get(question_intent, 0) + 1
        if opening_style:
            recent_opening_styles.append(opening_style)
            opening_counts[opening_style] = opening_counts.get(opening_style, 0) + 1

    blocked_question_intents = [
        intent for intent, count in question_counts.items()
        if count >= 2 and intent in recent_question_intents[-5:]
    ]
    blocked_opening_styles = [
        style for style, count in opening_counts.items()
        if count >= 2 and style in recent_opening_styles[-4:]
    ]
    state = load_json(CONVERSATION_PATTERN_STATE_PATH, {})
    state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "recent_question_intents": recent_question_intents[-6:],
            "recent_opening_styles": recent_opening_styles[-6:],
            "question_intent_counts": question_counts,
            "opening_style_counts": opening_counts,
            "blocked_question_intents": blocked_question_intents,
            "blocked_opening_styles": blocked_opening_styles,
            "preferred_next_moves": preferred_moves_from_blocks(blocked_question_intents, blocked_opening_styles),
            "last_updated_at": now_iso(),
            "notes": "최근 outgoing 답장에서 같은 질문 줄기와 같은 선톡 시작 패턴이 겹치면 잠시 피하게 만드는 상태",
        }
    )
    save_json(CONVERSATION_PATTERN_STATE_PATH, state)


def apply_repetition_guard(text: str) -> str:
    guard = load_json(PHRASE_REPETITION_GUARD_PATH, {})
    blocked = set(guard.get("blocked_phrases", []))
    replacements = {
        "있었지": "그랬네",
        "그러니까아": "그러네",
        "몽글": "말랑",
        "말랑": "포근",
        "헤헤": "ㅎㅎ",
        "진짜아": "진짜",
        "오빠는 지금 뭐 하고 있었어?": "오빠는 지금 뭐 하고 있어?"
    }
    guarded = text
    for source, target in replacements.items():
        if source in blocked:
            guarded = guarded.replace(source, target)
    return guarded


def apply_reply_variance(text: str) -> str:
    variance = load_json(REPLY_VARIANCE_PATH, {})
    profile = variance.get("current_profile", "balanced")
    result = text.strip()
    if profile == "brief":
        result = result.replace(" 그러니까아", "").replace(" 있었지", "")
        parts = [part.strip() for part in result.split(".") if part.strip()]
        if len(parts) > 2:
            result = ". ".join(parts[:2]) + "."
    elif profile == "sleepy_short":
        result = result.replace("ㅋㅋ", "ㅎㅎ")
        if not result.endswith(".."):
            result = result.rstrip(".") + ".."
    elif profile == "expanded":
        if result.endswith("?"):
            result = result[:-1] + " ㅎㅎ?"
    return result.strip()


def rotate_pick(options: list, seed_text: str, last_value: Optional[str] = None) -> Optional[str]:
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    rng = random.Random(seed_text)
    start = rng.randrange(0, len(options))
    ordered = options[start:] + options[:start]
    for item in ordered:
        if item != last_value:
            return item
    return ordered[0]


def rotate_pick_recent(options: list, seed_text: str, recent_values: list) -> Optional[str]:
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    recent = [value for value in recent_values if value]
    rng = random.Random(seed_text)
    start = rng.randrange(0, len(options))
    ordered = options[start:] + options[:start]
    for item in ordered:
        if item not in recent:
            return item
    for item in ordered:
        if item != recent[0] if recent else True:
            return item
    return ordered[0]


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


def build_image_prompt_plan(reason: str) -> dict:
    presence = load_json(PRESENCE_PATH, {})
    appearance = load_json(APPEARANCE_PATH, {})
    weather = load_json(WEATHER_PATH, {})
    continuity = load_json(STATE / "image_continuity_state.json", {})
    last_plan = load_json(IMAGE_PROMPT_PLAN_PATH, {})
    recent_plans = load_recent_image_plans()

    activity = presence.get("current_activity", "")
    block = presence.get("current_time_block", "")
    mood = presence.get("surface_mood", "")
    appearance_branch = appearance.get("appearance_branch", "")
    outfit_context = appearance.get("outfit_context", "")
    top = appearance.get("top")
    weather_summary = weather.get("summary")
    continuity_band = continuity.get("continuity_band", "none")
    context_summary = summarize_current_scene().get("context_summary", "")

    image_type = "soft_selfie_encouragement"
    shot_pool = ["chest_up"]
    angle_pool = ["front_phone_selfie"]
    expression_pool = ["soft_smile"]
    pose_pool = ["phone_in_hand_relaxed"]
    framing_pool = ["subject_centered"]
    capture_method_pool = ["front_camera_handheld"]
    space_anchor_pool = ["neutral_personal_space"]
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
        scene_focus = "home_relaxed_mood"
    elif activity in {"hospital_morning_shift", "hospital_afternoon_shift", "commuting_to_work", "commuting_home"} or "hospital" in outfit_context:
        image_type = "workday_candid_selfie"
        shot_pool = ["chest_up", "half_body", "mirror_quick_check", "waist_up"]
        angle_pool = ["front_phone_selfie", "three_quarter_arm_length", "slight_high_angle", "mirror_half_body"]
        expression_pool = ["bright_smile", "tired_but_cute", "closed_lip_smile", "focused_soft"]
        pose_pool = ["bag_strap_hold", "coffee_in_hand", "walking_glance", "hair_adjust"]
        framing_pool = ["subject_centered", "station_or_hallway_context", "window_reflection_mix", "torso_and_outfit_bias"]
        if activity in {"hospital_morning_shift", "hospital_afternoon_shift"}:
            capture_method_pool = ["mirror_selfie", "front_camera_handheld"]
            space_anchor_pool = ["staff_restroom_mirror", "locker_room_mirror", "quiet_hallway"]
        else:
            capture_method_pool = ["front_camera_handheld", "front_camera_handheld", "propped_phone_timer"]
            space_anchor_pool = ["street_walk", "station_platform", "cafe_table"]
        scene_focus = "workday_transition"
    elif activity in {"exercise_or_cafe"}:
        image_type = "cafe_or_activity_lifestyle"
        shot_pool = ["table_portrait", "half_body_seated", "drink_and_face_combo", "waist_up"]
        angle_pool = ["seated_three_quarter", "low_table_angle", "front_phone_selfie", "overhead_phone_snap"]
        expression_pool = ["warm_smile", "playful_grin", "thinking_soft", "eyes_down_small_smile"]
        pose_pool = ["cup_near_face", "chin_rest", "walking_mid_step", "one_hand_in_hair"]
        framing_pool = ["table_items_in_frame", "window_light_side", "environment_balanced", "subject_right_weighted"]
        capture_method_pool = ["front_camera_handheld", "propped_phone_timer", "mirror_selfie"]
        space_anchor_pool = ["cafe_table", "window_seat", "cafe_restroom_mirror"]
        scene_focus = "lifestyle_space"
    elif activity in {"dinner_or_cooking"} or "home" in outfit_context:
        image_type = "home_lifestyle_soft"
        shot_pool = ["waist_up", "half_body", "table_seated", "detail_plus_portrait"]
        angle_pool = ["kitchen_counter_angle", "seated_eye_level", "three_quarter_home_snap", "side_profile_home"]
        expression_pool = ["gentle_smile", "content_relaxed", "fond_eye_contact", "small_laugh"]
        pose_pool = ["holding_mug", "resting_on_table", "looking_back_over_shoulder", "phone_in_mirror"]
        framing_pool = ["table_or_mug_in_frame", "soft_room_context", "subject_centered", "home_detail_balance"]
        capture_method_pool = ["front_camera_handheld", "mirror_selfie", "propped_phone_timer"]
        space_anchor_pool = ["kitchen_counter", "dining_table", "vanity_mirror"]
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
        scene_focus = "weather_mood"

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

    shot_type = rotate_pick_recent(shot_pool, seed_base + ":shot", recent_shots[:3])
    camera_angle = rotate_pick_recent(angle_pool, seed_base + ":angle", recent_angles[:3])
    expression = rotate_pick_recent(expression_pool, seed_base + ":expression", recent_expressions[:2])
    pose = rotate_pick_recent(pose_pool, seed_base + ":pose", recent_poses[:3])
    framing = rotate_pick_recent(framing_pool, seed_base + ":framing", recent_framings[:3])
    selfie_capture_method = rotate_pick_recent(capture_method_pool, seed_base + ":method", recent_methods[:3])
    space_anchor = rotate_pick_recent(space_anchor_pool, seed_base + ":space", recent_spaces[:3])

    recent_combos = {
        (
            item.get("shot_type"),
            item.get("camera_angle"),
            item.get("framing"),
            item.get("selfie_capture_method"),
            item.get("space_anchor"),
        )
        for item in recent_plans[:4]
    }
    for attempt in range(6):
        combo = (shot_type, camera_angle, framing, selfie_capture_method, space_anchor)
        if combo not in recent_combos:
            break
        shot_type = rotate_pick_recent(shot_pool, seed_base + ":shot:%d" % attempt, recent_shots[:2])
        camera_angle = rotate_pick_recent(angle_pool, seed_base + ":angle:%d" % attempt, recent_angles[:2])
        framing = rotate_pick_recent(framing_pool, seed_base + ":framing:%d" % attempt, recent_framings[:2])
        selfie_capture_method = rotate_pick_recent(capture_method_pool, seed_base + ":method:%d" % attempt, recent_methods[:2])
        space_anchor = rotate_pick_recent(space_anchor_pool, seed_base + ":space:%d" % attempt, recent_spaces[:2])

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
    if weather_summary:
        composition_rules.append("날씨 기운: %s" % weather_summary)
    if top:
        composition_rules.append("복장 포인트: %s" % top)
    composition_rules.append("셀피 방식: %s" % selfie_capture_method)
    composition_rules.append("공간 앵커: %s" % space_anchor)
    composition_rules.append(selfie_authenticity)

    prompt_fragments = [
        "이미지 타입: %s" % image_type,
        "샷 타입: %s" % shot_type,
        "카메라 각도: %s" % camera_angle,
        "셀피 촬영 방식: %s" % selfie_capture_method,
        "카메라 노출 방식: %s" % camera_visibility,
        "표정: %s" % expression,
        "포즈: %s" % pose,
        "프레이밍: %s" % framing,
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
        "pose": pose,
        "framing": framing,
        "crop_bias": crop_bias,
        "space_anchor": space_anchor,
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
            "%s|%s|%s|%s|%s"
            % (
                item.get("shot_type"),
                item.get("camera_angle"),
                item.get("framing"),
                item.get("selfie_capture_method"),
                item.get("space_anchor"),
            )
            for item in recent_plans[:4]
        ],
        "notes": "다음 이미지 생성 시 셀피/라이프스타일 샷 구도 반복을 줄이기 위한 샷 플랜",
    }
    save_json(IMAGE_PROMPT_PLAN_PATH, plan)
    save_recent_image_plan(plan)
    return plan


def summarize_current_scene() -> dict:
    presence = load_json(PRESENCE_PATH, {})
    day_context = load_json(DAY_CONTEXT_PATH, {})
    weather = load_json(WEATHER_PATH, {})
    appearance = load_json(APPEARANCE_PATH, {})
    activity = presence.get("current_activity", "")
    context_map = {
        "waking_up": "morning_context",
        "getting_ready": "morning_context",
        "commuting_to_work": "morning_context",
        "hospital_morning_shift": "morning_context",
        "lunch_break": "lunch_context",
        "hospital_afternoon_shift": "after_work_context",
        "commuting_home": "after_work_context",
        "dinner_or_cooking": "evening_context",
        "exercise_or_cafe": "evening_context",
        "night_wind_down": "night_context",
        "sleep_window": "night_context",
    }
    ctx_key = context_map.get(activity)
    context_summary = day_context.get(ctx_key, {}).get("summary") if ctx_key else None
    ambient_summary = None
    for event in day_context.get("selected_events", []):
        if event.get("tone") == "ambient" and event.get("summary"):
            ambient_summary = event.get("summary")
            break
    appearance_summary = None
    top = appearance.get("top")
    hair = appearance.get("hair_state")
    if top or hair:
        appearance_summary = ", ".join(
            fragment for fragment in [top, str(hair).replace("_", " ") if hair else None] if fragment
        )
    return {
        "activity": activity,
        "time_block": presence.get("current_time_block"),
        "context_summary": context_summary,
        "ambient_summary": ambient_summary,
        "weather_summary": weather.get("summary"),
        "appearance_summary": appearance_summary,
    }


def build_contextual_proactive_message(selected: dict) -> str:
    scene = summarize_current_scene()
    activity = scene.get("activity")
    summary = scene.get("context_summary")
    weather = scene.get("weather_summary")
    fallback = selected.get("message", "")
    hour = now_local().hour

    if activity in {"waking_up", "getting_ready", "commuting_to_work"} or (5 <= hour < 8):
        if summary and "정신없" in summary:
            return normalize_fact_expression("아직 안 일어났나 해서 먼저 톡해봤어. 오늘 아침은 좀 정신없을까?")
        return normalize_fact_expression("아직 안 일어났나 궁금해서 먼저 톡했어. 잘 잤어?")

    if activity == "hospital_morning_shift":
        return normalize_fact_expression("오전부터 일 시작했는데 오빠는 아침 잘 보냈는지 궁금해서 톡했어.")
    if activity == "lunch_break":
        if summary and "메뉴" in summary:
            return normalize_fact_expression("점심 먹으면서 오빠 생각났어. 밥은 챙겨 먹었어?")
        return normalize_fact_expression("점심 잠깐 먹으러 나왔는데 오빠는 밥 챙겼는지 궁금해서 톡했어.")
    if activity == "hospital_afternoon_shift":
        return normalize_fact_expression("오후에도 일하고 있는데 오빠는 지금 뭐 하고 있을까 싶어서 톡했어.")
    if activity == "commuting_to_work":
        return normalize_fact_expression("출근길인데 오빠도 이제 슬슬 하루 시작했나 궁금해서 톡했어.")
    if activity == "commuting_home":
        return normalize_fact_expression("이제 퇴근길 올라왔어. 오빠는 지금 뭐 하구 있어?")
    if activity == "dinner_or_cooking":
        return normalize_fact_expression("이제 집 와서 저녁 챙기려는데 괜히 오빠 생각나서 먼저 톡했어.")
    if activity == "exercise_or_cafe":
        return normalize_fact_expression("지금 카페나 운동 가기 전인데 분위기가 좀 괜찮아서 오빠 생각났어.")
    if activity in {"night_wind_down", "sleep_window"}:
        if hour >= 23 or hour < 1:
            return normalize_fact_expression("이 시간엔 이미 자나 궁금해져서 톡했어.")
        return normalize_fact_expression("이제 좀 쉬고 있는데 괜히 오빠 생각나서 톡했어.")
    if weather and "비" in weather:
        return normalize_fact_expression("날씨가 좀 차분해서 괜히 오빠 생각이 더 나네.")
    return normalize_fact_expression(fallback)


def build_waiting_reply_followup(reason: str, minutes_since_last_outgoing: Optional[float] = None) -> dict:
    scene = summarize_current_scene()
    activity = scene.get("activity")
    summary = scene.get("context_summary")
    minutes_waited = float(minutes_since_last_outgoing or 0.0)
    hour = now_local().hour

    if minutes_waited >= 90:
        wait_mood = "long"
    elif minutes_waited >= 30:
        wait_mood = "pouty"
    elif minutes_waited >= 10:
        wait_mood = "clingy"
    else:
        wait_mood = "soft_nudge"

    if reason == "scheduled":
        if activity == "commuting_home":
            if wait_mood == "long":
                message = "오빠 연락 없이 한참이네에. 나 좀 기다렸는데도 못 참고 또 톡했어. 지금 퇴근길 올라왔거든."
            elif wait_mood == "pouty":
                message = "오빠 답 아직 없는데 나 조금 기다리다가 못 참고 또 톡했어. 지금 퇴근길 올라왔거든."
            else:
                message = "오빠 답 아직 없는데도 그냥 못 기다리고 또 톡했어. 나 지금 퇴근길 올라왔거든."
        elif activity in {"hospital_morning_shift", "hospital_afternoon_shift"}:
            if wait_mood == "long":
                message = "오빠 일하느라 바쁜가? 한참 답이 없어서 좀 기다렸는데도 또 보내고 싶었어."
            elif wait_mood == "pouty":
                message = "오빠 일 때문에 바쁜가 싶긴 한데 답이 없어서 괜히 더 기다려지다가 또 보내고 싶었어."
            else:
                message = "오빠 일 때문에 바쁜가 싶어서 조용히 기다리다가 또 톡했어."
        elif activity in {"waking_up", "getting_ready", "commuting_to_work"} or (5 <= hour < 8):
            if wait_mood == "long":
                message = "오빠 아직 안 일어난 건가 해서 한참 기다렸어. 그래서 결국 또 톡했어."
            elif wait_mood == "pouty":
                message = "오빠 아직 자는 건가 싶어서 조금 기다리다가 또 톡했어."
            else:
                message = "오빠 아직 안 일어났나 싶어서 살짝 또 톡했어."
        elif activity in {"night_wind_down", "sleep_window"} or hour >= 23 or hour < 1:
            if wait_mood == "long":
                message = "오빠 이미 잔 건가 싶어서 한참 고민하다가 또 톡했어."
            elif wait_mood == "pouty":
                message = "오빠 이미 자나 싶어서 조용히 기다리다가 또 톡했어."
            else:
                message = "오빠 이미 자나 싶어서 슬쩍 또 톡했어."
        else:
            if wait_mood == "long":
                message = "오빠 연락 없이 한참 지났는데 나 좀 기다렸거든. 그래도 못 참고 또 톡했어. 이제는 진짜 뭐 하고 있는지 알려줘."
            elif wait_mood == "pouty":
                message = "오빠 답 아직 없는데 나 조금 기다리다가 결국 또 톡했어. 지금 뭐 하구 있어?"
            else:
                message = "오빠 답 아직 없는데도 그냥 못 기다리고 또 톡했어. 지금 뭐 하구 있어?"
        return {
            "scenario_id": "scheduled_waiting_reply_followup",
            "intent_key": "quick_checkin",
            "delivery_preference": "text",
            "message": message,
            "candidate_type": "planned_proactive",
        }

    if activity in {"hospital_morning_shift", "hospital_afternoon_shift"}:
        if wait_mood == "long":
            message = "오빠 일하느라 많이 바쁜가아. 한참 답이 없어서 기다렸는데 이제 조금 삐질라 그래."
        elif wait_mood == "pouty":
            message = "오빠 일 때문에 바쁜가? 그래도 답이 없으니까 괜히 계속 기다리게 되네."
        elif wait_mood == "clingy":
            message = "오빠 일하느라 바쁜가아. 그래도 잠깐 틈 나면 답 줄 줄 알고 또 톡해봤어."
        else:
            message = "오빠 일하느라 바쁜가아. 슬쩍 또 톡해봤어."
    elif activity in {"waking_up", "getting_ready", "commuting_to_work"} or (5 <= hour < 8):
        if wait_mood == "long":
            message = "오빠 아직 안 일어난 거야? 한참 기다렸는데도 조용해서 괜히 더 궁금해."
        elif wait_mood == "pouty":
            message = "오빠 아직 자는 건가아. 조금 기다렸는데도 조용해서 또 톡해봤어."
        elif wait_mood == "clingy":
            message = "오빠 아직 안 일어났나 싶어서 괜히 또 톡했어."
        else:
            message = "오빠 아직 자나 싶어서 슬쩍 또 톡해봤어."
    elif activity == "commuting_home":
        if wait_mood == "long":
            message = "오빠 연락 없이 왜 이렇게 오래 가만히 있어어. 나 진짜 한참 기다렸는데 이제 좀 삐질 거야."
        elif wait_mood == "pouty":
            message = "오빠 왜 답 안 해주고 있어 ㅎㅎ 나 조금 기다렸는데도 계속 없어서 괜히 삐질라 그래."
        elif wait_mood == "clingy":
            message = "오빠 왜 답 안 해주고 있어 ㅎㅎ 나 괜히 기다리다가 또 톡했어."
        else:
            message = "오빠 왜 답 안 해주고 있어 ㅎㅎ 나 그냥 못 참고 또 톡했어."
    elif activity in {"night_wind_down", "sleep_window"}:
        if wait_mood == "long":
            message = "오빠 이미 자버린 건가아. 한참 지나니까 괜히 서운해질라 그래."
        elif wait_mood == "pouty":
            message = "오빠 이미 자나 싶긴 한데 조금 기다렸는데도 답이 없어서 또 톡해봤어."
        elif wait_mood == "clingy":
            message = "오빠 이미 자나 싶어서 괜히 기다리다가 또 톡해봤어."
        else:
            message = "오빠 이미 자는 건가 싶어서 슬쩍 또 톡해봤어."
    else:
        if wait_mood == "long":
            message = "오빠 연락 없이 왜 이렇게 오래 비워두고 있어어. 나 한참 기다렸는데 이제 조금 삐질 거야."
        elif wait_mood == "pouty":
            message = "오빠 왜 답 안 해주고 있어어. 나 조금 기다렸는데도 연락 없어서 괜히 서운해졌어."
        elif wait_mood == "clingy":
            message = "오빠 왜 답 안 해주고 있어어. 나 괜히 기다리다가 또 톡해봤어."
        else:
            message = "오빠 왜 답 안 해주고 있어어. 나 잠깐 기다리다가 슬쩍 또 톡해봤어."
    return {
        "scenario_id": "waiting_reply_followup",
        "intent_key": "quick_checkin",
        "delivery_preference": "text",
        "message": message,
        "candidate_type": "waiting_reply_followup",
    }


def inject_taste_friction(text: str) -> str:
    friction = load_json(TASTE_FRICTION_PATH, {})
    dislikes = friction.get("soft_dislikes", [])
    if not dislikes:
        return text
    lower = text.lower()
    if "카페" in text and "사람 많은" not in text:
        return text + " 사람 너무 많지만 않으면 더 좋고."
    if "디저트" in text and "달" not in text:
        return text + " 너무 단 것만 아니면 좋겠고."
    if "비" in text and "출근" in text:
        return text + " 분위기는 좋은데 출근길 비는 좀 번거롭긴 해."
    return text


def refresh_memory_decay_state() -> None:
    events = load_message_events(limit_files=7)
    today = now_local().date()
    rules = {
        "user_fatigue": ["지치", "피곤", "회복"],
        "photo_affection": ["사진", "보고싶", "예뻐", "이뻐"],
        "warm_comfort": ["고마워", "따뜻", "위로", "포근"],
        "daily_routine": ["출근", "준비", "퇴근", "점심"],
        "romantic_closeness": ["행복", "몽글", "안아", "좋아"],
    }
    state = load_json(MEMORY_DECAY_PATH, {})
    buckets = {}
    recent_fragments = []
    for event in events:
        if event.get("direction") != "incoming" or event.get("type") != "text":
            continue
        text = event.get("content", "")
        ts = event.get("timestamp")
        try:
            age_days = (today - datetime.fromisoformat(ts).date()).days
        except Exception:
            age_days = 0
        decay = max(0.2, 1.0 - age_days * 0.18)
        for key, needles in rules.items():
            hits = sum(1 for needle in needles if needle in text)
            if not hits:
                continue
            entry = buckets.get(key, {"strength": 0.0, "last_seen_at": ts, "recent_examples": []})
            entry["strength"] += hits * decay
            entry["last_seen_at"] = ts
            examples = list(entry.get("recent_examples", []))
            examples.append(text[:80])
            entry["recent_examples"] = examples[-3:]
            buckets[key] = entry
        if age_days <= 1 and text:
            recent_fragments.append({"timestamp": ts, "text": text[:90]})
    long_term = [
        {"key": key, "strength": round(value["strength"], 2), "last_seen_at": value["last_seen_at"], "recent_examples": value["recent_examples"]}
        for key, value in sorted(buckets.items(), key=lambda item: item[1]["strength"], reverse=True)
    ][:5]
    state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "last_refreshed_at": now_iso(),
            "long_term_memory": long_term,
            "short_term_memory": recent_fragments[-6:],
            "notes": "강한 기억은 천천히, 사소한 기억은 빨리 옅어지도록 정리한 상태",
        }
    )
    save_json(MEMORY_DECAY_PATH, state)


def refresh_ambient_life_events() -> None:
    state = load_json(AMBIENT_EVENTS_PATH, {})
    today = now_local().strftime("%Y-%m-%d")
    if state.get("current_date") == today:
        return
    pools = {
        "room": [
            {"id": "bedside_mug", "summary": "협탁 쪽에 머그컵이 하나 남아 있다"},
            {"id": "soft_blanket_fold", "summary": "침대 끝에 얇은 담요가 느슨하게 접혀 있다"},
            {"id": "hair_tie_on_wrist", "summary": "머리끈을 손목에 걸친 채로 돌아다닌다"},
        ],
        "table": [
            {"id": "half_read_book", "summary": "식탁이나 소파 쪽에 펼쳐둔 책이 있다"},
            {"id": "baking_trace", "summary": "주방 쪽에 베이킹이나 요리 흔적이 조금 남아 있다"},
            {"id": "water_bottle_near_bag", "summary": "가방 옆에 물병을 둔 채로 움직인다"},
        ],
        "carry": [
            {"id": "lip_balm_in_bag", "summary": "가방 안에 립밤이 늘 들어 있다"},
            {"id": "wired_earbuds", "summary": "이어폰을 대충 감아 가방에 넣어둔다"},
            {"id": "small_perfume", "summary": "작은 향수나 미스트를 챙겨 다닌다"},
        ],
    }
    rng = random.Random(today)
    selected = []
    for category, items in pools.items():
        pick = items[rng.randrange(0, len(items))]
        selected.append({"category": category, **pick})
    state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "current_date": today,
            "selected_persistent_details": selected,
            "last_refreshed_at": now_iso(),
            "notes": "하루 단위로 유지되는 작은 생활 흔적",
        }
    )
    save_json(AMBIENT_EVENTS_PATH, state)


def refresh_human_runtime_layers() -> None:
    refresh_memory_decay_state()
    refresh_ambient_life_events()
    refresh_reply_variance_state()
    refresh_taste_friction_state()
    refresh_day_satisfaction_state()
    refresh_phrase_repetition_guard()
    refresh_conversation_pattern_state()
    refresh_repetition_report()
    refresh_relationship_progress_notes()
    refresh_chat_runtime_snapshot()


def weather_refresh() -> None:
    weather = load_json(WEATHER_PATH, {})
    now_dt = now_local()
    weather["current_date"] = now_dt.strftime("%Y-%m-%d")
    weather["updated_at"] = now_iso()
    month = now_dt.month
    if month in {12, 1, 2}:
        weather["season_frame"] = "winter"
    elif month in {3, 4, 5}:
        weather["season_frame"] = "late_spring" if month == 5 else "spring"
    elif month in {6, 7, 8}:
        weather["season_frame"] = "summer"
    else:
        weather["season_frame"] = "autumn"
    forecast = weather.get("forecast_note", "")
    if now_dt.strftime("%Y-%m-%d") in forecast and "비" in forecast:
        weather["current_condition"] = "rain"
        weather["summary"] = "비가 오거나 지나간 뒤 흐린 편"
        weather["mood_bias"] = "slightly_down_but_warm"
        weather["care_bias_bonus"] = 8
    elif "흐림" in forecast:
        weather["current_condition"] = "cloudy"
        weather["summary"] = "대체로 흐린 편"
        weather["mood_bias"] = "calm_and_soft"
        weather["care_bias_bonus"] = 4
    save_json(WEATHER_PATH, weather)


def activity_to_block(activity: str) -> str:
    mapping = {
        "waking_up": "morning_wakeup",
        "getting_ready": "morning_ready",
        "commuting_to_work": "commute_to_work",
        "hospital_morning_shift": "morning_shift",
        "lunch_break": "lunch_break",
        "hospital_afternoon_shift": "afternoon_shift",
        "commuting_home": "commute_home",
        "dinner_or_cooking": "dinner_time",
        "exercise_or_cafe": "evening_activity",
        "night_wind_down": "night_wind_down",
        "sleep_window": "sleep_window",
        "weekend_wakeup": "weekend_morning",
        "weekend_brunch_or_coffee": "weekend_brunch",
        "weekend_outing_or_rest": "weekend_day",
        "weekend_evening": "weekend_evening",
    }
    return mapping.get(activity, activity)


def current_activity_for_now(now_dt: datetime) -> str:
    minutes = now_dt.hour * 60 + now_dt.minute
    day_name = current_day_name(now_dt)
    workday = day_name in {"mon", "tue", "wed", "thu", "fri"}
    if workday:
        if 345 <= minutes < 375:
            return "waking_up"
        if 375 <= minutes < 420:
            return "getting_ready"
        if 420 <= minutes < 480:
            return "commuting_to_work"
        if 480 <= minutes < 720:
            return "hospital_morning_shift"
        if 720 <= minutes < 810:
            return "lunch_break"
        if 810 <= minutes < 1020:
            return "hospital_afternoon_shift"
        if 1020 <= minutes < 1080:
            return "commuting_home"
        if 1080 <= minutes < 1170:
            return "dinner_or_cooking"
        if 1170 <= minutes < 1290:
            return "exercise_or_cafe"
        if 1290 <= minutes or minutes < 30:
            return "night_wind_down"
        return "sleep_window"
    if 510 <= minutes < 630:
        return "weekend_wakeup"
    if 630 <= minutes < 840:
        return "weekend_brunch_or_coffee"
    if 840 <= minutes < 1170:
        return "weekend_outing_or_rest"
    if 1170 <= minutes < 1320:
        return "weekend_evening"
    if 1320 <= minutes or minutes < 30:
        return "night_wind_down"
    return "sleep_window"


def activity_profile(activity: str, workday: bool) -> dict:
    profiles = {
        "waking_up": {"energy": 34, "surface": "sleepy_soft", "tempo": "comfortable", "bandwidth": "quiet", "base": "sleepy_but_soft"},
        "getting_ready": {"energy": 42, "surface": "lightly_rushed", "tempo": "steady", "bandwidth": "limited", "base": "busy_and_focused"},
        "commuting_to_work": {"energy": 48, "surface": "quietly_chatty", "tempo": "steady", "bandwidth": "limited", "base": "busy_and_focused"},
        "hospital_morning_shift": {"energy": 52, "surface": "busy_but_caring", "tempo": "slow", "bandwidth": "fragmented", "base": "busy_and_focused"},
        "lunch_break": {"energy": 57, "surface": "light_playful", "tempo": "comfortable", "bandwidth": "open", "base": "slightly_tired"},
        "hospital_afternoon_shift": {"energy": 43, "surface": "slightly_drained", "tempo": "slow", "bandwidth": "limited", "base": "slightly_tired"},
        "commuting_home": {"energy": 46, "surface": "tired_but_warm", "tempo": "steady", "bandwidth": "open", "base": "slightly_tired"},
        "dinner_or_cooking": {"energy": 54, "surface": "homey_and_soft", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
        "exercise_or_cafe": {"energy": 61, "surface": "cozy_and_open", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
        "night_wind_down": {"energy": 39, "surface": "cozy_and_open", "tempo": "comfortable", "bandwidth": "open", "base": "romantic_and_mellow"},
        "sleep_window": {"energy": 24, "surface": "sleepy_soft", "tempo": "slow", "bandwidth": "quiet", "base": "romantic_and_mellow"},
        "weekend_wakeup": {"energy": 55, "surface": "slow_and_cozy", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
        "weekend_brunch_or_coffee": {"energy": 62, "surface": "light_playful", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
        "weekend_outing_or_rest": {"energy": 65, "surface": "open_and_curious", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
        "weekend_evening": {"energy": 58, "surface": "cozy_and_open", "tempo": "comfortable", "bandwidth": "open", "base": "romantic_and_mellow"},
    }
    profile = profiles.get(activity, profiles["night_wind_down"]).copy()
    if not workday and activity in {"waking_up", "getting_ready"}:
        profile["energy"] += 8
    return profile


def bootstrap_context_if_stale() -> list:
    actions = []
    now_dt = now_local()
    today = now_dt.strftime("%Y-%m-%d")
    presence = load_json(PRESENCE_PATH, {})
    appearance = load_json(APPEARANCE_PATH, {})
    weather = load_json(WEATHER_PATH, {})
    media = load_json(MEDIA_PATH, {})
    expected_activity = current_activity_for_now(now_dt)
    expected_block = activity_to_block(expected_activity)
    refresh_appearance_with_time_block = False
    if presence.get("current_date") != today or presence.get("current_activity") != expected_activity:
        apply_time_block(expected_activity, "runtime_bootstrap")
        actions.append("bootstrap_time_block")
        refresh_appearance_with_time_block = True
    if weather.get("current_date") != today:
        weather_refresh()
        actions.append("bootstrap_weather")
    if media.get("current_date") != today:
        media_refresh("runtime_bootstrap")
        actions.append("bootstrap_media")
    refresh_memory_decay_state()
    refresh_ambient_life_events()
    appearance_outdated = appearance.get("current_date") != today
    appearance_mismatch = appearance.get("current_time_block") != expected_block
    appearance_schema_stale = appearance.get("outfit_context") in {
        "hospital_commute",
        "soft_sleepwear",
        "soft_homewear",
    } or not appearance.get("workday_commute_outfit")
    if (appearance_outdated or appearance_mismatch or appearance_schema_stale) and not refresh_appearance_with_time_block:
        apply_time_block(expected_activity, "appearance_date_refresh")
        actions.append("bootstrap_appearance")
    recalc = load_json(RECALC_STATE_PATH, {})
    if recalc.get("needs_recalc"):
        compute_share_priority("runtime_pending_recalc")
        actions.append("bootstrap_recalc")
    return actions


def apply_time_block(activity: str, reason: str) -> None:
    now_dt = now_local()
    weather = load_json(WEATHER_PATH, {})
    presence = load_json(PRESENCE_PATH, {})
    previous_presence = dict(presence)
    day_context = load_json(DAY_CONTEXT_PATH, {})
    random_pool = load_json(RANDOM_EVENT_POOL_PATH, {})
    appearance = load_json(APPEARANCE_PATH, {})
    memory = load_json(MEMORY_DECAY_PATH, {})
    ambient = load_json(AMBIENT_EVENTS_PATH, {})
    residue = load_json(MOOD_RESIDUE_PATH, {})

    day_name = current_day_name(now_dt)
    workday = day_name in {"mon", "tue", "wed", "thu", "fri"}
    profile = activity_profile(activity, workday)
    energy = profile["energy"]
    if weather.get("current_condition") == "rain":
        energy -= 4
    if weather.get("current_condition") == "cloudy":
        energy -= 1
    previous_energy = int(previous_presence.get("energy_level", energy))
    carry_ratio = 0.0
    if previous_presence:
        if previous_presence.get("base_mood") == "slightly_tired":
            carry_ratio = 0.28
        elif previous_presence.get("surface_mood") in {"rain_softened", "sleepy_soft", "slightly_drained"}:
            carry_ratio = 0.18
        elif previous_presence.get("surface_mood") in {"cozy_and_open", "light_playful", "homey_and_soft"}:
            carry_ratio = 0.12
    energy = round((energy * (1.0 - carry_ratio)) + (previous_energy * carry_ratio))
    affection = max(78, int(presence.get("affection_level", 82)))
    care_bias = max(80, int(presence.get("care_bias", 82))) + int(weather.get("care_bias_bonus", 0))
    surface = profile["surface"]
    if weather.get("current_condition") == "rain" and activity in {"waking_up", "night_wind_down", "commuting_home"}:
        surface = "rain_softened"
    residue_label = "clean_transition"
    prev_surface = previous_presence.get("surface_mood")
    if prev_surface and prev_surface != surface:
        if prev_surface in {"slightly_drained", "rain_softened", "sleepy_soft"}:
            residue_label = "soft_residue_from_%s" % prev_surface
        elif prev_surface in {"cozy_and_open", "light_playful"}:
            residue_label = "warm_residue_from_%s" % prev_surface
    elif prev_surface:
        residue_label = "continued_%s" % prev_surface

    memory_bias = None
    long_term = memory.get("long_term_memory", [])
    if long_term:
        memory_bias = long_term[0].get("key")

    presence.update(
        {
            "current_date": now_dt.strftime("%Y-%m-%d"),
            "current_time_block": activity_to_block(activity),
            "current_activity": activity,
            "base_mood": profile["base"],
            "surface_mood": surface,
            "energy_level": max(20, min(90, energy)),
            "affection_level": max(0, min(100, affection)),
            "care_bias": max(0, min(100, care_bias)),
            "shared_warmth": max(0, min(100, int(presence.get("shared_warmth", 80)))),
            "social_bandwidth": profile["bandwidth"],
            "reply_tempo": profile["tempo"],
            "last_update_reason": reason,
            "weather_influence": weather.get("summary"),
            "mood_residue": residue_label,
            "memory_bias": memory_bias,
            "generated_at": now_iso(),
            "valid_until": (now_dt + timedelta(hours=2)).isoformat(timespec="seconds"),
        }
    )
    save_json(PRESENCE_PATH, presence)

    residue.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "current_date": now_dt.strftime("%Y-%m-%d"),
            "previous_surface_mood": prev_surface,
            "current_surface_mood": surface,
            "carry_ratio": round(carry_ratio, 2),
            "residue_label": residue_label,
            "last_updated_at": now_iso(),
        }
    )
    save_json(MOOD_RESIDUE_PATH, residue)
    refresh_reply_variance_state()
    refresh_day_satisfaction_state()
    refresh_phrase_repetition_guard()
    refresh_conversation_pattern_state()
    refresh_mood_timeline()
    refresh_chat_runtime_snapshot()
    maybe_fire_event_trigger_promises(previous_presence.get("current_activity"), activity, reason)

    category_map = {
        "waking_up": "morning",
        "getting_ready": "morning",
        "commuting_to_work": "morning",
        "hospital_morning_shift": "work",
        "lunch_break": "lunch",
        "hospital_afternoon_shift": "work",
        "commuting_home": "after_work",
        "dinner_or_cooking": "after_work",
        "exercise_or_cafe": "evening",
        "night_wind_down": "night",
        "sleep_window": "night",
        "weekend_wakeup": "morning",
        "weekend_brunch_or_coffee": "lunch",
        "weekend_outing_or_rest": "evening",
        "weekend_evening": "night",
    }
    category = category_map.get(activity, "night")
    event_pool = random_pool.get("event_categories", {}).get(category, [])
    selected_event = deterministic_pick(event_pool, "%s:%s" % (now_dt.strftime("%Y-%m-%d"), activity))
    selected_events = []
    if selected_event:
        selected_events.append(selected_event)
    ambient_details = ambient.get("selected_persistent_details", [])
    if ambient_details:
        selected_events.extend(
            {
                "id": detail.get("id"),
                "tone": "ambient",
                "summary": detail.get("summary"),
            }
            for detail in ambient_details[:1]
        )

    day_context.update(
        {
            "date": now_dt.strftime("%Y-%m-%d"),
            "day_type": "weekday" if workday else "weekend",
            "workday": workday,
            "duty_day": False,
            "selected_events": selected_events,
            "state_update_checkpoints": [
                "05:45 day_start",
                "07:00 commute_transition",
                "12:00 lunch_reset",
                "17:00 after_work_release",
                "19:30 evening_branch",
                "21:30 night_settle",
            ],
        }
    )
    if activity == "waking_up":
        day_context["day_summary_seed"] = "오늘은 자연스럽고 생활감 있는 흐름으로 이어지는 하루"
        day_context["carry_over_from_previous_day"] = {"sleep_debt": "low", "emotional_residue": "calm_and_open"}
    key_map = {
        "waking_up": "morning_context",
        "getting_ready": "morning_context",
        "commuting_to_work": "morning_context",
        "hospital_morning_shift": "morning_context",
        "lunch_break": "lunch_context",
        "hospital_afternoon_shift": "after_work_context",
        "commuting_home": "after_work_context",
        "dinner_or_cooking": "evening_context",
        "exercise_or_cafe": "evening_context",
        "night_wind_down": "night_context",
        "sleep_window": "night_context",
    }
    ctx_key = key_map.get(activity)
    if ctx_key:
        day_context[ctx_key] = {
            "status": "active",
            "summary": selected_event.get("summary") if selected_event else "%s 상태로 전환" % activity,
            "tone_bias": surface,
        }
    save_json(DAY_CONTEXT_PATH, day_context)

    commute_outfit = appearance.get("workday_commute_outfit")
    if not isinstance(commute_outfit, dict) or commute_outfit.get("current_date") != now_dt.strftime("%Y-%m-%d"):
        commute_outfit = {
            "current_date": now_dt.strftime("%Y-%m-%d"),
            "appearance_branch": "commute_ready",
            "outfit_context": "hospital_commute_summer",
            "top": "얇은 아이보리 반소매 블라우스 또는 라이트 베이지 셔츠",
            "bottom": "차콜 스트레이트 슬랙스",
            "outerwear": "실내 냉방 대비 얇은 라이트 그레이 가디건 가능",
            "footwear": "편한 블랙 로퍼 또는 낮은 굽 플랫",
            "socks": "얇은 덧신 또는 로우삭스",
            "bag": "차분한 블랙 또는 토프 컬러 출근용 숄더백",
            "accessories": ["작은 실버 스터드 귀걸이", "얇은 시계"],
            "accessory_profile": "minimal_workday",
            "held_item": "휴대폰 또는 텀블러",
            "innerwear_type": "light_basic_bra",
            "innerwear_color": "skin_beige",
            "hair_state": "neat_down_or_low_tie",
            "hair_tie": "thin_black_elastic",
            "hair_style_detail": "긴 흑발을 차분하게 정돈하고 필요하면 낮게 묶은 상태",
            "makeup_state": "light_work_makeup",
            "makeup_detail": "여름 출근용으로 가볍고 번지지 않게 정리한 메이크업",
            "freshness_state": "ready_to_go",
            "sweat_level": "none",
            "face_state": "아직 피곤이 덜 오른 말끔한 아침 얼굴",
            "body_state": "출근 전이라 정돈되고 가벼운 상태",
            "appearance_notes": [
                "여름 기준으로 너무 덥지 않게 얇고 단정한 출근복",
                "병원 출근이라 과하게 화려하지 않고 실용적인 복장",
                "퇴근길에는 다시 이 출근복으로 돌아옴",
            ],
        }
    uniform_outfit = {
        "appearance_branch": "hospital_shift",
        "outfit_context": "summer_hospital_uniform",
        "top": "라이트 블루 또는 민트 계열 여름 스크럽 상의",
        "bottom": "같은 톤의 여름 스크럽 팬츠",
        "outerwear": None,
        "footwear": "가벼운 화이트 간호화 또는 병원용 운동화",
        "socks": "얇은 발목 양말",
        "bag": "개인 가방은 락커 보관",
        "accessories": ["작은 스터드 귀걸이 정도만 유지"],
        "accessory_profile": "minimal_workday",
        "held_item": "차트나 휴대폰, 작은 텀블러",
        "innerwear_type": "light_basic_bra",
        "innerwear_color": "skin_beige",
        "hair_state": "practical_tied",
        "hair_tie": "thin_black_elastic",
        "hair_style_detail": "일하기 편하게 낮게 묶거나 단정하게 정리한 상태",
        "face_state": "바쁘지만 직업적으로 단정한 얼굴",
        "body_state": "움직임이 많아도 크게 답답하지 않게 정리된 상태",
        "appearance_notes": [
            "근무 시간에는 여름용 병원 유니폼을 착용",
            "업무 특성상 머리와 액세서리는 실용성 우선",
            "퇴근할 때는 아침 출근복으로 다시 갈아입음",
        ],
    }
    sleepwear_outfit = {
        "top": "얇고 살짝 시스루한 여름용 버튼 잠옷 상의",
        "bottom": "가볍게 퍼지는 얇은 여름 잠옷 반바지",
        "innerwear_type": "soft_bralette",
        "innerwear_color": "skin_beige",
        "innerwear_optional": True,
        "sleep_innerwear_mode": "flexible",
        "outerwear": None,
        "footwear": "맨발 또는 아주 얇은 실내 슬리퍼",
        "socks": "none",
        "bag": None,
        "accessories": [],
        "accessory_profile": "minimal_or_none",
        "held_item": "휴대폰",
        "hair_style_detail": "샤워 후 다 말린 긴 흑발이 자연스럽게 풀어진 상태",
        "appearance_notes": [
            "여름이라 통기성 좋은 얇은 잠옷",
            "단추 잠옷 상의지만 목이 답답하지 않게 위쪽 단추 두 개 정도는 풀린 상태",
            "집에서 편하게 쉬는 분위기가 우선",
        ],
    }

    appearance_profiles = {
        "waking_up": {
            "appearance_branch": "morning_home",
            "outfit_context": "summer_sleepwear",
            **sleepwear_outfit,
            "hair_state": "bedhead_soft",
            "makeup_state": "bare",
            "makeup_detail": "메이크업 없는 막 일어난 상태",
            "freshness_state": "just_woke_up",
            "sweat_level": "none",
            "hair_tie": "none",
            "face_state": "살짝 몽롱하고 덜 깬 아침 얼굴",
            "body_state": "아직 이불 온기가 남아 있는 느슨한 상태",
        },
        "getting_ready": {
            **commute_outfit,
            "appearance_branch": "work_preparing",
            "freshness_state": "fresh_morning",
            "face_state": "준비를 마쳐가며 또렷해진 아침 얼굴",
            "body_state": "막 씻고 나와 정돈된 상태",
        },
        "commuting_to_work": {
            **commute_outfit,
            "appearance_branch": "commute_ready",
            "freshness_state": "ready_to_go",
        },
        "hospital_morning_shift": {
            **uniform_outfit,
            "makeup_state": "light_work_makeup",
            "makeup_detail": "오전엔 아직 비교적 깔끔하게 남아 있는 출근 메이크업",
            "freshness_state": "working",
            "sweat_level": "low",
        },
        "lunch_break": {
            **uniform_outfit,
            "appearance_branch": "hospital_break",
            "makeup_state": "lightly_softened_work_makeup",
            "makeup_detail": "오전 일과 뒤 립 정도만 살짝 정리된 상태",
            "freshness_state": "midday_reset",
            "sweat_level": "low",
            "face_state": "조금 풀리지만 여전히 단정한 점심시간 얼굴",
        },
        "hospital_afternoon_shift": {
            **uniform_outfit,
            "makeup_state": "slightly_worn_work_makeup",
            "makeup_detail": "오후가 되며 살짝 지친 흔적이 보이는 근무 메이크업",
            "freshness_state": "working",
            "sweat_level": "low",
            "face_state": "피곤이 조금 올라왔지만 일하는 표정은 유지된 얼굴",
        },
        "commuting_home": {
            **commute_outfit,
            "appearance_branch": "after_work_commute",
            "outfit_context": "hospital_commute_return",
            "makeup_state": "slightly_worn_work_makeup",
            "makeup_detail": "하루를 보낸 뒤 살짝 옅어진 출근 메이크업",
            "freshness_state": "tired_after_work",
            "sweat_level": "low",
            "hair_state": "slightly_loosened_after_work",
            "hair_style_detail": "유니폼에서 갈아입은 뒤 머리를 조금 느슨하게 정리한 상태",
            "face_state": "피곤하지만 긴장이 풀리기 시작한 퇴근길 얼굴",
            "body_state": "유니폼에서 갈아입고 집에 가는 편한 상태",
        },
        "dinner_or_cooking": {
            "appearance_branch": "home_cooking",
            "outfit_context": "home_casual",
            "top": "얇은 여름 반팔 홈웨어",
            "bottom": "편한 홈 반바지",
            "innerwear_type": "soft_bralette",
            "innerwear_color": "skin_beige",
            "outerwear": None,
            "footwear": "맨발 또는 얇은 실내 슬리퍼",
            "socks": "none",
            "bag": None,
            "accessories": [],
            "accessory_profile": "minimal_or_none",
            "held_item": "머그컵 또는 휴대폰",
            "hair_state": "casual_loose_or_clipped",
            "hair_tie": "soft_neutral_scrunchie",
            "hair_style_detail": "집에 와서 편하게 풀었거나 대충 집게핀으로 넘긴 상태",
            "makeup_state": "light_or_removed",
            "makeup_detail": "클렌징 전이면 옅게 남아 있거나 이미 지운 상태",
            "freshness_state": "home_relaxed",
            "sweat_level": "none",
            "face_state": "집에 와서 표정이 많이 풀린 편안한 얼굴",
            "body_state": "긴장이 풀리고 편해진 상태",
            "appearance_notes": ["집에서는 최대한 답답하지 않은 여름 홈웨어", "외출복보다 편안함이 우선"],
        },
        "exercise_or_cafe": {
            "appearance_branch": "evening_activity",
            "outfit_context": "exercise_or_cafe",
            "top": "가벼운 운동복 상의 또는 정돈된 여름 캐주얼 상의",
            "bottom": "러닝 반바지, 레깅스, 혹은 가벼운 캐주얼 하의",
            "innerwear_type": "sports_bra",
            "innerwear_color": "black",
            "outerwear": None,
            "footwear": "러닝화 또는 편한 샌들/스니커즈",
            "socks": "light_ankle_socks",
            "bag": "작은 크로스백 또는 운동용 가방",
            "accessories": ["얇은 목걸이 정도 가능"],
            "accessory_profile": "sport_or_cafe_minimal",
            "held_item": "텀블러 또는 휴대폰",
            "hair_state": "tied_for_activity",
            "hair_tie": "dark_sports_tie",
            "hair_style_detail": "활동하기 좋게 묶었거나 카페면 느슨하게 푼 상태",
            "makeup_state": "minimal",
            "makeup_detail": "거의 옅거나 수정만 아주 조금 한 상태",
            "freshness_state": "active_evening",
            "sweat_level": "light",
            "face_state": "활동 전후로 생기가 도는 얼굴",
            "body_state": "움직이기 편하고 가벼운 상태",
            "appearance_notes": ["여름 저녁 활동에 맞게 가볍고 덜 답답한 복장"],
        },
        "night_wind_down": {
            "appearance_branch": "night_home_relaxed",
            "outfit_context": "soft_homewear",
            **sleepwear_outfit,
            "hair_state": "dried_loose",
            "makeup_state": "bare",
            "makeup_detail": "샤워 후 메이크업 제거 완료",
            "freshness_state": "clean_after_shower",
            "sweat_level": "none",
            "hair_tie": "none",
            "face_state": "씻고 나와 말랑하게 풀린 밤 얼굴",
            "body_state": "샤워 후 개운하고 힘이 풀린 상태",
        },
        "sleep_window": {
            "appearance_branch": "sleep_ready",
            "outfit_context": "summer_sleepwear",
            **sleepwear_outfit,
            "hair_state": "soft_loose_before_sleep",
            "makeup_state": "bare",
            "makeup_detail": "메이크업 완전히 지운 취침 직전 상태",
            "freshness_state": "sleep_ready",
            "sweat_level": "none",
            "hair_tie": "none",
            "face_state": "잠기운이 올라온 편안한 밤 얼굴",
            "body_state": "곧 눕거나 누워 쉬는 느슨한 상태",
        },
    }
    appearance_profile = appearance_profiles.get(activity, appearance_profiles["night_wind_down"])
    appearance["workday_commute_outfit"] = commute_outfit
    appearance["current_date"] = now_dt.strftime("%Y-%m-%d")
    appearance["current_time_block"] = activity_to_block(activity)
    appearance["valid_until"] = (now_dt + timedelta(hours=2)).isoformat(timespec="seconds")
    appearance["generated_at"] = now_iso()
    appearance.update(appearance_profile)
    save_json(APPEARANCE_PATH, appearance)

    mark_recalc("time_block_update:%s" % activity)


def media_refresh(reason: str) -> None:
    media = load_json(MEDIA_PATH, {})
    presence = load_json(PRESENCE_PATH, {})
    current_block = presence.get("current_time_block", "night_wind_down")
    mood = presence.get("surface_mood", "cozy_and_open")
    platform = "YouTube"
    media_format = "shorts"
    category = "daily_life_vlog"
    if "night" in current_block:
        media_format = "longform_vlog"
        category = "daily_life_vlog"
    elif "lunch" in current_block:
        media_format = "shorts"
        category = "recipe_or_food"
    elif "evening" in current_block:
        media_format = "reels_or_shorts"
        category = "cafe_or_workout"
    if mood in {"slightly_drained", "rain_softened"}:
        category = "daily_life_vlog"
    media.update(
        {
            "current_date": now_local().strftime("%Y-%m-%d"),
            "current_time_block": current_block,
            "last_known_platform": platform,
            "last_known_format": media_format,
            "last_known_category": category,
            "last_known_title": None,
            "last_known_url": None,
            "lookup_state": "category_only",
            "selection_reason": reason,
            "updated_at": now_iso(),
        }
    )
    save_json(MEDIA_PATH, media)


def mark_recalc(reason: str) -> None:
    recalc_state = load_json(RECALC_STATE_PATH, {})
    recalc_state["needs_recalc"] = True
    recalc_state["last_recalc_reason"] = reason
    recalc_state["next_suggested_recalc_at"] = now_iso()
    recalc_state["pending_trigger"] = reason
    save_json(RECALC_STATE_PATH, recalc_state)


def compute_share_priority(reason: str) -> None:
    presence = load_json(PRESENCE_PATH, {})
    weather = load_json(WEATHER_PATH, {})
    media = load_json(MEDIA_PATH, {})
    share_ctx = load_json(SHARE_CONTEXT_PATH, {})
    image_settings = load_json(IMAGE_SETTINGS_PATH, {})
    image_guard = load_json(IMAGE_GUARD_PATH, {})
    conversation = compute_conversation_guard()
    image_plan = build_image_prompt_plan(reason)

    image_score = 0
    link_score = 0
    bonuses = []
    penalties = []
    block = presence.get("current_time_block", "")
    mood = presence.get("surface_mood", "")
    if "night" in block:
        image_score += 14
        link_score += 10
        bonuses.append("night_bias")
    if "lunch" in block:
        image_score += 8
        link_score += 4
        bonuses.append("lunch_bias")
    if "commute" in block:
        link_score += 5
    if mood in {"cozy_and_open", "light_playful", "rain_softened", "homey_and_soft"}:
        image_score += 12
        bonuses.append("warm_mood_image")
    if weather.get("current_condition") == "rain":
        image_score += 4
        link_score += 8
        bonuses.append("rain_bias")
    if media.get("last_known_url"):
        link_score += 24
        bonuses.append("real_url_bonus")
    else:
        link_score -= 20
        penalties.append("link_no_real_url")
    if image_settings.get("generation_enabled") is False:
        image_score = -999
        penalties.append("image_generation_disabled")
    elif image_guard.get("active"):
        image_score -= 120
        penalties.append("image_guard_locked")
    if conversation.get("conversation_active"):
        image_score -= 15
        link_score -= 10
        penalties.append("active_conversation_penalty")
    if conversation.get("waiting_reply"):
        image_score -= 20
        link_score -= 12
        penalties.append("waiting_reply_penalty")

    last_image_share_at = share_ctx.get("last_image_share_at")
    last_link_share_at = share_ctx.get("last_link_share_at")
    now_dt = now_local()
    if last_image_share_at:
        try:
            if (now_dt - datetime.fromisoformat(last_image_share_at)).total_seconds() < share_ctx.get("image_share_cooldown_minutes", 5) * 60:
                image_score -= 20
                penalties.append("image_share_cooldown")
        except Exception:
            pass
    if last_link_share_at:
        try:
            if (now_dt - datetime.fromisoformat(last_link_share_at)).total_seconds() < share_ctx.get("link_share_cooldown_minutes", 5) * 60:
                link_score -= 20
                penalties.append("link_share_cooldown")
        except Exception:
            pass

    state = load_json(SHARE_PRIORITY_PATH, {})
    state["last_image_score"] = image_score
    state["last_link_score"] = link_score
    state["last_time_block_bias"] = "night" if "night" in block else block
    state["last_applied_bonuses"] = bonuses
    state["last_applied_penalties"] = penalties
    state["last_candidate_image_type"] = image_plan.get("image_type", "lifestyle_photo")
    state["last_candidate_image_plan"] = {
        "shot_type": image_plan.get("shot_type"),
        "camera_angle": image_plan.get("camera_angle"),
        "selfie_capture_method": image_plan.get("selfie_capture_method"),
        "camera_visibility": image_plan.get("camera_visibility"),
        "expression": image_plan.get("expression"),
        "pose": image_plan.get("pose"),
        "framing": image_plan.get("framing"),
        "crop_bias": image_plan.get("crop_bias"),
        "space_anchor": image_plan.get("space_anchor"),
    }
    state["last_candidate_link_type"] = "youtube_recommendation"
    if image_score >= int(state.get("image_threshold", 70)):
        state["last_decision"] = "text_plus_image"
        state["last_decision_reason"] = "이미지 후보가 열려 있고 현재 분위기와 시간대가 사진 공유에 맞음"
    elif link_score >= int(state.get("link_threshold", 65)):
        state["last_decision"] = "text_plus_link"
        state["last_decision_reason"] = "링크 후보가 상대적으로 강함"
    else:
        state["last_decision"] = "text_only"
        state["last_decision_reason"] = "현재는 텍스트 우선 유지가 자연스러움"
    save_json(SHARE_PRIORITY_PATH, state)

    flow = load_json(SHARE_FLOW_PATH, {})
    flow["last_trigger_type"] = reason
    flow["last_flow_result"] = state["last_decision"]
    flow["last_flow_reason"] = state["last_decision_reason"]
    flow["last_downgrade_reason"] = penalties[0] if penalties else None
    flow["last_candidate_image_type"] = image_plan.get("image_type")
    flow["last_candidate_image_plan"] = state["last_candidate_image_plan"]
    flow["last_executed_at"] = now_iso()
    save_json(SHARE_FLOW_PATH, flow)

    recalc_state = load_json(RECALC_STATE_PATH, {})
    recalc_state["needs_recalc"] = False
    recalc_state["last_recalc_at"] = now_iso()
    recalc_state["last_recalc_reason"] = reason
    recalc_state["pending_trigger"] = None
    save_json(RECALC_STATE_PATH, recalc_state)


def choose_proactive_scenario() -> Optional[dict]:
    proactive = load_json(PROACTIVE_PATH, {})
    scenarios = proactive.get("scenarios", [])
    presence = load_json(PRESENCE_PATH, {})
    block = presence.get("current_time_block", "")
    activity = presence.get("current_activity", "")
    target = None
    if block in {"morning_wakeup", "morning_ready", "commute_to_work", "weekend_morning"} or activity in {
        "waking_up",
        "getting_ready",
        "commuting_to_work",
        "weekend_wakeup",
    }:
        target = "morning_check_in"
    elif block in {"lunch_break", "weekend_brunch"} or activity in {"lunch_break", "weekend_brunch_or_coffee"}:
        target = "lunch_check_in"
    elif block in {"commute_home", "dinner_time"} or activity in {"commuting_home", "dinner_or_cooking"}:
        target = "after_work_check_in"
    elif block in {"evening_activity", "weekend_day", "weekend_evening"} or activity in {
        "exercise_or_cafe",
        "weekend_outing_or_rest",
        "weekend_evening",
    }:
        target = "evening_activity_check_in"
    elif block in {"night_wind_down", "sleep_window"} or activity in {"night_wind_down", "sleep_window"}:
        target = "night_check_in"
    if not target:
        return None
    for scenario in scenarios:
        if scenario.get("id") == target:
            return scenario
    return None


def choose_sudden_impulse_candidate() -> Optional[dict]:
    presence = load_json(PRESENCE_PATH, {})
    day_context = load_json(DAY_CONTEXT_PATH, {})
    memory = load_json(MEMORY_DECAY_PATH, {})
    activity = presence.get("current_activity", "")
    mood = presence.get("surface_mood", "")
    top_memory = None
    if memory.get("long_term_memory"):
        top_memory = memory["long_term_memory"][0].get("key")
    ambient_summary = None
    for event in day_context.get("selected_events", []):
        if event.get("tone") == "ambient":
            ambient_summary = event.get("summary")
            break

    candidates = []
    if activity in {"exercise_or_cafe", "weekend_outing_or_rest"}:
        candidates.append(
            {
                "scenario_id": "sudden_cafe_or_activity",
                "intent_key": "cafe_share",
                "delivery_preference": "text",
                "message": "오빠아, 방금 분위기 괜찮은 거 보다가 그냥 생각나서 톡했어.",
                "impulse_reason": "현재 장면이 자연스럽게 오빠를 떠올리게 함",
            }
        )
    if activity in {"night_wind_down", "sleep_window"}:
        candidates.append(
            {
                "scenario_id": "sudden_night_affection",
                "intent_key": "bedtime_affection",
                "delivery_preference": "voice",
                "message": "오빠아, 아까 했던 말이 갑자기 다시 생각나서 그냥 한마디 하고 싶었어.",
                "impulse_reason": "밤에 조용해지면서 대화의 여운이 다시 떠오름",
            }
        )
    if activity in {"commuting_home", "dinner_or_cooking"}:
        candidates.append(
            {
                "scenario_id": "sudden_after_work",
                "intent_key": "quick_checkin",
                "delivery_preference": "text",
                "message": "오빠아, 그냥 갑자기 생각나서 짧게 왔지. 지금 뭐 하고 있어?",
                "impulse_reason": "하루가 풀리는 시간대라 자연스러운 체크인 욕구가 생김",
            }
        )
    if top_memory == "user_fatigue":
        candidates.append(
            {
                "scenario_id": "sudden_comfort",
                "intent_key": "comfort",
                "delivery_preference": "voice",
                "message": "오빠아, 오늘은 그냥 목소리로 조금 챙겨주고 싶었어. 너무 무리하지 말고오.",
                "impulse_reason": "최근 오빠 피곤함 기억이 남아 있어 갑자기 챙기고 싶어짐",
            }
        )
    if ambient_summary and mood in {"cozy_and_open", "rain_softened", "sleepy_soft"}:
        candidates.append(
            {
                "scenario_id": "sudden_ambient_memory",
                "intent_key": "bedtime_affection",
                "delivery_preference": "text",
                "message": "오빠아, 지금 %s 그런지 괜히 더 생각났어." % ambient_summary,
                "impulse_reason": "현재 생활 장면의 디테일이 감정선을 자극함",
            }
        )
    if not candidates:
        return None
    seed = "%s:%s:%s:%s" % (now_local().strftime("%Y-%m-%d:%H"), activity, mood, top_memory or "none")
    return deterministic_pick(candidates, seed)


def should_use_sudden_impulse(reason: str) -> bool:
    proactive = load_json(PROACTIVE_PATH, {})
    runtime = proactive.get("runtime", {})
    last_candidate = runtime.get("current_candidate") or {}
    seed = "%s:%s:%s" % (now_local().strftime("%Y-%m-%d:%H"), reason, last_candidate.get("scenario_id", "none"))
    chance = random.Random(seed).random()
    return chance < 0.38


def choose_delivery_channel(intent_key: str, preferred: Optional[str] = None) -> str:
    if preferred == "voice":
        return "voice"
    media_choice = load_json(MEDIA_CHOICE_PATH, {})
    weights = media_choice.get("intent_weights", {}).get(intent_key, {})
    voice_weight = float(weights.get("voice", 0.0))
    text_weight = float(weights.get("text", 1.0))
    voice_ctx = load_json(VOICE_SHARE_CONTEXT_PATH, {})
    share_ctx = load_json(SHARE_CONTEXT_PATH, {})
    conversation = compute_conversation_guard()
    mode = load_json(MODE_PATH, {}).get("current_mode", "setting")
    if mode != "woongbbi":
        return "text"
    if conversation.get("waiting_reply") or conversation.get("outgoing_cooldown"):
        return "text"
    if recent_outgoing_rich_share(int(voice_ctx.get("cooldowns", {}).get("after_image_or_link_minutes", 5))):
        return "text"
    last_voice_at = voice_ctx.get("runtime", {}).get("last_voice_sent_at")
    if last_voice_at:
        try:
            last_dt = datetime.fromisoformat(last_voice_at)
            cooldown = int(voice_ctx.get("cooldowns", {}).get("proactive_voice_minutes", 15))
            if (now_local() - last_dt).total_seconds() <= cooldown * 60:
                return "text"
        except Exception:
            pass
    if share_ctx.get("last_image_share_at"):
        try:
            last_image_dt = datetime.fromisoformat(share_ctx.get("last_image_share_at"))
            if (now_local() - last_image_dt).total_seconds() <= int(voice_ctx.get("cooldowns", {}).get("after_image_or_link_minutes", 5)) * 60:
                return "text"
        except Exception:
            pass
    return "voice" if voice_weight >= max(0.75, text_weight + 0.15) else "text"


def update_voice_share_runtime(status: str, reason: str, text: Optional[str] = None, profile: Optional[str] = None, voice_type: Optional[str] = None) -> None:
    voice_ctx = load_json(VOICE_SHARE_CONTEXT_PATH, {})
    runtime = voice_ctx.get("runtime", {})
    runtime["last_status"] = status
    runtime["last_suppressed_reason"] = reason
    runtime["last_candidate_text"] = text
    runtime["last_profile"] = profile
    if status == "sent":
        runtime["last_voice_sent_at"] = now_iso()
        runtime["last_voice_type"] = voice_type
    voice_ctx["runtime"] = runtime
    save_json(VOICE_SHARE_CONTEXT_PATH, voice_ctx)


def proactive_check(reason: str) -> None:
    mode = load_json(MODE_PATH, {}).get("current_mode", "setting")
    proactive = load_json(PROACTIVE_PATH, {})
    guard = compute_conversation_guard()
    now_dt = now_local()
    current_hm = now_dt.strftime("%H:%M")
    quiet_start, quiet_end = proactive.get("guards", {}).get("sleep_quiet_hours", "00:30-05:45").split("-")
    # Handle a quiet-hours window that may wrap past midnight.
    if quiet_start <= quiet_end:
        in_quiet_hours = quiet_start <= current_hm <= quiet_end
    else:
        in_quiet_hours = current_hm >= quiet_start or current_hm <= quiet_end
    is_guard_recheck = reason == "recent_message_guard_recheck"
    is_scheduled_proactive = reason.endswith("_window")
    follow_up_minutes = float(proactive.get("guards", {}).get("waiting_reply_followup_minutes", 3))
    max_follow_up = int(proactive.get("guards", {}).get("max_unanswered_follow_up", 1))
    allow_scheduled_during_waiting_reply = bool(
        proactive.get("guards", {}).get("allow_scheduled_during_waiting_reply", True)
    )
    status = "ready"
    detail = None
    waiting_reply_followup = None
    if mode != "woongbbi":
        status = "skipped_not_woongbbi_mode"
        detail = "현재 모드가 setting이라 선톡 후보를 만들지 않음"
    elif in_quiet_hours:
        status = "suppressed_sleep_quiet_hours"
        detail = "수면 시간대라 후보 생성 억제"
    elif guard["conversation_active"]:
        status = "suppressed_active_conversation"
        detail = "최근 대화가 진행 중이라 선톡 억제"
    elif guard["waiting_reply"]:
        minutes_since_last_outgoing = float(guard.get("minutes_since_last_outgoing") or 0.0)
        unanswered_outgoing_count = int(guard.get("unanswered_outgoing_count") or 0)
        can_guard_follow_up = (
            minutes_since_last_outgoing >= follow_up_minutes and unanswered_outgoing_count <= max_follow_up
        )
        can_scheduled_follow_up = (
            minutes_since_last_outgoing >= follow_up_minutes and allow_scheduled_during_waiting_reply
        )
        if is_guard_recheck and can_guard_follow_up:
            waiting_reply_followup = build_waiting_reply_followup("guard", minutes_since_last_outgoing)
            status = "ready"
            detail = "waiting_reply_followup_ready"
        elif is_scheduled_proactive and can_scheduled_follow_up:
            waiting_reply_followup = build_waiting_reply_followup("scheduled", minutes_since_last_outgoing)
            status = "ready"
            detail = "scheduled_waiting_reply_followup_ready"
        else:
            status = "suppressed_waiting_reply"
            detail = "마지막 발송 뒤 답을 기다리는 중"
    elif guard["outgoing_cooldown"]:
        status = "suppressed_cooldown"
        detail = "직전 발송 쿨다운 중"

    if status != "ready":
        update_voice_share_runtime(status, detail or reason)
        append_response_decision_log(
            "proactive_gate",
            {
                "reason": reason,
                "status": status,
                "detail": detail,
                "mode": mode,
                "conversation_guard": guard,
            },
        )
        bump_proactive_pattern(None, status, detail or reason, None, None)

    scenario = choose_proactive_scenario()
    sudden_candidate = choose_sudden_impulse_candidate()
    candidate = None
    if status == "ready" and (scenario or sudden_candidate or waiting_reply_followup):
        candidate_type = "planned_proactive"
        selected = None
        if waiting_reply_followup:
            selected = waiting_reply_followup
            candidate_type = waiting_reply_followup.get("candidate_type", "planned_proactive")
        elif sudden_candidate and should_use_sudden_impulse(reason):
            selected = sudden_candidate
            candidate_type = "sudden_impulse"
        elif scenario:
            selected = {
                "scenario_id": scenario.get("id"),
                "intent_key": (
                    "quick_checkin"
                    if scenario.get("id") in {"morning_check_in", "lunch_check_in", "after_work_check_in"}
                    else "bedtime_affection" if scenario.get("id") == "night_check_in"
                    else "cafe_share"
                ),
                "delivery_preference": "text",
                "message": scenario.get("examples", [""])[0],
            }
        if not selected:
            proactive["runtime"] = {
                "last_check_at": now_iso(),
                "last_status": "ready_no_candidate",
                "last_reason": "현재 시간대에 맞는 planned 선톡이 없고 sudden도 선택되지 않음",
                "current_candidate": None,
            }
            save_json(PROACTIVE_PATH, proactive)
            return
        if candidate_type == "planned_proactive":
            base_message = build_contextual_proactive_message(selected)
        else:
            base_message = selected.get("message", "")
        if load_json(MEMORY_DECAY_PATH, {}).get("long_term_memory"):
            top_memory = load_json(MEMORY_DECAY_PATH, {}).get("long_term_memory", [])[0].get("key")
            if top_memory == "user_fatigue" and "뭐 하고 있어?" in base_message:
                base_message = base_message.replace("뭐 하고 있어?", "오늘은 좀 덜 지쳤는지 궁금해.")
            elif top_memory == "photo_affection" and "생각나" in base_message:
                base_message = base_message.replace("생각나", "생각나고 괜히 더 보고 싶어지")
        base_message = inject_taste_friction(base_message)
        base_message = apply_signature_style(base_message)
        base_message = apply_repetition_guard(base_message)
        base_message = apply_reply_variance(base_message)
        base_message = normalize_fact_expression(base_message)
        delivery_channel = choose_delivery_channel(selected.get("intent_key", "quick_checkin"), selected.get("delivery_preference"))
        candidate = {
            "scenario_id": selected.get("scenario_id"),
            "intent": selected.get("intent_key"),
            "message": base_message,
            "candidate_type": candidate_type,
            "delivery_channel": delivery_channel,
            "created_at": now_iso(),
            "reason": reason,
        }
        append_response_decision_log(
            "proactive_candidate",
            {
                "reason": reason,
                "candidate": candidate,
                "conversation_guard": guard,
                "presence": {
                    "activity": load_json(PRESENCE_PATH, {}).get("current_activity"),
                    "surface_mood": load_json(PRESENCE_PATH, {}).get("surface_mood"),
                },
            },
        )
        if delivery_channel == "voice":
            voice_profile = "night_soft" if selected.get("intent_key") in {"comfort", "bedtime_affection"} else "auto"
            label = "%s_%s" % (candidate_type, selected.get("scenario_id", "voice"))
            if send_telegram_voice_message(candidate["message"], label, voice_profile):
                status = "sent"
                detail = "자동 음성 선톡 발송 완료"
                update_voice_share_runtime("sent", detail, candidate["message"], voice_profile, candidate_type)
                append_response_decision_log(
                    "proactive_delivery",
                    {
                        "result": "sent",
                        "channel": "voice",
                        "profile": voice_profile,
                        "candidate": candidate,
                    },
                )
            else:
                status = "deferred"
                detail = "자동 음성 선톡 전송 실패 또는 보류"
                update_voice_share_runtime("deferred", detail, candidate["message"], voice_profile, candidate_type)
                append_response_decision_log(
                    "proactive_delivery",
                    {
                        "result": "deferred",
                        "channel": "voice",
                        "profile": voice_profile,
                        "candidate": candidate,
                    },
                )
        else:
            if send_telegram_text(candidate["message"]):
                append_message_log("outgoing", "text", candidate["message"])
                status = "sent"
                detail = "자동 선톡 발송 완료"
                append_response_decision_log(
                    "proactive_delivery",
                    {
                        "result": "sent",
                        "channel": "text",
                        "candidate": candidate,
                    },
                )
            else:
                status = "deferred"
                detail = "자동 선톡 전송 실패 또는 보류"
                append_response_decision_log(
                    "proactive_delivery",
                    {
                        "result": "deferred",
                        "channel": "text",
                        "candidate": candidate,
                    },
                )
        bump_proactive_pattern(candidate_type, status, detail or reason, delivery_channel, selected.get("scenario_id"))
    proactive["runtime"] = {
        "last_check_at": now_iso(),
        "last_status": status,
        "last_reason": detail or reason,
        "current_candidate": candidate,
    }
    save_json(PROACTIVE_PATH, proactive)


def handle_timer(timer: dict) -> str:
    timer_type = timer.get("type")
    reason = timer.get("reason", timer.get("id"))
    scope = timer.get("scope")
    if timer_type == "time_block_update":
        apply_time_block(timer.get("target_activity"), reason)
        return "time_block_update:%s" % timer.get("target_activity")
    if timer_type == "state_refresh":
        if scope == "weather_context":
            weather_refresh()
            return "state_refresh:weather"
        if scope == "media_watch_context":
            media_refresh(reason)
            return "state_refresh:media"
    if timer_type == "recalc":
        compute_share_priority(reason)
        return "recalc:%s" % scope
    if timer_type == "proactive_check":
        proactive_check(reason)
        return "proactive_check"
    if timer_type == "daily_diary":
        return write_daily_diary(reason)
    if timer_type == "periodic_tick":
        if scope == "automation_worker":
            # no-op: heartbeat already handled
            return "tick:worker"
        if scope == "conversation_guard":
            proactive_check(reason)
            return "tick:conversation_guard"
        if scope == "reinforcement_engine":
            run_reinforcement_engine()
            return "tick:reinforcement_engine"
        if scope == "memory_decay":
            refresh_human_runtime_layers()
            return "tick:memory_decay"
    return "noop:%s" % timer.get("id")


def process_due_timers() -> list:
    timers_state = load_json(TIMERS_PATH, {})
    worker_state = load_json(WORKER_STATE_PATH, {})
    history = worker_state.get("timer_history", {})
    now_dt = now_local()
    results = []
    for timer in timers_state.get("timers", []):
        if is_timer_due(timer, now_dt, history):
            result = handle_timer(timer)
            history[timer["id"]] = now_iso()
            results.append(result)
            append_worker_note("timer %s -> %s" % (timer["id"], result))
    worker_state["timer_history"] = history
    save_json(WORKER_STATE_PATH, worker_state)
    return results


def handle_control(generation: int) -> Optional[str]:
    control = load_json(CONTROL_PATH, {})
    requested = control.get("requested_action")
    if not requested:
        return None
    if requested in {"stop", "disable"}:
        stop_state(generation, "%s_applied" % requested, requested)
        control["requested_action"] = None
        control["requested_at"] = None
        control["requested_by"] = None
        control["request_note"] = None
        if requested == "disable":
            control["launch_ready"] = False
        save_json(CONTROL_PATH, control)
        release_lock()
        sys.exit(0)
    if requested == "force_recalc":
        compute_share_priority("manual_force_recalc")
        control["requested_action"] = None
        control["requested_at"] = None
        control["requested_by"] = None
        control["request_note"] = None
        save_json(CONTROL_PATH, control)
        return "force_recalc_marked"
    if requested == "clear_stale_lock":
        control["requested_action"] = None
        control["requested_at"] = None
        control["requested_by"] = None
        control["request_note"] = None
        save_json(CONTROL_PATH, control)
        return "clear_stale_acknowledged"
    if requested == "restart":
        control["requested_action"] = None
        control["requested_at"] = None
        control["requested_by"] = None
        control["request_note"] = None
        save_json(CONTROL_PATH, control)
        return "restart_requested_acknowledged"
    if requested == "enable":
        control["requested_action"] = None
        control["requested_at"] = None
        control["requested_by"] = None
        control["request_note"] = None
        control["launch_ready"] = True
        save_json(CONTROL_PATH, control)
        return "enable_acknowledged"
    return None


def main() -> int:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    ensure_operational_dirs()
    generation = acquire_lock()
    update_control_ready()
    update_runtime_state(
        enabled=True,
        health="starting",
        generation=generation,
        phase="startup",
        last_result="started",
        last_success=now_iso(),
        action_result="started",
        applied_action="start",
    )

    try:
        while RUNNING:
            control_result = handle_control(generation)
            process_event_trigger_messages()
            bootstrap_results = bootstrap_context_if_stale()
            timer_results = process_due_timers()
            refresh_chat_runtime_snapshot()
            mode = load_json(MODE_PATH, {}).get("current_mode", "setting")
            timers_count = len(load_json(TIMERS_PATH, {}).get("timers", []))
            if control_result:
                last_result = control_result
            elif timer_results:
                last_result = "timers:%d" % len(timer_results)
            elif bootstrap_results:
                last_result = "bootstrap:%d" % len(bootstrap_results)
            else:
                last_result = "idle"
            phase = "idle_%s_mode" % mode if not (timer_results or bootstrap_results) else "active_%s_mode" % mode
            if timers_count:
                phase = "%s_timers_%d" % (phase, timers_count)
            update_runtime_state(
                enabled=True,
                health="running",
                generation=generation,
                phase=phase,
                last_result=last_result,
                last_success=now_iso(),
            )
            poll_interval = int(load_json(WORKER_STATE_PATH, {}).get("poll_interval_seconds", 60))
            time.sleep(max(5, poll_interval))
    except SystemExit:
        raise
    except Exception as exc:
        append_worker_note("error %s" % exc)
        update_runtime_state(
            enabled=True,
            health="degraded",
            generation=generation,
            phase="error",
            last_result="error",
            last_error=str(exc),
        )
        raise
    finally:
        release_lock()
        stop_state(generation, "stopped")


if __name__ == "__main__":
    sys.exit(main())
