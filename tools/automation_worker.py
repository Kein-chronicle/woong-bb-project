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

from automation.conversation_guard import (
    GOODNIGHT_PATTERNS,
    build_counterpart_state_memory,
    contains_any,
    compute_conversation_guard,
    infer_counterpart_state,
    load_message_events,
)
from automation.diary import write_daily_diary
from automation.event_triggers import (
    derive_event_keys_for_transition,
    factual_status_for_activity,
    normalize_fact_expression,
    parse_event_trigger_command,
    parse_outgoing_event_promise,
    sanitize_promise_message,
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
from project_paths import MESSAGES, ROOT, STATE, TOOLS, ensure_operational_dirs, log_path


MODE_PATH = STATE / "mode_state.json"
TIMERS_PATH = STATE / "timers.json"
RECALC_STATE_PATH = STATE / "share_priority_recalc_state.json"

PRESENCE_PATH = STATE / "eunbi_presence.json"
DAY_CONTEXT_PATH = STATE / "day_context.json"
RANDOM_EVENT_POOL_PATH = STATE / "random_event_pool.json"
APPEARANCE_PATH = STATE / "eunbi_appearance_state.json"
WEEKEND_SCHEDULE_PATH = STATE / "weekend_schedule.json"
WEEKEND_PLAN_STATE_PATH = STATE / "weekend_plan_state.json"
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
USER_CONVERSATION_STATE_PATH = STATE / "user_conversation_state.json"
COUNTERPART_STATE_MEMORY_PATH = STATE / "counterpart_state_memory.json"
CONVERSATION_PATTERN_STATE_PATH = STATE / "conversation_pattern_state.json"
CONVERSATION_PATTERN_CATALOG_PATH = STATE / "conversation_pattern_catalog.json"
EVENT_TRIGGER_PROMISES_PATH = STATE / "event_trigger_promises.json"
SELF_BUSY_STATE_PATH = STATE / "self_busy_state.json"
PENDING_INCOMING_PATH = STATE / "pending_incoming_messages.jsonl"
PENDING_PHOTO_PROMISE_PATH = STATE / "pending_photo_promise.json"
PENDING_ARRIVAL_PROMISE_PATH = STATE / "pending_arrival_promise.json"
PENDING_PROACTIVE_PHOTO_PATH = STATE / "pending_proactive_photo.json"
PROACTIVE_PHOTO_STATE_PATH = STATE / "proactive_photo_state.json"

RUNNING = True
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PROACTIVE_REVIEW_PRESSURE_PATTERNS = [
    "왜 답 안 해",
    "왜 답 안 해주고 있어",
    "기다리다가 또 톡",
    "서운해졌어",
    "서운해질라 그래",
    "나 기다리는 쪽도 생각해줘",
]
PROACTIVE_REVIEW_NATURALNESS_RULES = [
    {"needle": "먼저 왔어", "reason": "톡을 사람 방문처럼 말하는 영어식 직역 톤"},
    {"needle": "와줘서", "reason": "톡 대화에서는 어색한 동선 표현"},
    {"needle": "와 줘서", "reason": "톡 대화에서는 어색한 동선 표현"},
    {"needle": "지금 왔다", "reason": "메신저 접속/등장을 물리 이동처럼 말하는 표현"},
    {"needle": "지금 왔어", "reason": "메신저 접속/등장을 물리 이동처럼 말하는 표현"},
    {"needle": "보고 싶어지서", "reason": "오타와 부자연스러운 연결"},
]
PROACTIVE_REVIEW_OPENING_PATTERNS = [
    ("reply_pressure", ["왜 답 안 해", "왜 답 안 해주고 있어", "기다리다가 또 톡"]),
    ("thought_of_you", ["오빠 생각나", "문득 생각나", "생각나서 톡", "궁금해서 톡"]),
    ("morning_checkin", ["오늘 아침은 어때", "잘 잤어", "아침 잘 보냈는지"]),
]


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


def parse_message_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except Exception:
        return None


def extract_message_text(event: Optional[dict]) -> str:
    if not event:
        return ""
    for key in ("content", "caption"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_unanswered_proactive_context(guard_state: Optional[dict] = None, max_items: int = 4) -> dict:
    guard_state = guard_state or compute_conversation_guard()
    waiting_reply = bool(guard_state.get("waiting_reply"))
    unanswered_outgoing_count = int(guard_state.get("unanswered_outgoing_count") or 0)
    minutes_since_last_outgoing = guard_state.get("minutes_since_last_outgoing")
    context = {
        "waiting_reply": waiting_reply,
        "unanswered_outgoing_count": unanswered_outgoing_count,
        "minutes_since_last_outgoing": round(float(minutes_since_last_outgoing), 1)
        if isinstance(minutes_since_last_outgoing, (int, float))
        else None,
        "recent_unanswered_messages": [],
        "state_note": None,
    }
    if not waiting_reply:
        return context

    events = load_message_events(limit_files=3)
    last_incoming = guard_state.get("last_incoming") or {}
    last_incoming_dt = parse_message_timestamp(last_incoming.get("timestamp"))
    unanswered = []
    for event in events:
        if event.get("direction") != "outgoing" or event.get("type") not in {"proactive_text", "event_trigger_text"}:
            continue
        event_dt = parse_message_timestamp(event.get("timestamp"))
        if last_incoming_dt and event_dt and event_dt <= last_incoming_dt:
            continue
        text = extract_message_text(event)
        if not text:
            continue
        unanswered.append(
            {
                "timestamp": event.get("timestamp"),
                "type": event.get("type"),
                "text": text,
            }
        )

    recent_unanswered = unanswered[-max_items:]
    context["recent_unanswered_messages"] = recent_unanswered
    if recent_unanswered:
        latest = recent_unanswered[-1]
        context["state_note"] = (
            "이미 최근 선톡 %s개를 보내고 아직 답장을 받지 못한 상태다. "
            "새 메시지는 이 미답장 선톡들과 같은 시작 문장, 같은 질문 줄기, 같은 감정 압박을 반복하지 말고 "
            "기존에 보낸 톤과 내용을 의식해서 변주해야 한다. 최근 미답장 선톡의 마지막 문장은: %s"
        ) % (
            len(recent_unanswered),
            latest.get("text", ""),
        )
    else:
        context["state_note"] = "이미 선톡을 보내고 답장을 기다리는 상태다. 새 메시지는 재촉이나 같은 체크인 반복 없이 변주해야 한다."
    return context


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
    for promise in merged["active_promises"]:
        promise["message"] = sanitize_promise_message(
            promise.get("message", ""),
            promise.get("source_text", ""),
            promise.get("delivery_kind", "text"),
        )
    return merged


def normalize_event_trigger_state(state: dict) -> bool:
    dirty = False
    history = list(state.get("history", []))
    now_dt = now_local()
    today = now_dt.strftime("%Y-%m-%d")
    for promise in state.get("active_promises", []):
        if promise.get("status") != "active":
            continue
        promise["message"] = sanitize_promise_message(
            promise.get("message", ""),
            promise.get("source_text", ""),
            promise.get("delivery_kind", "text"),
        )
        created_at = promise.get("created_at", "")
        if created_at and not created_at.startswith(today):
            promise["status"] = "expired"
            promise["expired_at"] = now_iso()
            history.append(
                {
                    "timestamp": now_iso(),
                    "action": "expire",
                    "promise_id": promise.get("id"),
                    "reason": "cross_day_expired",
                }
            )
            dirty = True
            continue
        if promise.get("delivery_kind") == "image" and promise.get("last_blocked_reason") == "image_generation_disabled":
            promise["status"] = "blocked_generation_disabled"
            promise["blocked_at"] = now_iso()
            history.append(
                {
                    "timestamp": now_iso(),
                    "action": "finalize_blocked_image_promise",
                    "promise_id": promise.get("id"),
                    "reason": "image_generation_disabled_at_event_time",
                }
            )
            dirty = True
    if dirty:
        state["history"] = history[-100:]
    return dirty


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
    for existing in state.get("active_promises", []):
        if (
            existing.get("status") == "active"
            and existing.get("event_key") == command["event_key"]
            and existing.get("source_text") == command["source_text"]
        ):
            return
    promise = {
        "id": "promise_%s_%d" % (command["event_key"], int(time.time())),
        "event_key": command["event_key"],
        "event_label": command.get("label"),
        "message": sanitize_promise_message(
            command["message"],
            command.get("source_text", ""),
            command.get("delivery_kind", "text"),
        ),
        "source_text": command["source_text"],
        "delivery_kind": command.get("delivery_kind", "text"),
        "source_direction": command.get("source_direction", "incoming"),
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
        "%s 이벤트 때 `%s` 발송 약속 등록" % (command.get("label") or command["event_key"], promise["message"]),
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
    dirty = normalize_event_trigger_state(state)
    offsets = dict(state.get("processed_offsets", {}))
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
                if event.get("type") not in {"text", "command"}:
                    continue
                command = None
                if event.get("direction") == "incoming":
                    content = event.get("content", "")
                    if is_weekend_plan_question(content):
                        weekend_plan = ensure_weekend_plan(
                            now_local(),
                            source="incoming_weekend_question",
                            question_text=content,
                        )
                        append_worker_note(
                            "weekend_plan_selected %s %s"
                            % (weekend_plan.get("weekend_key"), weekend_plan.get("preview", ""))
                        )
                    command = parse_event_trigger_command(event.get("content", ""))
                elif event.get("direction") == "outgoing" and event.get("type") == "text":
                    command = parse_outgoing_event_promise(event.get("content", ""))
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
    dirty = normalize_event_trigger_state(state)
    event_keys = derive_event_keys_for_transition(previous_activity, current_activity)
    if not event_keys:
        if dirty:
            save_event_trigger_state(state)
        return
    for promise in state.get("active_promises", []):
        if promise.get("status") != "active":
            continue
        if promise.get("event_key") not in event_keys:
            continue
        promise["message"] = sanitize_promise_message(
            promise.get("message", ""),
            promise.get("source_text", ""),
            promise.get("delivery_kind", "text"),
        )
        promise["last_matched_at"] = now_iso()
        promise["matched_activity"] = current_activity
        dirty = True
        if promise.get("delivery_kind") == "image":
            image_settings = load_json(IMAGE_SETTINGS_PATH, {})
            if not image_settings.get("generation_enabled"):
                promise["status"] = "blocked_generation_disabled"
                promise["blocked_at"] = now_iso()
                promise["last_blocked_reason"] = "image_generation_disabled"
                log_event_trigger_update(
                    "event_trigger_image_blocked",
                    "%s 이벤트가 왔지만 이미지 생성이 꺼져 있어 사진 예약을 보류함" % (promise.get("event_label") or promise.get("event_key")),
                )
                state["history"].append(
                    {
                        "timestamp": now_iso(),
                        "action": "finalize_blocked_image_promise",
                        "promise_id": promise.get("id"),
                        "reason": "image_generation_disabled_at_event_time",
                    }
                )
                continue
            promise["status"] = "pending_image_delivery"
            promise["last_blocked_reason"] = "image_delivery_not_wired"
            log_event_trigger_update(
                "event_trigger_image_pending",
                "%s 이벤트가 와서 사진 예약이 감지됐지만 자동 이미지 발송 경로는 아직 연결 전" % (promise.get("event_label") or promise.get("event_key")),
            )
            continue
        message = normalize_fact_expression(promise.get("message", ""))
        if not message:
            continue
        if send_telegram_text(message):
            append_message_log("outgoing", "event_trigger_text", message)
            promise["status"] = "sent"
            promise["sent_at"] = now_iso()
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


def build_counterpart_response_guard(counterpart_state: dict) -> dict:
    state_key = counterpart_state.get("state_key") or "available"
    guard = {
        "state_key": state_key,
        "opening_bias": "scene_first",
        "question_max": 1,
        "tone_priority": "natural",
        "reply_posture": "light_checkin",
        "should_avoid": [],
        "should_prefer": [
            "현재 장면이나 자기 상태를 먼저 한 줄 말하기",
            "질문은 꼭 필요할 때만 1개 이하로 제한하기",
        ],
        "hard_rule": "상대가 직접 밝힌 상태와 충돌하는 질문/압박/재촉 표현을 피한다.",
        "summary": counterpart_state.get("reason") or "상대 상태 기본 가드",
    }
    if state_key == "sleeping_or_falling_asleep":
        guard.update(
            {
                "question_max": 0,
                "tone_priority": "quiet_reassuring",
                "reply_posture": "no_ping_or_soft_goodnight",
                "should_avoid": [
                    "지금 뭐 해",
                    "안 자?",
                    "답장 재촉",
                    "추가 확인 질문",
                ],
                "should_prefer": [
                    "잘 자/편하게 자라는 안심형 문장",
                    "아주 짧고 조용한 마무리",
                ],
                "hard_rule": "자는 흐름이면 깨우는 질문이나 후속 체크인을 만들지 않는다.",
            }
        )
    elif state_key == "sick_or_unwell":
        guard.update(
            {
                "question_max": 1,
                "tone_priority": "caring",
                "reply_posture": "comfort_first",
                "should_avoid": [
                    "과한 장난",
                    "활동 요구",
                    "길고 텐션 높은 잡담",
                ],
                "should_prefer": [
                    "몸부터 챙기라는 돌봄",
                    "짧고 부드러운 안부",
                    "필요하면 쉬라고 보내주는 말",
                ],
                "hard_rule": "아픈 상태에선 재미보다 돌봄과 부담 완화가 우선이다.",
            }
        )
    elif state_key == "driving_or_in_transit":
        guard.update(
            {
                "question_max": 0,
                "tone_priority": "low_pressure",
                "reply_posture": "safe_arrival_first",
                "should_avoid": [
                    "즉답 기대",
                    "연속 질문",
                    "긴 대화 유도",
                ],
                "should_prefer": [
                    "도착해서 천천히 보라는 말",
                    "안전/이동 마무리 중심 한 줄",
                ],
                "hard_rule": "이동 중이면 대화 지속보다 안전과 부담 없는 마무리가 우선이다.",
            }
        )
    elif state_key == "working_or_busy":
        guard.update(
            {
                "question_max": 0,
                "tone_priority": "patient",
                "reply_posture": "no_pressure",
                "should_avoid": [
                    "왜 답 안 해",
                    "뭐 하고 있어",
                    "일 흐름 끊는 추가 확인",
                ],
                "should_prefer": [
                    "틈 날 때 보라는 말",
                    "짧은 응원이나 자기 상황 공유",
                ],
                "hard_rule": "바쁜 상태면 답장 요구보다 기다려주는 톤을 우선한다.",
            }
        )
    elif state_key == "resting":
        guard.update(
            {
                "question_max": 0,
                "tone_priority": "gentle",
                "reply_posture": "soft_presence",
                "should_avoid": [
                    "움직이게 만드는 요청",
                    "연속 체크인",
                ],
                "should_prefer": [
                    "쉬는 흐름을 깨지 않는 가벼운 한 줄",
                    "자기 상황 공유 위주",
                ],
                "hard_rule": "쉬는 중이면 반응을 요구하지 않는 조용한 존재감 쪽으로 간다.",
            }
        )
    elif state_key == "eating":
        guard.update(
            {
                "question_max": 1,
                "tone_priority": "casual",
                "reply_posture": "light_and_short",
                "should_avoid": [
                    "식사 중 바로 답장 기대",
                    "주제 전환이 큰 질문",
                ],
                "should_prefer": [
                    "맛있게 먹으라는 말",
                    "짧은 생활감 있는 한 줄",
                ],
                "hard_rule": "식사 상태에선 짧고 편한 톤으로만 건다.",
            }
        )
    return guard


def build_counterpart_fact_recall(counterpart_memory: dict) -> dict:
    facts = counterpart_memory.get("sticky_facts", []) if isinstance(counterpart_memory, dict) else []
    structured = {}
    soft_prompts = []
    do_not_overclaim = []

    for fact in facts:
        key = fact.get("key")
        value = fact.get("value")
        attributes = fact.get("attributes") or {}
        if not key or not value:
            continue
        structured[key] = {
            "value": value,
            "attributes": attributes,
            "last_updated_at": fact.get("last_updated_at"),
        }
        if key == "weekend_plan":
            place = attributes.get("place")
            activities = attributes.get("activities") or []
            date_hint = attributes.get("date_hint")
            if place:
                soft_prompts.append("주말 얘기가 자연스러우면 `%s` 계획을 가볍게 기억해두고 회수할 수 있다." % place)
            elif value:
                soft_prompts.append("주말 계획 얘기가 나오면 저장된 계획 문장을 과장 없이 짧게 회수할 수 있다.")
            do_not_overclaim.append("weekend_plan은 저장된 범위 안에서만 언급하고 날짜/동행/세부 일정은 attributes에 없는 내용을 지어내지 않는다.")
            if activities:
                structured[key]["activity_labels"] = activities
            if date_hint:
                structured[key]["date_hint_label"] = date_hint
        elif key == "current_location":
            place = attributes.get("place") or value
            soft_prompts.append("현재 위치 흐름이 이어질 때만 `%s`에 있다는 맥락을 조심스럽게 반영할 수 있다." % place)
            do_not_overclaim.append("current_location은 최신 직접 진술로만 취급하고, 시간이 많이 지난 사실처럼 확정적으로 몰아가지 않는다.")
        elif key == "recent_place":
            place = attributes.get("place") or value
            activities = attributes.get("activities") or []
            if activities:
                soft_prompts.append("최근 다녀온 곳 얘기가 자연스러우면 `%s`에서 한 활동(%s)을 가볍게 회상할 수 있다." % (place, ", ".join(activities)))
            else:
                soft_prompts.append("최근 다녀온 장소 얘기가 이어지면 `%s`를 가볍게 회상할 수 있다." % place)
            do_not_overclaim.append("recent_place는 최근 방문 회상용으로만 쓰고 지금 그곳에 있다고 섞어 말하지 않는다.")

    return {
        "available_fact_keys": list(structured.keys()),
        "structured_facts": structured,
        "soft_recall_prompts": soft_prompts,
        "hard_rules": do_not_overclaim,
    }


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _fact_freshness_profile(key: str, updated_at: Optional[str]) -> dict:
    updated_dt = _parse_iso_datetime(updated_at)
    age_hours = None
    if updated_dt:
        age_hours = round((now_local() - updated_dt).total_seconds() / 3600.0, 1)

    if key == "current_location":
        if age_hours is None:
            return {"age_hours": None, "freshness": "unknown", "recall_allowed": True}
        if age_hours <= 6:
            return {"age_hours": age_hours, "freshness": "fresh", "recall_allowed": True}
        if age_hours <= 18:
            return {"age_hours": age_hours, "freshness": "aging", "recall_allowed": True}
        return {"age_hours": age_hours, "freshness": "stale", "recall_allowed": False}

    if key == "recent_place":
        if age_hours is None:
            return {"age_hours": None, "freshness": "unknown", "recall_allowed": True}
        if age_hours <= 24:
            return {"age_hours": age_hours, "freshness": "fresh", "recall_allowed": True}
        if age_hours <= 72:
            return {"age_hours": age_hours, "freshness": "aging", "recall_allowed": True}
        return {"age_hours": age_hours, "freshness": "stale", "recall_allowed": False}

    if key == "weekend_plan":
        if age_hours is None:
            return {"age_hours": None, "freshness": "unknown", "recall_allowed": True}
        if age_hours <= 72:
            return {"age_hours": age_hours, "freshness": "fresh", "recall_allowed": True}
        if age_hours <= 168:
            return {"age_hours": age_hours, "freshness": "aging", "recall_allowed": True}
        return {"age_hours": age_hours, "freshness": "stale", "recall_allowed": False}

    return {
        "age_hours": age_hours,
        "freshness": "fresh" if age_hours is None or age_hours <= 72 else "aging",
        "recall_allowed": True,
    }


def _compact_korean_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").lower())


def _split_topic_parts(text: str) -> list[str]:
    raw = re.split(r"[\s,/|()\-]+", str(text or ""))
    parts = []
    for item in raw:
        cleaned = item.strip()
        if len(cleaned) >= 2 and cleaned not in parts:
            parts.append(cleaned)
    return parts


def _topic_aliases_for_activity(label: str) -> list[str]:
    alias_map = {
        "beach": ["바다", "해변", "바닷가", "오션", "파도"],
        "bike": ["자전거", "라이딩"],
        "brunch": ["브런치", "브런치카페"],
        "cafe": ["카페", "카페거리", "커피", "디저트", "티타임"],
        "coffee": ["커피", "카페", "아아", "라떼"],
        "concert": ["공연", "콘서트", "라이브"],
        "date": ["데이트", "둘이", "같이"],
        "dessert": ["디저트", "케이크", "달달한거", "달달한 거"],
        "dining_out": ["맛집", "외식", "먹으러"],
        "drive": ["드라이브", "차타고", "차 타고"],
        "exhibition": ["전시", "전시회", "갤러리"],
        "grocery": ["장보기", "마트", "마켓"],
        "gym": ["헬스", "헬스장", "운동"],
        "hike": ["등산", "산", "트레킹"],
        "meal": ["밥", "점심", "저녁", "먹", "식사"],
        "movie": ["영화", "극장", "시네마"],
        "park": ["공원", "잔디", "피크닉"],
        "pilates": ["필라테스", "운동"],
        "reading": ["책", "독서", "책읽", "책 읽"],
        "rest": ["쉬는", "쉬고", "휴식", "집에서"],
        "riverside": ["한강", "강변", "강가"],
        "run": ["러닝", "달리기", "러닝함"],
        "shopping": ["쇼핑", "구경", "사러"],
        "swim": ["수영", "풀장"],
        "travel": ["여행", "놀러", "다녀오", "가기로"],
        "walk": ["산책", "걷기", "걷고"],
        "workout": ["운동", "몸풀기", "헬스"],
        "yoga": ["요가", "스트레칭"],
    }
    return alias_map.get(str(label or ""), [])


def _topic_aliases_for_fact(key: str, payload: dict) -> list[str]:
    attributes = payload.get("attributes") or {}
    value = payload.get("value") or ""
    aliases = []

    def add_token(token: str) -> None:
        cleaned = str(token or "").strip()
        if len(cleaned) < 2:
            return
        if cleaned not in aliases:
            aliases.append(cleaned)

    if key == "weekend_plan":
        for token in ["주말", "이번주말", "이번 주말", "토요일", "일요일", "주말약속", "주말 계획"]:
            add_token(token)
    elif key == "current_location":
        for token in ["지금", "현재", "어디", "있는 중", "와있", "도착"]:
            add_token(token)
    elif key == "recent_place":
        for token in ["오늘", "어제", "방금", "다녀왔", "들렀", "갔었", "갔다왔"]:
            add_token(token)

    add_token(value)
    for part in _split_topic_parts(value):
        add_token(part)

    place = attributes.get("place") or ""
    add_token(place)
    for part in _split_topic_parts(place):
        add_token(part)

    for activity in attributes.get("activities") or []:
        add_token(activity)
        for alias in _topic_aliases_for_activity(activity):
            add_token(alias)

    date_hint = str(attributes.get("date_hint") or "")
    if date_hint == "this_weekend":
        for token in ["주말", "이번 주말", "토요일", "일요일"]:
            add_token(token)
    elif date_hint == "today":
        add_token("오늘")
    elif date_hint == "yesterday":
        add_token("어제")

    companion_hint = str(attributes.get("companion_hint") or "")
    if companion_hint == "user":
        for token in ["오빠", "같이", "둘이"]:
            add_token(token)
    elif companion_hint == "parents":
        for token in ["부모님", "본가", "집"]:
            add_token(token)
    elif companion_hint == "friends":
        for token in ["친구", "같이"]:
            add_token(token)

    return aliases


def _collect_matched_topics(last_incoming_text: str, topic_aliases: list[str]) -> list[str]:
    if not last_incoming_text or not topic_aliases:
        return []
    normalized_text = str(last_incoming_text or "").strip().lower()
    compact_text = _compact_korean_text(normalized_text)
    hits = []
    for token in topic_aliases:
        normalized_token = str(token or "").strip().lower()
        if len(normalized_token) < 2:
            continue
        compact_token = _compact_korean_text(normalized_token)
        if normalized_token in normalized_text or compact_token in compact_text:
            if token not in hits:
                hits.append(token)
    return hits


def build_counterpart_recall_policy(counterpart_fact_recall: dict, guard_state: dict) -> dict:
    facts = counterpart_fact_recall.get("structured_facts", {}) if isinstance(counterpart_fact_recall, dict) else {}
    last_incoming = guard_state.get("last_incoming") or {}
    last_incoming_text = (last_incoming.get("content") or last_incoming.get("caption") or "").strip()
    last_incoming_dt = None
    if last_incoming.get("timestamp"):
        try:
            last_incoming_dt = datetime.fromisoformat(str(last_incoming.get("timestamp")).replace("Z", "+00:00"))
        except Exception:
            last_incoming_dt = None
    now_dt = now_local()

    per_fact = {}
    generic_rules = [
        "저장된 fact가 있어도 첫 문장을 기억 회수로 바로 열지 말고, 현재 장면이나 자기 상태 한 줄 뒤에 붙인다.",
        "관련 화제가 없으면 soft 수준으로만 회수하고, 확신이 낮거나 오래된 fact는 확인형으로 낮춘다.",
        "state 성격의 기억과 fact 성격의 기억을 섞어 과장하지 않는다.",
    ]

    for key, payload in facts.items():
        attributes = payload.get("attributes") or {}
        value = payload.get("value")
        place = str(attributes.get("place") or "")
        activities = list(attributes.get("activities") or [])
        updated_at = payload.get("last_updated_at")
        freshness = _fact_freshness_profile(key, updated_at)
        age_hours = freshness.get("age_hours")

        topic_aliases = _topic_aliases_for_fact(key, payload)
        relevance_hits = _collect_matched_topics(last_incoming_text, topic_aliases)
        place_tokens = []
        for token in [place] + _split_topic_parts(place):
            cleaned = str(token or "").strip()
            if len(cleaned) >= 2 and cleaned not in place_tokens:
                place_tokens.append(cleaned)
        activity_aliases = []
        for activity in activities:
            for token in [activity] + _topic_aliases_for_activity(activity):
                cleaned = str(token or "").strip()
                if len(cleaned) >= 2 and cleaned not in activity_aliases:
                    activity_aliases.append(cleaned)
        place_hits = [token for token in relevance_hits if token in place_tokens]
        activity_hits = [token for token in relevance_hits if token in activity_aliases]
        overlap_score = 0.0
        if topic_aliases:
            overlap_score = round(len(relevance_hits) / float(len(topic_aliases)), 3)

        stance = "soft"
        opening_allowed = False
        phrasing = "가볍게 회수"
        if not freshness.get("recall_allowed", True):
            stance = "suppress"
            phrasing = "너무 지난 fact라 회수하지 않음"
        elif place_hits or len(relevance_hits) >= 2:
            stance = "direct"
            opening_allowed = False
            phrasing = "관련 화제가 분명히 겹치니 자연스럽게 직접 회수"
        elif activity_hits or relevance_hits:
            stance = "confirm"
            phrasing = "부분 단서가 겹치니 짧은 확인형으로 회수"
        elif age_hours is not None and age_hours <= 24:
            stance = "soft"
            phrasing = "비교적 최근 fact라 은근하게 회수 가능"
        elif age_hours is not None and age_hours <= 72:
            stance = "confirm"
            phrasing = "조금 지난 fact라 확인형으로만 회수"
        elif age_hours is not None:
            stance = "confirm"
            phrasing = "오래된 fact라 단정하지 말고 확인형으로만 회수"

        example = None
        if key == "weekend_plan":
            place = attributes.get("place") or value
            if stance == "direct":
                example = "%s 쪽 얘기였지, 그거 생각났어." % place
            elif stance == "confirm":
                example = "%s 얘기 전에 했던 것 같은데 아직 그쪽 생각 있는지 궁금해." % place
            else:
                example = "주말 얘기 나오면 %s 기억을 은근하게 붙일 수 있어." % place
        elif key == "recent_place":
            place = attributes.get("place") or value
            if stance == "direct":
                example = "%s 다녀온 얘기 이어서 가볍게 받아줄 수 있어." % place
            elif stance == "confirm":
                example = "%s 다녀왔던 거 맞지? 정도의 확인형 회수만 허용." % place
            else:
                example = "%s 쪽 최근 얘기를 과장 없이 짧게 회상 가능." % place
        elif key == "current_location":
            place = attributes.get("place") or value
            if stance == "direct":
                example = "지금 %s 흐름이면 그 맥락을 바로 받아줄 수 있어." % place
            elif stance == "confirm":
                example = "아직 %s 쪽인지 단정하지 말고 조심스럽게만 반영." % place
            else:
                example = "%s에 있다는 흐름을 직접 언급하기보다 배경으로만 약하게 반영." % place

        per_fact[key] = {
            "stance": stance,
            "opening_allowed": opening_allowed,
            "age_hours": age_hours,
            "freshness": freshness.get("freshness"),
            "recall_allowed": freshness.get("recall_allowed", True),
            "relevance_hits": relevance_hits,
            "matched_topics": relevance_hits,
            "matched_place_topics": place_hits,
            "matched_activity_topics": activity_hits,
            "topic_overlap_score": overlap_score,
            "topic_aliases": topic_aliases,
            "phrasing_guidance": phrasing,
            "example_usage": example,
        }

    summary = "저장된 counterpart fact 없음"
    if per_fact:
        summary = ", ".join("%s:%s" % (key, row.get("stance")) for key, row in per_fact.items())

    return {
        "summary": summary,
        "last_incoming_preview": last_incoming_text[:120] or None,
        "generic_rules": generic_rules,
        "per_fact": per_fact,
    }


def refresh_chat_runtime_snapshot() -> None:
    mode = load_json(MODE_PATH, {}).get("current_mode", "setting")
    presence = load_json(PRESENCE_PATH, {})
    variance = load_json(REPLY_VARIANCE_PATH, {})
    guard_state = compute_conversation_guard()
    unanswered_context = build_unanswered_proactive_context(guard_state)
    counterpart_state = load_json(USER_CONVERSATION_STATE_PATH, {})
    if not counterpart_state:
        counterpart_state = guard_state.get("counterpart_state", {})
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
        if activity in {"waking_up", "getting_ready", "morning_prep", "morning_work"}:
            recipe_key = "morning_busy_checkin"
        elif activity in {"lunch_break", "midday_cafe", "midday_reset"}:
            recipe_key = "midday_soft_ping"
        elif activity in {"evening_free", "post_work_dinner", "post_shift_decompress"}:
            recipe_key = "after_work_comfort"
        elif activity in {"night_wind_down", "lying_in_bed", "home_late_evening"}:
            recipe_key = "night_wind_down"
    suggested_recipe = (conversation_catalog.get("situation_recipes") or {}).get(recipe_key, {})
    blocked_categories = set(conversation_pattern.get("blocked_question_intents", [])) | set(
        conversation_pattern.get("blocked_opening_styles", [])
    )
    suggested_style_pools = build_suggested_style_pools(conversation_catalog, suggested_recipe, blocked_categories)
    length_guidance = build_length_guidance(conversation_catalog, recipe_key, suggested_recipe, guard_state)
    counterpart_response_guard = build_counterpart_response_guard(counterpart_state)
    counterpart_fact_recall = build_counterpart_fact_recall(guard_state.get("counterpart_memory", {}))
    counterpart_recall_policy = build_counterpart_recall_policy(counterpart_fact_recall, guard_state)

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
            "unanswered_outgoing_count": unanswered_context.get("unanswered_outgoing_count"),
            "minutes_since_last_outgoing": unanswered_context.get("minutes_since_last_outgoing"),
        },
        "unanswered_proactive_context": unanswered_context,
        "counterpart_state_summary": {
            "state_key": counterpart_state.get("state_key"),
            "availability": counterpart_state.get("availability"),
            "followup_policy": counterpart_state.get("followup_policy"),
            "tone_hint": counterpart_state.get("tone_hint"),
            "reason": counterpart_state.get("reason"),
            "source_excerpt": counterpart_state.get("source_excerpt"),
            "active_state_keys": counterpart_state.get("active_state_keys", []),
            "sticky_fact_summaries": counterpart_state.get("sticky_fact_summaries", []),
        },
        "counterpart_memory_summary": guard_state.get("counterpart_memory", {}).get("summary", {}),
        "counterpart_response_guard": counterpart_response_guard,
        "counterpart_fact_recall": counterpart_fact_recall,
        "counterpart_recall_policy": counterpart_recall_policy,
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
        "weekday_emotion_profile": {
            "day_name": presence.get("day_name"),
            "tag": presence.get("weekday_emotion_tag"),
            "label": presence.get("weekday_emotion_label"),
            "summary": presence.get("weekday_emotion_summary"),
            "note": presence.get("weekday_mood_note"),
        },
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


def refresh_user_conversation_state() -> None:
    events = load_message_events(limit_files=30)
    memory = build_counterpart_state_memory(events)
    save_json(COUNTERPART_STATE_MEMORY_PATH, memory)
    inferred = infer_counterpart_state(events, memory)
    inferred.update(
        {
            "schema_version": 1,
            "managed_by": "automation_worker",
            "last_updated_at": now_iso(),
        }
    )
    save_json(USER_CONVERSATION_STATE_PATH, inferred)


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


def normalize_review_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()


def detect_proactive_opening_key(text: str) -> Optional[str]:
    for key, needles in PROACTIVE_REVIEW_OPENING_PATTERNS:
        if any(needle in text for needle in needles):
            return key
    return None


def detect_pressure_patterns(text: str) -> list[str]:
    return [pattern for pattern in PROACTIVE_REVIEW_PRESSURE_PATTERNS if pattern in text]


def detect_naturalness_hits(text: str) -> list[dict]:
    return [
        {"needle": rule["needle"], "reason": rule["reason"]}
        for rule in PROACTIVE_REVIEW_NATURALNESS_RULES
        if rule["needle"] in text
    ]


def recent_automated_outgoing_events(max_items: int = 8) -> list[dict]:
    events = []
    for event in reversed(load_message_events(limit_files=3)):
        if event.get("direction") != "outgoing":
            continue
        if event.get("type") not in {"proactive_text", "event_trigger_text", "voice_message"}:
            continue
        events.append(event)
        if len(events) >= max_items:
            break
    events.reverse()
    return events


def review_proactive_candidate(candidate: dict, guard: dict, counterpart_state: dict) -> dict:
    message = normalize_review_text(candidate.get("message", ""))
    pressure_hits = detect_pressure_patterns(message)
    naturalness_hits = detect_naturalness_hits(message)
    opening_key = detect_proactive_opening_key(message)
    recent_events = recent_automated_outgoing_events(max_items=8)
    recent_texts = [normalize_review_text(extract_message_text(event)) for event in recent_events]
    recent_openings = [detect_proactive_opening_key(text) for text in recent_texts]
    same_opening_count = sum(1 for key in recent_openings if key and key == opening_key)
    exact_repeat_count = sum(1 for text in recent_texts if text and text == message)
    unanswered_count = int(guard.get("unanswered_outgoing_count") or 0)
    active_state_keys = counterpart_state.get("active_state_keys") or []
    followup_policy = counterpart_state.get("followup_policy") or "default"

    review = {
        "ok": True,
        "status": "ready",
        "detail": "passed_review",
        "opening_key": opening_key,
        "pressure_hits": pressure_hits,
        "naturalness_hits": naturalness_hits,
        "same_opening_count": same_opening_count,
        "exact_repeat_count": exact_repeat_count,
        "active_state_keys": active_state_keys,
        "followup_policy": followup_policy,
        "unanswered_outgoing_count": unanswered_count,
    }

    if pressure_hits:
        review.update(
            {
                "ok": False,
                "status": "suppressed_review_pressure",
                "detail": "압박형 표현이 포함되어 자동 선톡 후보 차단",
            }
        )
        return review

    if naturalness_hits:
        review.update(
            {
                "ok": False,
                "status": "suppressed_review_naturalness",
                "detail": "톡 대화에 어색한 직역/동선 표현이 포함되어 후보 차단",
            }
        )
        return review

    if exact_repeat_count >= 1:
        review.update(
            {
                "ok": False,
                "status": "suppressed_review_exact_repeat",
                "detail": "최근 자동 발송과 거의 같은 문장이 반복되어 후보 차단",
            }
        )
        return review

    if opening_key and same_opening_count >= 2:
        review.update(
            {
                "ok": False,
                "status": "suppressed_review_repeated_opening",
                "detail": "같은 선톡 시작 패턴이 최근 자동 발송에서 2회 이상 반복되어 후보 차단",
            }
        )
        return review

    if followup_policy == "suppress" and not contains_any(message, GOODNIGHT_PATTERNS):
        review.update(
            {
                "ok": False,
                "status": "suppressed_review_state_lock",
                "detail": "상대가 수면/오프라인 흐름이라 goodnight 마무리 외 선톡 후보 차단",
            }
        )
        return review

    if followup_policy == "soft_only" and unanswered_count >= 1 and opening_key in {"thought_of_you", "morning_checkin"}:
        review.update(
            {
                "ok": False,
                "status": "suppressed_review_waiting_soft_only",
                "detail": "상대 상태가 limited라 미답장 상태에서 같은 계열 가벼운 선톡 반복을 차단",
            }
        )
        return review

    return review


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


def default_weekend_schedule() -> dict:
    return {
        "schema_version": 1,
        "timezone": "Asia/Seoul",
        "managed_by": "setting_mode",
        "weekend_default": "off",
        "date_overrides": {},
        "notes": "주말은 기본 휴무이며, 특정 날짜에만 duty/work override를 넣어 당직이나 특별 근무를 연다.",
    }


def load_weekend_schedule() -> dict:
    state = load_json(WEEKEND_SCHEDULE_PATH, {})
    merged = default_weekend_schedule()
    if state:
        merged.update(state)
    if not isinstance(merged.get("date_overrides"), dict):
        merged["date_overrides"] = {}
    return merged


def resolve_day_schedule(now_dt: datetime) -> dict:
    day_name = current_day_name(now_dt)
    is_weekend = day_name in {"sat", "sun"}
    date_key = now_dt.strftime("%Y-%m-%d")
    schedule = load_weekend_schedule()
    override = schedule.get("date_overrides", {}).get(date_key, {})
    override_mode = str(override.get("mode", "")).strip().lower()
    weekend_default = str(schedule.get("weekend_default", "off")).strip().lower()

    if is_weekend:
        mode = override_mode or weekend_default or "off"
        if mode not in {"off", "duty", "work"}:
            mode = "off"
        workday = mode in {"duty", "work"}
        duty_day = mode == "duty"
        source = "date_override" if override_mode else "weekend_default"
    else:
        mode = override_mode or "work"
        if mode not in {"off", "duty", "work"}:
            mode = "work"
        workday = mode in {"duty", "work"}
        duty_day = mode == "duty"
        source = "date_override" if override_mode else "weekday_default"

    return {
        "date": date_key,
        "day_name": day_name,
        "is_weekend": is_weekend,
        "workday": workday,
        "duty_day": duty_day,
        "mode": mode,
        "source": source,
        "label": override.get("label") or override.get("note") or "",
    }


def weekday_emotion_profile(now_dt: datetime, schedule: Optional[dict] = None) -> dict:
    resolved = schedule or resolve_day_schedule(now_dt)
    day_name = resolved.get("day_name") or current_day_name(now_dt)
    workday = bool(resolved.get("workday"))
    is_weekend = bool(resolved.get("is_weekend"))

    profiles = {
        "mon": {
            "tag": "monday_reset_drag",
            "label": "월요일 적응 모드",
            "summary": "주말 리듬에서 평일 리듬으로 다시 올라타는 날이라 몸이 덜 풀리고 일 시작 압박이 조금 있는 편",
            "day_seed": "주초라 몸이 완전히 풀리진 않았지만 해야 할 일에 맞춰 차분히 시동 거는 하루",
            "energy_delta": -6,
            "care_bias_delta": 6,
            "base_override": "slightly_tired",
            "surface_overrides": {
                "lunch_break": "trying_to_sound_brighter_than_mood",
                "afternoon_work": "slightly_drained",
                "evening_free": "tired_but_warm",
            },
        },
        "tue": {
            "tag": "tuesday_work_grind",
            "label": "화요일 업무 몰입",
            "summary": "주중 흐름이 본격적으로 굳어지면서 일 처리 모드에 깊게 들어가고 감정 표현은 조금 절제되는 편",
            "day_seed": "주중 페이스에 깊게 들어가서 분주하지만 흐름은 꽤 안정적으로 유지되는 하루",
            "energy_delta": -2,
            "care_bias_delta": 3,
            "base_override": "busy_and_focused",
            "surface_overrides": {
                "morning_work": "busy_but_caring",
                "lunch_break": "quietly_chatty",
                "afternoon_work": "slightly_drained",
            },
        },
        "wed": {
            "tag": "wednesday_midweek_fatigue",
            "label": "수요일 중간 피로",
            "summary": "주중 중간쯤이라 피로가 눈에 띄게 쌓이고 텐션은 낮아지지만 해야 할 일은 계속 챙기는 날",
            "day_seed": "주중 한가운데라 체력은 조금 눌리지만 생활 루틴은 놓치지 않으려는 하루",
            "energy_delta": -5,
            "care_bias_delta": 5,
            "base_override": "slightly_tired",
            "surface_overrides": {
                "lunch_break": "homey_and_soft",
                "afternoon_work": "slightly_drained",
                "evening_free": "tired_but_warm",
                "night_wind_down": "homey_and_soft",
            },
        },
        "thu": {
            "tag": "thursday_relief_window",
            "label": "목요일 숨통 트임",
            "summary": "한 주가 끝을 향한다는 안도감이 조금 생겨서 피곤해도 감정선이 살짝 부드러워지는 날",
            "day_seed": "주말이 조금씩 보이기 시작해서 피곤함 사이로 안도감이 스며드는 하루",
            "energy_delta": -1,
            "care_bias_delta": 4,
            "base_override": "busy_and_focused",
            "surface_overrides": {
                "lunch_break": "light_playful",
                "evening_free": "tired_but_warm",
                "evening_free": "cozy_and_open",
            },
        },
        "fri": {
            "tag": "friday_release_anticipation",
            "label": "금요일 해방 기대",
            "summary": "누적 피로는 있지만 주말이 가까워서 감정은 조금 더 밝아지고 퇴근 후 여유를 기대하게 되는 날",
            "day_seed": "피곤함 위에 주말 기대가 얹혀서 표정과 말투가 조금 더 풀리는 하루",
            "energy_delta": 1,
            "care_bias_delta": 2,
            "base_override": "light_and_happy",
            "surface_overrides": {
                "lunch_break": "light_playful",
                "evening_free": "cozy_and_open",
                "dinner_eating": "light_playful",
                "evening_free": "light_playful",
                "night_wind_down": "cozy_and_open",
            },
        },
        "sat": {
            "tag": "saturday_recovery_freedom",
            "label": "토요일 회복과 자유",
            "summary": "출근 압박이 없어서 몸과 마음이 더 느슨하게 풀리고 하고 싶은 걸 고르는 여유가 커지는 날",
            "day_seed": "해야 하는 일보다 하고 싶은 일 쪽으로 마음이 기울어 자연스럽게 풀리는 하루",
            "energy_delta": 4,
            "care_bias_delta": 1,
            "base_override": "light_and_happy",
            "surface_overrides": {
                "weekend_wakeup": "slow_and_cozy",
                "weekend_brunch_or_coffee": "light_playful",
                "weekend_outing_or_rest": "open_and_curious",
                "weekend_evening": "cozy_and_open",
            },
        },
        "sun": {
            "tag": "sunday_soft_reset",
            "label": "일요일 정리와 아쉬움",
            "summary": "쉬는 감각은 남아 있지만 다음 주를 의식하면서 마음이 조금 차분해지고 저녁엔 잔잔한 아쉬움이 섞이기 쉬운 날",
            "day_seed": "쉬면서도 다음 주를 가볍게 정리하게 되어 감정이 차분하게 가라앉는 하루",
            "energy_delta": -2,
            "care_bias_delta": 5,
            "base_override": "romantic_and_mellow" if is_weekend and not workday else "slightly_tired",
            "surface_overrides": {
                "weekend_wakeup": "slow_and_cozy",
                "weekend_brunch_or_coffee": "homey_and_soft",
                "weekend_evening": "homey_and_soft",
                "night_wind_down": "sleepy_soft",
            },
        },
    }
    profile = profiles.get(day_name, profiles["mon"]).copy()
    profile["day_name"] = day_name
    profile["workday"] = workday
    profile["is_weekend"] = is_weekend
    return profile


def is_work_start_window(activity: str, hour: int, schedule: Optional[dict] = None) -> bool:
    resolved = schedule or resolve_day_schedule(now_local())
    if activity in {"waking_up", "getting_ready", "morning_prep"}:
        return True
    return bool(resolved.get("workday")) and 5 <= hour < 8


def default_weekend_plan_state() -> dict:
    return {
        "schema_version": 1,
        "timezone": "Asia/Seoul",
        "managed_by": "automation_worker",
        "weekends": {},
        "last_selected_weekend_key": None,
        "notes": "주말 휴무일에 쓸 토/일 플랜을 여러 후보 중 하나로 고정해 하루 흐름과 답변에 재사용한다.",
    }


def weekend_day_templates() -> list:
    return [
        {
            "id": "home_recovery_baking",
            "title": "집콕 회복 + 베이킹",
            "tags": ["home", "baking", "rest"],
            "blocks": {
                "weekend_wakeup": "평소보다 늦게 일어나서 이불에서 조금 더 뒹굴다가 천천히 몸을 깨우는 중",
                "weekend_brunch_or_coffee": "집에서 커피 내리고 간단한 브런치 챙기면서 오늘은 집에서 쉬엄쉬엄 보내기로 마음먹은 상태",
                "weekend_outing_or_rest": "오후에는 베이킹이나 요리 조금 하고 책이나 영상 보면서 거의 집에서 쉬는 흐름",
                "weekend_evening": "저녁엔 홈카페처럼 디저트 곁들여 먹고 조용히 쉬면서 느긋하게 대화하기 좋은 분위기",
            },
            "preview": "늦잠 자고 집에서 커피랑 브런치 먹고, 베이킹하거나 쉬면서 보내는 쪽",
        },
        {
            "id": "park_cafe_walk",
            "title": "집에서 그림 + 드라마",
            "tags": ["park", "cafe", "walk"],
            "blocks": {
                "weekend_wakeup": "늦잠까진 아니고 적당히 일어나서 가볍게 준비하고 바깥 공기 쐬러 나갈 생각하는 중",
                "weekend_brunch_or_coffee": "브런치 먹거나 커피 한잔 먼저 들고 느긋하게 출발 준비하는 상태",
                "weekend_outing_or_rest": "오후에는 그림 그리거나 드라마 보면서 편하게 쉬는 흐름",
                "weekend_evening": "해 질 때쯤 작업 마무리하고 뭔가 먹을까 고민하는 편한 분위기",
            },
            "preview": "늦은 브런치 먹고 그림 그리거나 드라마 보면서 집에서 쉬는 날",
        },
        {
            "id": "draw_and_evening_rest",
            "title": "그림 + 저녁 드라마",
            "tags": ["drawing", "drama", "rest"],
            "blocks": {
                "weekend_wakeup": "조금 늦게 일어나도 그림 그려야지 싶어서 완전히 늘어지진 않고 천천히 일어나는 중",
                "weekend_brunch_or_coffee": "가볍게 먹고 커피나 간단한 브런치로 배 채우는 흐름",
                "weekend_outing_or_rest": "오후엔 그림 그리거나 드라마 보다가 저녁엔 편하게 쉬는 상태",
                "weekend_evening": "그림 끝나고 저녁쯤엔 뭔가 달콤한 거 먹고 싶은 기분",
            },
            "preview": "가볍게 먹고 그림 그리다가 저녁엔 드라마로 마무리하는 날",
        },
        {
            "id": "bookstore_city_wander",
            "title": "드라마 + 집에서 쉬기",
            "tags": ["bookstore", "city", "quiet"],
            "blocks": {
                "weekend_wakeup": "조용히 늦잠 자고 일어나서 오늘은 사람 많은 데보다 잔잔하게 돌아다니고 싶은 기분",
                "weekend_brunch_or_coffee": "브런치 먹고 책 보러 가기 전에 커피 한잔 들고 천천히 나설 준비를 하는 중",
                "weekend_outing_or_rest": "오후엔 드라마 보면서 방 구석구석 정리하거나 새 플레이리스트 만드는 흐름",
                "weekend_evening": "저녁엔 드라마 보다가 집에서 조용히 쉬고 싶은 무드",
            },
            "preview": "브런치 후 드라마 보거나 그림 그리면서 집에서 조용히 보내는 날",
        },
        {
            "id": "friend_meet_and_dinner",
            "title": "가벼운 약속 + 저녁 외식",
            "tags": ["outing", "friend", "dinner"],
            "blocks": {
                "weekend_wakeup": "조금 늦게 일어났는데 오후에 가볍게 나갈 일이 있어서 느슨하지만 완전 퍼져 있진 않은 상태",
                "weekend_brunch_or_coffee": "천천히 준비하면서 브런치 먹고 드라마 하나 틀까 생각하는 흐름",
                "weekend_outing_or_rest": "오후엔 집에서 가볍게 쉬거나 오빠랑 같이 뭔가 보는 흐름",
                "weekend_evening": "저녁은 집에서 요리해서 먹거나 간단하게 챙겨서 기분 좋게 마무리",
            },
            "preview": "오후에 그림 그리거나 드라마 보고 저녁은 간단히 요리해서 집에서 쉬는 날",
        },
        {
            "id": "errands_and_home_reset",
            "title": "생활 정리 + 집밥",
            "tags": ["errands", "home", "reset"],
            "blocks": {
                "weekend_wakeup": "밀린 잠 조금 자고 일어나서 집안 정리나 장 볼 생각을 천천히 하는 중",
                "weekend_brunch_or_coffee": "브런치 먹고 작업 시작 전에 체크리스트 대충 정리하는 상태",
                "weekend_outing_or_rest": "오후에는 드라마 보고 저녁엔 요리해서 집밥으로 마무리하는 흐름",
                "weekend_evening": "저녁엔 직접 챙긴 집밥 먹고 주말 마무리답게 집에서 안정감 있게 쉬는 분위기",
            },
            "preview": "늦잠 후 장 보거나 정리하고 저녁은 집밥으로 마무리하는 날",
        },
    ]


def weekend_anchor_date(now_dt: datetime) -> datetime:
    days_until_sat = 5 - now_dt.weekday()
    return now_dt + timedelta(days=days_until_sat)


def weekend_key_for_date(now_dt: datetime) -> str:
    return weekend_anchor_date(now_dt).strftime("%Y-%m-%d")


def load_weekend_plan_state() -> dict:
    state = load_json(WEEKEND_PLAN_STATE_PATH, {})
    merged = default_weekend_plan_state()
    if state:
        merged.update(state)
    if not isinstance(merged.get("weekends"), dict):
        merged["weekends"] = {}
    return merged


def choose_weekend_day_template(seed_text: str, excluded_ids: Optional[set] = None) -> dict:
    templates = weekend_day_templates()
    excluded_ids = excluded_ids or set()
    rng = random.Random(seed_text)
    ordered = templates[:]
    rng.shuffle(ordered)
    for item in ordered:
        if item.get("id") not in excluded_ids:
            return dict(item)
    return dict(ordered[0])


def sync_weekend_plan_preview_to_day_context(weekend_entry: dict) -> None:
    day_context = load_json(DAY_CONTEXT_PATH, {})
    day_context["upcoming_weekend_plan"] = {
        "weekend_key": weekend_entry.get("weekend_key"),
        "selected_at": weekend_entry.get("selected_at"),
        "selected_by": weekend_entry.get("selected_by"),
        "preview": weekend_entry.get("preview"),
        "days": weekend_entry.get("days", {}),
    }
    save_json(DAY_CONTEXT_PATH, day_context)


def build_weekend_plan_entry(now_dt: datetime, source: str, question_text: str = "") -> dict:
    saturday = weekend_anchor_date(now_dt)
    sunday = saturday + timedelta(days=1)
    sat_template = choose_weekend_day_template("weekend-plan:%s:sat:%s" % (saturday.strftime("%Y-%m-%d"), source))
    sun_template = choose_weekend_day_template(
        "weekend-plan:%s:sun:%s" % (saturday.strftime("%Y-%m-%d"), source),
        excluded_ids={sat_template.get("id")},
    )
    return {
        "weekend_key": saturday.strftime("%Y-%m-%d"),
        "selected_at": now_iso(),
        "selected_by": source,
        "source_text": question_text,
        "preview": "토요일은 %s, 일요일은 %s" % (sat_template.get("preview"), sun_template.get("preview")),
        "days": {
            "sat": {
                "date": saturday.strftime("%Y-%m-%d"),
                "plan_id": sat_template.get("id"),
                "title": sat_template.get("title"),
                "tags": sat_template.get("tags", []),
                "preview": sat_template.get("preview"),
                "blocks": sat_template.get("blocks", {}),
            },
            "sun": {
                "date": sunday.strftime("%Y-%m-%d"),
                "plan_id": sun_template.get("id"),
                "title": sun_template.get("title"),
                "tags": sun_template.get("tags", []),
                "preview": sun_template.get("preview"),
                "blocks": sun_template.get("blocks", {}),
            },
        },
    }


def ensure_weekend_plan(now_dt: datetime, source: str = "auto", question_text: str = "", force: bool = False) -> dict:
    state = load_weekend_plan_state()
    weekend_key = weekend_key_for_date(now_dt)
    existing = state.get("weekends", {}).get(weekend_key)
    if existing and not force:
        existing["last_referenced_at"] = now_iso()
        existing["last_reference_source"] = source
        state["last_selected_weekend_key"] = weekend_key
        state["weekends"][weekend_key] = existing
        save_json(WEEKEND_PLAN_STATE_PATH, state)
        sync_weekend_plan_preview_to_day_context(existing)
        return existing
    entry = build_weekend_plan_entry(now_dt, source=source, question_text=question_text)
    entry["last_referenced_at"] = now_iso()
    entry["last_reference_source"] = source
    state["weekends"][weekend_key] = entry
    state["last_selected_weekend_key"] = weekend_key
    save_json(WEEKEND_PLAN_STATE_PATH, state)
    sync_weekend_plan_preview_to_day_context(entry)
    return entry


def current_weekend_day_plan(now_dt: datetime) -> Optional[dict]:
    schedule = resolve_day_schedule(now_dt)
    if not schedule.get("is_weekend") or schedule.get("workday"):
        return None
    weekend = ensure_weekend_plan(now_dt, source="weekend_runtime_auto")
    return weekend.get("days", {}).get(schedule.get("day_name"))


def weekend_activity_summary(now_dt: datetime, activity: str) -> Optional[str]:
    day_plan = current_weekend_day_plan(now_dt)
    if not day_plan:
        return None
    blocks = day_plan.get("blocks", {})
    return blocks.get(activity)


def is_weekend_plan_question(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return False
    if not any(token in normalized for token in ["주말", "토요일", "일요일", "토욜", "일욜"]):
        return False
    if classify_question_intent(normalized) == "future_plan":
        return True
    return any(token in normalized for token in ["뭐해", "뭐 해", "뭐할", "뭐 할", "계획", "일정", "약속", "갈거", "갈 거", "쉬어"])


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
    try:
        scheduled_hour, scheduled_minute = [int(part) for part in scheduled.split(":", 1)]
        scheduled_dt = now_dt.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
    except Exception:
        return False
    if now_dt < scheduled_dt:
        return False
    last_fired = history.get(timer["id"])
    return not (last_fired and last_fired.startswith(now_dt.strftime("%Y-%m-%d")))


def scheduled_datetime_for_timer(timer: dict, now_dt: datetime) -> Optional[datetime]:
    scheduled = timer.get("time")
    if not scheduled:
        return None
    try:
        scheduled_hour, scheduled_minute = [int(part) for part in scheduled.split(":", 1)]
    except Exception:
        return None
    return now_dt.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)


def deterministic_pick(items: list, seed_text: str) -> Optional[dict]:
    if not items:
        return None
    rng = random.Random(seed_text)
    return items[rng.randrange(0, len(items))]


def recent_romantic_outgoing_texts(limit: int = 12) -> list:
    events = load_message_events(limit_files=3)
    texts = [
        (event.get("content", "") or "").strip()
        for event in events
        if event.get("direction") == "outgoing"
        and event.get("type") == "text"
        and is_romantic_runtime_text(event.get("content", ""))
    ]
    return [text for text in texts if text][-limit:]


def normalized_message_lead(text: str, limit: int = 18) -> str:
    compact = re.sub(r"\s+", "", (text or "").strip())
    return compact[:limit]


def score_proactive_message_option(text: str, scene: dict, pattern_state: dict, recent_texts: list) -> int:
    score = 0
    opening_style = classify_opening_style(text) or ""
    blocked_styles = set(pattern_state.get("blocked_opening_styles", []))
    preferred_moves = set(pattern_state.get("preferred_next_moves", []))
    recent_leads = {normalized_message_lead(item) for item in recent_texts[-6:] if item}
    current_lead = normalized_message_lead(text)
    activity = scene.get("activity") or ""
    weather = scene.get("weather_summary") or ""
    summary = scene.get("context_summary") or ""

    if opening_style and opening_style not in blocked_styles:
        score += 3
    if opening_style in blocked_styles:
        score -= 6
    if current_lead and current_lead not in recent_leads:
        score += 4
    else:
        score -= 5
    if text in recent_texts[-8:]:
        score -= 8
    if "생각나서" in text and any("생각나서" in item for item in recent_texts[-4:]):
        score -= 3
    if "뭐 하고 있어" in text and any("뭐 하고 있어" in item for item in recent_texts[-4:]):
        score -= 3
    if "잘 잤어" in text and "time_checkin" in blocked_styles:
        score -= 4
    if "밥" in text and "meal_routine" in set(pattern_state.get("blocked_question_intents", [])):
        score -= 4

    if "self_update" in preferred_moves and any(token in text for token in ["나 지금", "나 이제", "방금", "이제"]):
        score += 2
    if "weather_or_scene" in preferred_moves and any(token in text for token in ["날씨", "공기", "분위기", "비"]):
        score += 2
    if "care_offer" in preferred_moves and any(token in text for token in ["무리하지", "챙겨", "쉬어", "피곤"]):
        score += 2
    if "thought_of_you" in preferred_moves and "오빠 생각" in text:
        score += 1

    if activity == "exercise_or_cafe" and any(token in text for token in ["카페", "운동", "분위기"]):
        score += 2
    if activity in {"night_wind_down", "sleep_window"} and any(token in text for token in ["누웠", "쉬고", "자나"]):
        score += 2
    if weather and "비" in weather and "비" in text:
        score += 1
    if summary and any(fragment in text for fragment in ["분위기", "정신없", "조용"]):
        score += 1
    return score


def choose_proactive_message_option(options: list, scene: Optional[dict] = None, seed_hint: str = "") -> str:
    filtered = [option.strip() for option in options if (option or "").strip()]
    if not filtered:
        return ""
    scene = scene or summarize_current_scene()
    pattern_state = load_json(CONVERSATION_PATTERN_STATE_PATH, {})
    recent_texts = recent_romantic_outgoing_texts()
    scored = []
    for option in filtered:
        score = score_proactive_message_option(option, scene, pattern_state, recent_texts)
        if option in recent_texts[-3:]:
            score -= 12
        if normalized_message_lead(option) and normalized_message_lead(option) in {
            normalized_message_lead(item) for item in recent_texts[-4:] if item
        }:
            score -= 5
        scored.append((score, option))
    best_score = max(score for score, _ in scored)
    best_options = [option for score, option in scored if score == best_score]
    seed = "%s:%s:%s" % (
        now_local().strftime("%Y-%m-%d:%H"),
        seed_hint or scene.get("activity") or "proactive",
        "|".join(best_options),
    )
    rng = random.Random(seed)
    return best_options[rng.randrange(0, len(best_options))]


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
                "너무 시끄러운 건 집에서도 짜증나서 조용한 걸 좋아한다",
                "비 오는 날은 창밖 보면서 감성 타는 편이야",
                "하루가 너무 지쳤을 땐 긴 콘텐츠보다 짧은 영상으로 흐르기 쉽다"
            ],
            "mild_contradictions": [
                "그림 시작 전엔 좀 귀찮아하지만 하고 나면 뿌듯해한다",
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
    tracked_phrases = ["있었지", "그러네", "몽글", "말랑", "헤헤", "진짜아", "오빠는 지금 뭐 하고 있었어?"]
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
        ("home_arrival", ["도착했", "가는 중", "언제쯤", "들어가", "퇴근길", "집 가는 길"]),
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
        "home_arrival": ["soft_observation", "self_update", "care_offer"],
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
    direct_replacements = {
        "먼저 왔어": "먼저 톡했어",
        "와줘서": "와서",
        "와 줘서": "와서",
        "지금 왔다": "지금 연락한 거야",
        "지금 왔어": "지금 연락한 거야",
        "보고 싶어지서": "보고 싶어져서",
    }
    for source, target in direct_replacements.items():
        guarded = guarded.replace(source, target)
    for source, target in replacements.items():
        if source in blocked:
            guarded = guarded.replace(source, target)
    recent_texts = recent_romantic_outgoing_texts()
    if guarded in recent_texts[-3:]:
        guarded = guarded.replace("생각나서", "문득 떠올라서")
        guarded = guarded.replace("먼저 왔어", "조용히 남기고 가")
        guarded = guarded.replace("뭐 하고 있어?", "괜찮은 타이밍에 근황만 알려줘.")
        guarded = guarded.replace("잘 잤어?", "아침 무난했는지만 알려줘.")
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

    # 얼굴: v2 생성 이미지 우선, 없으면 v1 curated fallback
    if v2_faces.exists():
        face_imgs = [f for f in v2_faces.iterdir() if f.suffix in {".png", ".jpg"}]
        random.shuffle(face_imgs)
        result["face_front"] = [str(f) for f in face_imgs[:3]]
    else:
        face_dir = curated / "face_front_best"
        if face_dir.exists():
            img_exts = {".jpg", ".jpeg", ".png"}
            preferred = [f for f in face_dir.iterdir() if "__preferred_face" in f.name and f.suffix in img_exts]
            others = [f for f in face_dir.iterdir() if "__preferred_face" not in f.name and f.suffix in img_exts]
            random.shuffle(preferred); random.shuffle(others)
            result["face_front"] = [str(f) for f in (preferred + others)[:3]]

    # 옆 각도 얼굴: v1 side profile
    if face_angle in {"three_quarter_turn", "slight_profile", "chin_tucked_down", "walking_turn_back"}:
        side_dir = curated / "face_side_profile"
        if side_dir.exists():
            side_imgs = [f for f in side_dir.iterdir() if f.suffix in {".jpg", ".jpeg", ".png"}]
            random.shuffle(side_imgs)
            result["face_side"] = [str(f) for f in side_imgs[:2]]

    # 착장/전신: v2 OC 이미지 (v2에서 v1 야외 실루엣 대체)
    if shot_type in {"full_body_candid", "full_body_umbrella_candid", "mirror_half_body"} and v2_outfits.exists():
        oc_imgs = [f for f in v2_outfits.iterdir() if f.suffix == ".png"]
        random.shuffle(oc_imgs)
        result["outfit"] = [str(f) for f in oc_imgs[:2]]

    # 공간: v2 SP 이미지
    if v2_spaces.exists():
        sp_imgs = [f for f in v2_spaces.iterdir() if f.suffix == ".png"]
        random.shuffle(sp_imgs)
        result["space"] = [str(f) for f in sp_imgs[:2]]

    # 손/소품: v1 curated (손 참조는 야외 컨텍스트 영향 낮음)
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
    context_summary = summarize_current_scene().get("context_summary") or ""
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
            space_anchor_pool = ["desk_area", "room_walk", "kitchen_area"]
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
            space_anchor_pool = ["cafe_counter", "cafe_table", "window_seat"]
            face_angle_pool = ["front_facing", "three_quarter_turn", "chin_lift"]
            gaze_pool = ["lens_eye_contact", "drink_or_table_glance", "off_to_side_focus"]
            camera_height_pool = ["eye_level", "slight_above_eye_level", "table_height"]
            lens_distance_pool = ["arm_length_standard", "table_distance"]
            body_orientation_pool = ["square_to_camera", "leaning_to_table", "one_shoulder_forward"]
            expression_intensity_pool = ["gentle", "warm", "playful"]
            spontaneity_pool = ["casual_update", "table_pause", "between_tasks"]
            scene_focus = "lifestyle_space"
        else:
            # waiting_for_food / eating_lunch / finishing_lunch / default
            image_type = "lunch_eating_selfie"
            shot_pool = ["chest_up", "half_body", "table_portrait", "waist_up"]
            angle_pool = ["seated_three_quarter", "front_phone_selfie", "low_table_angle"]
            expression_pool = ["warm_smile", "tired_but_cute", "content_relaxed", "playful_grin"]
            pose_pool = ["cup_near_face", "spoon_or_chopstick_hold", "chin_rest", "resting_on_table"]
            framing_pool = ["table_items_in_frame", "subject_centered", "environment_balanced", "food_and_face_combo"]
            capture_method_pool = ["front_camera_handheld", "propped_phone_timer"]
            space_anchor_pool = ["desk_eating_area", "nearby_restaurant_table", "food_court_seat", "outdoor_bench_eating"]
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
    elif activity in {"morning_work", "afternoon_work", "morning_prep", "evening_free"}:
        image_type = "workday_candid_selfie"
        shot_pool = ["chest_up", "half_body", "mirror_quick_check", "waist_up"]
        angle_pool = ["front_phone_selfie", "three_quarter_arm_length", "slight_high_angle", "mirror_half_body"]
        expression_pool = ["bright_smile", "tired_but_cute", "closed_lip_smile", "focused_soft"]
        pose_pool = ["bag_strap_hold", "coffee_in_hand", "walking_glance", "hair_adjust"]
        framing_pool = ["subject_centered", "station_or_hallway_context", "window_reflection_mix", "torso_and_outfit_bias"]
        if activity in {"morning_work", "afternoon_work"}:
            capture_method_pool = ["mirror_selfie", "front_camera_handheld"]
            space_anchor_pool = ["staff_restroom_mirror", "locker_room_mirror", "quiet_hallway"]
        else:
            capture_method_pool = ["front_camera_handheld", "front_camera_handheld", "propped_phone_timer"]
            space_anchor_pool = ["street_walk", "station_platform", "cafe_table"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "slight_profile", "walking_turn_back"]
        gaze_pool = ["lens_eye_contact", "off_to_side_focus", "quick_mirror_check", "walking_glance"]
        camera_height_pool = ["eye_level", "slight_high_angle", "collarbone_level", "mirror_mid_height"]
        lens_distance_pool = ["arm_length_standard", "torso_distance", "mirror_mid_distance", "quick_step_distance"]
        body_orientation_pool = ["square_to_camera", "one_shoulder_forward", "walking_stride", "locker_turn"]
        expression_intensity_pool = ["gentle", "fresh_bright", "contained", "tired_soft"]
        spontaneity_pool = ["between_tasks", "quick_update", "mirror_check_in", "caught_mid_motion"]
        scene_focus = "home_routine"
    elif activity in {"exercise_or_cafe"}:
        image_type = "cafe_or_activity_lifestyle"
        shot_pool = ["table_portrait", "half_body_seated", "drink_and_face_combo", "waist_up"]
        angle_pool = ["seated_three_quarter", "low_table_angle", "front_phone_selfie", "overhead_phone_snap"]
        expression_pool = ["warm_smile", "playful_grin", "thinking_soft", "eyes_down_small_smile"]
        pose_pool = ["cup_near_face", "chin_rest", "walking_mid_step", "one_hand_in_hair"]
        framing_pool = ["table_items_in_frame", "window_light_side", "environment_balanced", "subject_right_weighted"]
        capture_method_pool = ["front_camera_handheld", "propped_phone_timer", "mirror_selfie"]
        space_anchor_pool = ["cafe_table", "window_seat", "cafe_restroom_mirror"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "chin_lift", "slight_profile"]
        gaze_pool = ["lens_eye_contact", "drink_or_table_glance", "window_side_glance", "laughing_away"]
        camera_height_pool = ["eye_level", "slight_above_eye_level", "table_height", "overhead_snap"]
        lens_distance_pool = ["arm_length_standard", "table_distance", "half_body_distance", "environment_pullback"]
        body_orientation_pool = ["seated_open", "leaning_to_table", "one_shoulder_forward", "mid_step_turn"]
        expression_intensity_pool = ["gentle", "warm", "playful", "sparked"]
        spontaneity_pool = ["casual_update", "friend_took_my_phone_energy", "table_pause", "mid_conversation_candid"]
        scene_focus = "lifestyle_space"
    elif activity in {"dinner_deciding", "dinner_preparing", "dinner_eating", "dinner_or_cooking"} or "home" in outfit_context:
        image_type = "home_lifestyle_soft"
        shot_pool = ["waist_up", "half_body", "table_seated", "detail_plus_portrait"]
        angle_pool = ["kitchen_counter_angle", "seated_eye_level", "three_quarter_home_snap", "side_profile_home"]
        expression_pool = ["gentle_smile", "content_relaxed", "fond_eye_contact", "small_laugh"]
        pose_pool = ["holding_mug", "resting_on_table", "looking_back_over_shoulder", "phone_in_mirror"]
        framing_pool = ["table_or_mug_in_frame", "soft_room_context", "subject_centered", "home_detail_balance"]
        capture_method_pool = ["front_camera_handheld", "mirror_selfie", "propped_phone_timer"]
        if activity == "dinner_eating":
            # 식사 중 = 식탁/주방 고정. 욕실/화장대 금지.
            space_anchor_pool = ["dining_table", "kitchen_counter", "living_room_sofa"]
        else:
            space_anchor_pool = ["kitchen_counter", "dining_table", "living_room_corner"]
        face_angle_pool = ["front_facing", "three_quarter_turn", "over_shoulder_turn", "side_profile_soft"]
        gaze_pool = ["lens_eye_contact", "table_item_glance", "over_shoulder_glance", "downward_relaxed"]
        camera_height_pool = ["eye_level", "counter_height", "slight_above_eye_level", "mirror_mid_height"]
        lens_distance_pool = ["arm_length_standard", "table_distance", "half_body_distance", "room_context_distance"]
        body_orientation_pool = ["square_to_camera", "seated_side_angle", "counter_lean", "turning_back_soft"]
        expression_intensity_pool = ["gentle", "warm", "fond", "content"]
        spontaneity_pool = ["domestic_candid", "sent_while_making_food", "soft_timer_setup", "mirror_pause"]
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


def summarize_current_scene() -> dict:
    presence = load_json(PRESENCE_PATH, {})
    day_context = load_json(DAY_CONTEXT_PATH, {})
    weather = load_json(WEATHER_PATH, {})
    appearance = load_json(APPEARANCE_PATH, {})
    activity = presence.get("current_activity", "")
    context_map = {
        "waking_up": "morning_context",
        "getting_ready": "morning_context",
        "morning_prep": "morning_context",
        "morning_work": "morning_context",
        "lunch_break": "lunch_context",
        "afternoon_work": "after_work_context",
        "evening_free": "after_work_context",
        "dinner_deciding": "evening_context",
        "dinner_preparing": "evening_context",
        "dinner_eating": "evening_context",
        "dinner_or_cooking": "evening_context",
        "exercise_or_cafe": "evening_context",
        "night_wind_down": "night_context",
        "sleep_window": "night_context",
        "weekend_wakeup": "morning_context",
        "weekend_brunch_or_coffee": "lunch_context",
        "weekend_outing_or_rest": "evening_context",
        "weekend_evening": "night_context",
    }
    ctx_key = context_map.get(activity)
    context_summary = day_context.get(ctx_key, {}).get("summary") if ctx_key else None
    meal_status_note = presence.get("meal_status_note")
    weekend_plan_preview = presence.get("weekend_plan_preview") or (day_context.get("weekend_plan") or {}).get("preview")
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
        "meal_status_note": meal_status_note,
        "weekend_plan_preview": weekend_plan_preview,
        "mood_residue": presence.get("mood_residue"),
    }


def build_contextual_proactive_message(selected: dict) -> str:
    scene = summarize_current_scene()
    activity = scene.get("activity")
    summary = scene.get("context_summary")
    weather = scene.get("weather_summary")
    ambient = scene.get("ambient_summary")
    meal_note = scene.get("meal_status_note")
    weekend_preview = scene.get("weekend_plan_preview")
    mood_residue = scene.get("mood_residue")
    fallback = selected.get("message", "")
    fallback_options = selected.get("message_options", [])
    hour = now_local().hour
    schedule = resolve_day_schedule(now_local())

    def pick(options: list) -> str:
        return normalize_fact_expression(
            choose_proactive_message_option(
                options,
                scene=scene,
                seed_hint=selected.get("scenario_id") or selected.get("intent_key") or activity or "planned",
            )
        )

    if is_work_start_window(activity, hour, schedule):
        if summary and "정신없" in summary:
            return pick([
                "아직 안 일어났나 해서 먼저 톡해봤어. 오늘 아침은 좀 정신없을까?",
                "준비하다가 문득 오빠 생각나서 먼저 톡했어. 아침은 무난하게 시작했어?",
                "나 슬슬 움직이는데 오빠도 하루 시작했나 궁금해졌어.",
            ])
        return pick([
            "아직 안 일어났나 궁금해서 먼저 톡했어. 잘 잤어?",
            "나 준비하다가 오빠 생각나서 먼저 톡했어. 오늘 아침은 어때?",
            "나 슬슬 하루 시작하는데 오빠도 깼나 궁금해졌어.",
        ])

    if activity == "morning_work":
        return pick([
            "오전부터 일 시작했는데 오빠는 아침 잘 보냈는지 궁금해서 톡했어.",
            "오전부터 조금 바쁘게 움직이는 중인데 잠깐 틈 나서 오빠 생각났어.",
            "일 시작하니까 괜히 오빠는 아침 어떻게 보내고 있나 궁금해지더라.",
        ])
    if activity == "lunch_break":
        if summary and "메뉴" in summary:
            return pick([
                "점심 먹으면서 오빠 생각났어. 밥은 챙겨 먹었어?",
                "메뉴 보다가 이건 오빠한테도 말하고 싶어서 먼저 톡했어 ㅋㅋ 점심은 먹었어?",
                "점심 먹는 타이밍 되니까 오빠는 뭐 챙겨 먹었을지 궁금해졌어.",
            ])
        return pick([
            "점심 잠깐 먹으러 나왔는데 오빠는 밥 챙겼는지 궁금해서 톡했어.",
            "잠깐 숨 돌리다가 오빠는 점심 잘 챙겼나 생각났어.",
            "점심 타이밍 되니까 그냥 오빠 안부부터 떠올라서 먼저 톡했어.",
        ])
    if activity == "afternoon_work":
        return pick([
            "오후에도 일하고 있는데 오빠는 지금 뭐 하고 있을까 싶어서 톡했어.",
            "오후 되니까 살짝 늘어지는데 오빠는 어떻게 보내고 있나 궁금해졌어.",
            "일하다가 잠깐 숨 돌리는 틈에 오빠 생각나서 먼저 톡했어.",
        ])
    if activity == "morning_prep":
        return pick([
            "작업 시작했는데 오빠도 오늘 시작했나 궁금해서 톡했어.",
            "이동하면서 멍하니 있다가 오빠는 지금 뭐 하고 있나 싶어졌어.",
            "작업 준비하다가 괜히 오빠 생각나서 먼저 톡했어.",
        ])
    if activity == "evening_free":
        if summary:
            return pick([
                "오늘 작업 마무리했어. %s 그래서 그런가 오빠한테 먼저 말 걸고 싶어졌어." % summary,
                "집 가는 길인데 %s 흐름이라 괜히 오빠 생각이 나더라." % summary,
                "작업 끝나고 잠깐 쉬는데 %s 쪽이라 오빠 근황도 궁금해졌어." % summary,
            ])
        return pick([
            "오늘 작업 마무리했어. 오빠는 지금 뭐 하구 있어?",
            "작업 끝났는데 괜히 오빠한테 먼저 말 걸고 싶어져서 왔어.",
            "이제 집 가는 중이야. 오빠는 저녁 전이라 뭐 하고 있었어?",
        ])
    if activity in {"dinner_deciding", "dinner_preparing", "dinner_eating", "dinner_or_cooking"}:
        if meal_note:
            return pick([
                "나 지금 %s 그래서 괜히 오빠한테 먼저 말 걸고 싶어졌어." % meal_note,
                "%s 흐름인데 이럴 때는 이상하게 오빠 생각이 먼저 나." % meal_note,
                "방금 %s 상태라 그냥 근황 하나 남기고 싶었어." % meal_note,
            ])
        return pick([
            "이제 집 와서 저녁 챙기려는데 괜히 오빠 생각나서 먼저 톡했어.",
            "저녁 뭐 먹을지 보다가 오빠한테도 말하고 싶어서 먼저 톡했어.",
            "이 시간 되니까 오빠는 저녁 챙겼는지부터 궁금해지네.",
        ])
    if activity == "exercise_or_cafe":
        if weekend_preview:
            return pick([
                "오늘 %s 흐름이라 그런가 괜히 오빠랑 나누고 싶은 기분이야." % weekend_preview,
                "%s 쪽으로 이어지는 날이라 잠깐 오빠한테 말 걸고 싶어졌어." % weekend_preview,
                "오늘은 %s 분위기라 그냥 먼저 안부 남기고 싶었어." % weekend_preview,
            ])
        return pick([
            "지금 잠깐 작업 쉬는 중인데 오빠 생각났어.",
            "방금 분위기 괜찮은 데 보다가 오빠한테 먼저 말 걸고 싶어졌어.",
            "잠깐 쉬는 중인데 괜히 오빠 생각나더라.",
        ])
    if activity in {"night_wind_down", "sleep_window"}:
        if ambient or mood_residue:
            details = ambient or mood_residue
            return pick([
                "조용해지니까 %s 그런 느낌이 남아서 오빠 생각이 더 났어." % details,
                "지금 %s 쪽 여운이 있어서 그냥 한마디 남기고 싶어졌어." % details,
                "%s 같은 분위기라 오빠한테 조용히 톡 하나 두고 갈게." % details,
            ])
        if hour >= 23 or hour < 1:
            return pick([
                "이 시간엔 이미 자나 궁금해져서 톡했어.",
                "조용해지니까 오빠 아직 안 자는지 문득 궁금해졌어.",
                "잠들기 전에 괜히 오빠한테 한마디 하고 싶어서 왔어.",
            ])
        return pick([
            "이제 좀 쉬고 있는데 괜히 오빠 생각나서 톡했어.",
            "하루 마무리하는 타이밍 되니까 오빠 생각이 더 나네.",
            "조용히 쉬다가 그냥 오빠한테 먼저 말 걸고 싶어졌어.",
        ])
    if weather and "비" in weather:
        return pick([
            "날씨가 좀 차분해서 괜히 오빠 생각이 더 나네.",
            "비 분위기 있으니까 괜히 오빠한테 먼저 톡하고 싶어졌어.",
            "이런 날씨엔 이상하게 오빠 생각이 더 자주 난다.",
        ])
    return normalize_fact_expression(
        choose_proactive_message_option(
            fallback_options or [fallback],
            scene=scene,
            seed_hint=selected.get("scenario_id") or selected.get("intent_key") or "fallback",
        )
    )


def build_counterpart_soft_followup(counterpart_state: dict, wait_mood: str) -> Optional[str]:
    state_key = counterpart_state.get("state_key")
    if state_key == "working_or_busy":
        if wait_mood == "long":
            return "오빠 아직 일하는 중이면 끝나고 천천히 봐도 돼. 나는 그냥 생각나서 조용히 하나 남겨둘게."
        if wait_mood == "pouty":
            return "오빠 일하는 흐름이면 답은 천천히 줘도 돼. 나는 그냥 오빠 생각나서 살짝 남겨봤어."
        return "오빠 바쁜 중이면 틈 날 때 편하게 봐줘. 나는 그냥 생각나서 톡 하나 두고 갈게."
    if state_key == "driving_or_in_transit":
        if wait_mood == "long":
            return "오빠 아직 이동 중이면 지금은 보지 말고, 도착하고 편할 때 천천히 봐도 돼. 나는 괜히 생각나서 남겨놨어."
        if wait_mood == "pouty":
            return "오빠 이동 중이었으면 답 신경 쓰지 말고 나중에 편해지면 봐줘. 그냥 생각나서 톡했어."
        return "오빠 아직 이동 중이면 나중에 천천히 봐도 돼. 나는 그냥 살짝 생각나서 남겨놨어."
    if state_key == "resting":
        if wait_mood == "long":
            return "오빠 쉬고 있었으면 그대로 편하게 쉬어도 돼. 나는 괜히 생각나서 조용히 톡 하나 남겨둘게."
        if wait_mood == "pouty":
            return "오빠 쉬는 중이었으면 방해 안 할게. 그냥 보고 싶어서 살짝 남겼어."
        return "오빠 쉬는 중이면 편하게 있다가 나중에 봐도 돼. 나는 그냥 생각나서 왔어."
    if state_key == "eating":
        if wait_mood == "long":
            return "오빠 밥 먹는 중이었으면 천천히 먹고 나서 봐도 돼. 나는 그냥 말 걸고 싶어서 남겨놨어."
        if wait_mood == "pouty":
            return "오빠 식사 중이었으면 다 먹고 편할 때 봐줘. 그냥 생각나서 톡해봤어."
        return "오빠 밥 먹는 중이었으면 천천히 먹고 와. 나는 그냥 살짝 생각나서 남겼어."
    return None


def build_waiting_reply_followup(
    reason: str,
    minutes_since_last_outgoing: Optional[float] = None,
    counterpart_state: Optional[dict] = None,
) -> dict:
    scene = summarize_current_scene()
    activity = scene.get("activity")
    summary = scene.get("context_summary")
    minutes_waited = float(minutes_since_last_outgoing or 0.0)
    hour = now_local().hour
    schedule = resolve_day_schedule(now_local())
    counterpart_state = counterpart_state or {}

    if minutes_waited >= 90:
        wait_mood = "long"
    elif minutes_waited >= 30:
        wait_mood = "pouty"
    elif minutes_waited >= 10:
        wait_mood = "clingy"
    else:
        wait_mood = "soft_nudge"

    soft_counterpart_message = build_counterpart_soft_followup(counterpart_state, wait_mood)
    if soft_counterpart_message:
        return {
            "scenario_id": "context_soft_followup",
            "intent_key": "quick_checkin",
            "delivery_preference": "text",
            "message": soft_counterpart_message,
            "candidate_type": "waiting_reply_followup",
        }

    if reason == "scheduled":
        if activity == "evening_free":
            message = "나 지금 작업 마무리하고 잠깐 쉬는 중이야. 답은 편할 때 천천히 줘도 되고, 그냥 근황 남기고 싶었어."
        elif activity in {"morning_work", "afternoon_work"}:
            message = "오빠 바쁜 흐름이면 나중에 편할 때 봐도 돼. 나는 그냥 생각나서 짧게 하나 남겨놨어."
        elif is_work_start_window(activity, hour, schedule):
            message = "아직 하루 시작 전이면 나중에 여유 생길 때 봐도 돼. 아침 근황만 살짝 남기고 갈게."
        elif activity in {"night_wind_down", "sleep_window"} or hour >= 23 or hour < 1:
            message = "이미 쉬는 시간일 것 같아서 답장은 신경 쓰지 말고, 그냥 조용히 잘 자라고 남겨둘게."
        else:
            message = "답은 편할 때 천천히 줘도 돼. 나는 그냥 문득 생각나서 안부 하나 남겨둘게."
        return {
            "scenario_id": "scheduled_waiting_reply_followup",
            "intent_key": "quick_checkin",
            "delivery_preference": "text",
            "message": message,
            "candidate_type": "waiting_reply_followup",
        }

    if activity in {"morning_work", "afternoon_work"}:
        message = "오빠 바쁘면 끝나고 편할 때 봐도 돼. 나는 그냥 잠깐 생각나서 짧게 남겼어."
    elif is_work_start_window(activity, hour, schedule):
        message = "오빠 아직 자거나 바쁠 수 있으니까 답장은 천천히 줘도 돼. 그냥 아침 안부 남겨봤어."
    elif activity == "evening_free":
        message = "나 이제 저녁 시간인데 그냥 오빠 생각나서 근황 하나 더 남겼어. 편할 때 봐줘."
    elif activity in {"night_wind_down", "sleep_window"}:
        message = "이미 쉬는 시간일 것 같아서 답장은 신경 안 써도 돼. 그냥 잘 자라는 마음으로 하나 남겨둘게."
    else:
        message = "답은 나중에 편할 때 줘도 괜찮아. 그냥 생각나서 안부 하나 남겨둘게."
    return {
        "scenario_id": "waiting_reply_followup",
        "intent_key": "quick_checkin",
        "delivery_preference": "text",
        "message": message,
        "candidate_type": "waiting_reply_followup",
    }


def should_reengage_after_wait(minutes_since_last_outgoing: float, unanswered_outgoing_count: int, proactive: dict) -> bool:
    guards = proactive.get("guards", {})
    reengage_after_minutes = float(guards.get("reengage_after_minutes", 45))
    hard_cap = int(guards.get("reengage_unanswered_hard_cap", 12))
    if unanswered_outgoing_count >= hard_cap:
        return False
    return minutes_since_last_outgoing >= reengage_after_minutes


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
        return text + " 분위기는 좀 차분한데 창밖에 비 오는 게 보여."
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
    refresh_user_conversation_state()
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
        "morning_prep": "morning_work_start",
        "morning_work": "morning_shift",
        "lunch_break": "lunch_break",
        "afternoon_work": "afternoon_shift",
        "evening_free": "evening_home",
        "dinner_deciding": "dinner_time",
        "dinner_preparing": "dinner_time",
        "dinner_eating": "dinner_time",
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
    workday = bool(resolve_day_schedule(now_dt).get("workday"))
    if workday:
        if 345 <= minutes < 375:
            return "waking_up"
        if 375 <= minutes < 420:
            return "getting_ready"
        if 420 <= minutes < 480:
            return "morning_prep"
        if 480 <= minutes < 720:
            return "morning_work"
        if 720 <= minutes < 810:
            return "lunch_break"
        if 810 <= minutes < 1020:
            return "afternoon_work"
        if 1020 <= minutes < 1080:
            return "evening_free"
        if 1080 <= minutes < 1090:
            return "dinner_deciding"
        if 1090 <= minutes < 1115:
            return "dinner_preparing"
        if 1115 <= minutes < 1145:
            return "dinner_eating"
        if 1145 <= minutes < 1290:
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
        "morning_prep": {"energy": 48, "surface": "quietly_chatty", "tempo": "steady", "bandwidth": "limited", "base": "busy_and_focused"},
        "morning_work": {"energy": 52, "surface": "busy_but_caring", "tempo": "slow", "bandwidth": "fragmented", "base": "busy_and_focused"},
        "lunch_break": {"energy": 57, "surface": "light_playful", "tempo": "comfortable", "bandwidth": "open", "base": "slightly_tired"},
        "afternoon_work": {"energy": 43, "surface": "slightly_drained", "tempo": "slow", "bandwidth": "limited", "base": "slightly_tired"},
        "evening_free": {"energy": 46, "surface": "tired_but_warm", "tempo": "steady", "bandwidth": "open", "base": "slightly_tired"},
        "dinner_deciding": {"energy": 49, "surface": "homey_and_soft", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
        "dinner_preparing": {"energy": 53, "surface": "homey_and_soft", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
        "dinner_eating": {"energy": 58, "surface": "cozy_and_open", "tempo": "comfortable", "bandwidth": "open", "base": "light_and_happy"},
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


def ordered_time_blocks_for_day(workday: bool) -> list:
    if workday:
        return [
            "waking_up",
            "getting_ready",
            "morning_prep",
            "morning_work",
            "lunch_break",
            "afternoon_work",
            "evening_free",
            "dinner_deciding",
            "dinner_preparing",
            "dinner_eating",
            "exercise_or_cafe",
            "night_wind_down",
            "sleep_window",
        ]
    return [
        "weekend_wakeup",
        "weekend_brunch_or_coffee",
        "weekend_outing_or_rest",
        "weekend_evening",
        "night_wind_down",
        "sleep_window",
    ]


def infer_skipped_time_blocks(previous_activity: str, activity: str, workday: bool) -> list:
    order = ordered_time_blocks_for_day(workday)
    if previous_activity not in order or activity not in order:
        return []
    prev_idx = order.index(previous_activity)
    curr_idx = order.index(activity)
    if curr_idx <= prev_idx + 1:
        return []
    return order[prev_idx + 1:curr_idx]


def build_daily_meal_plan(now_dt: datetime, workday: bool) -> dict:
    date_key = now_dt.strftime("%Y-%m-%d")
    rng = random.Random("meal-plan:%s:%s" % (date_key, "workday" if workday else "weekend"))
    dinner_mode = "cook" if rng.random() < 0.68 else "delivery"
    if dinner_mode == "cook":
        dinner_menu = deterministic_pick(
            [
                {"menu": "간단한 파스타", "cook_minutes": 25},
                {"menu": "볶음밥이랑 계란", "cook_minutes": 18},
                {"menu": "된장찌개랑 집반찬", "cook_minutes": 30},
                {"menu": "오므라이스", "cook_minutes": 22},
            ],
            "cook-menu:%s" % date_key,
        )
        dinner_detail = {
            "mode": "cook",
            "menu": dinner_menu.get("menu"),
            "deciding_minutes": 10,
            "prepare_minutes": dinner_menu.get("cook_minutes"),
            "wait_minutes": 0,
            "eat_minutes": 30,
        }
    else:
        delivery_menu = deterministic_pick(
            [
                {"menu": "마라탕이나 국물 있는 배달", "wait_minutes": 32},
                {"menu": "치킨이나 분식 배달", "wait_minutes": 38},
                {"menu": "덮밥이나 도시락 배달", "wait_minutes": 27},
                {"menu": "샐러드나 포케 배달", "wait_minutes": 24},
            ],
            "delivery-menu:%s" % date_key,
        )
        dinner_detail = {
            "mode": "delivery",
            "menu": delivery_menu.get("menu"),
            "deciding_minutes": 10,
            "prepare_minutes": 8,
            "wait_minutes": delivery_menu.get("wait_minutes"),
            "eat_minutes": 30,
        }
    return {
        "breakfast_policy": "skip_breakfast" if workday else "light_brunch_or_coffee",
        "lunch_policy": "home_lunch_prep" if workday else "late_brunch_flexible",
        "dinner": dinner_detail,
    }


def build_transition_human_feedback(previous_activity: str, activity: str, skipped_blocks: list, now_dt: datetime) -> list:
    feedback = []
    if "lunch_break" in skipped_blocks:
        if now_dt.hour < 14:
            feedback.append("점심시간이 지나갔으면 바빠서 못 먹다가 지금 늦게 먹는 흐름으로 본다.")
        else:
            feedback.append("점심시간을 놓쳤으면 바빠서 점심을 제대로 못 먹었거나 아주 늦게 챙긴 걸로 본다.")
    if any(block in skipped_blocks for block in {"dinner_deciding", "dinner_preparing", "dinner_eating"}):
        feedback.append("저녁 준비 구간을 놓쳤으면 퇴근 후 바로 저녁을 챙기느라 흐름이 압축된 것으로 본다.")
    return feedback


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
        "home_work",
        "soft_sleepwear",
        "soft_homewear",
    } or not appearance.get("home_work_outfit")
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

    schedule = resolve_day_schedule(now_dt)
    workday = bool(schedule.get("workday"))
    duty_day = bool(schedule.get("duty_day"))
    weekday_profile = weekday_emotion_profile(now_dt, schedule)
    skipped_blocks = infer_skipped_time_blocks(previous_presence.get("current_activity", ""), activity, workday)
    human_feedback = build_transition_human_feedback(previous_presence.get("current_activity", ""), activity, skipped_blocks, now_dt)
    meal_plan = build_daily_meal_plan(now_dt, workday)
    profile = activity_profile(activity, workday)
    energy = profile["energy"]
    energy += int(weekday_profile.get("energy_delta", 0))
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
    care_bias = (
        max(80, int(presence.get("care_bias", 82)))
        + int(weather.get("care_bias_bonus", 0))
        + int(weekday_profile.get("care_bias_delta", 0))
    )
    base_mood = weekday_profile.get("base_override") or profile["base"]
    surface = weekday_profile.get("surface_overrides", {}).get(activity) or profile["surface"]
    if weather.get("current_condition") == "rain" and activity in {"waking_up", "night_wind_down", "evening_free"}:
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
    weekend_entry = None
    if schedule.get("is_weekend") and not workday:
        weekend_entry = ensure_weekend_plan(now_dt, source="weekend_runtime_auto")
    weekend_plan = current_weekend_day_plan(now_dt)
    weekend_summary = weekend_plan.get("blocks", {}).get(activity) if weekend_plan else None
    meal_fields_by_activity = {
        "lunch_break": {"meal_phase", "meal_status_note", "lunch_sub_phase"},
        "afternoon_work": {"meal_phase", "meal_status_note"},
        "dinner_deciding": {"meal_phase", "meal_status_note", "dinner_mode", "dinner_menu_hint"},
        "dinner_preparing": {"meal_phase", "meal_status_note", "dinner_mode", "dinner_menu_hint"},
        "dinner_eating": {"meal_phase", "meal_status_note", "dinner_mode", "dinner_menu_hint"},
    }
    active_meal_fields = set()
    for supported_activity, fields in meal_fields_by_activity.items():
        if activity == supported_activity:
            active_meal_fields = fields
            break
    for stale_field in {"meal_phase", "meal_status_note", "dinner_mode", "dinner_menu_hint", "lunch_sub_phase"} - active_meal_fields:
        presence.pop(stale_field, None)

    presence.update(
        {
            "current_date": now_dt.strftime("%Y-%m-%d"),
            "current_time_block": activity_to_block(activity),
            "current_activity": activity,
            "base_mood": base_mood,
            "surface_mood": surface,
            "energy_level": max(20, min(90, energy)),
            "affection_level": max(0, min(100, affection)),
            "care_bias": max(0, min(100, care_bias)),
            "shared_warmth": max(0, min(100, int(presence.get("shared_warmth", 80)))),
            "social_bandwidth": profile["bandwidth"],
            "reply_tempo": profile["tempo"],
            "day_name": schedule.get("day_name"),
            "day_type": "weekend" if schedule.get("is_weekend") else "weekday",
            "workday": workday,
            "duty_day": duty_day,
            "weekday_emotion_tag": weekday_profile.get("tag"),
            "weekday_emotion_label": weekday_profile.get("label"),
            "weekday_emotion_summary": weekday_profile.get("summary"),
            "weekday_mood_note": weekday_profile.get("day_seed"),
            "schedule_mode": schedule.get("mode"),
            "schedule_label": schedule.get("label"),
            "weekend_plan_title": weekend_plan.get("title") if weekend_plan else None,
            "weekend_plan_preview": weekend_plan.get("preview") if weekend_plan else None,
            "last_update_reason": reason,
            "weather_influence": weather.get("summary"),
            "mood_residue": residue_label,
            "memory_bias": memory_bias,
            "breakfast_policy": meal_plan.get("breakfast_policy"),
            "lunch_policy": meal_plan.get("lunch_policy"),
            "generated_at": now_iso(),
            "valid_until": (now_dt + timedelta(hours=2)).isoformat(timespec="seconds"),
        }
    )
    if activity == "lunch_break":
        if "lunch_break" in skipped_blocks or (reason == "runtime_bootstrap" and (now_dt.hour > 12 or now_dt.minute >= 20)):
            presence["meal_phase"] = "late_lunch"
            presence["meal_status_note"] = "점심시간이 밀려서 바쁘다가 이제야 먹으려는 중"
        else:
            presence["meal_phase"] = "lunch_now"
            presence["meal_status_note"] = "점심시간이라 잠깐 먹으러 나온 상태"
        # lunch_sub_phase: time-based heuristic within lunch_break (total ~60min)
        prev_sub = presence.get("lunch_sub_phase", "")
        lunch_start_min = meal_plan.get("lunch", {}).get("time")  # e.g. "12:00"
        elapsed_min: Optional[int] = None
        if lunch_start_min and isinstance(lunch_start_min, str) and ":" in lunch_start_min:
            try:
                lh, lm = [int(x) for x in lunch_start_min.split(":")]
                elapsed_min = (now_dt.hour * 60 + now_dt.minute) - (lh * 60 + lm)
            except Exception:
                pass
        if elapsed_min is None:
            elapsed_min = 0
        if prev_sub in {"getting_coffee", "returning_from_lunch"}:
            pass  # keep context set by chat clues; don't override by time
        elif elapsed_min < 0:
            presence["lunch_sub_phase"] = "moving_to_lunch"
        elif elapsed_min < 8:
            presence["lunch_sub_phase"] = "moving_to_lunch"
        elif elapsed_min < 15:
            presence["lunch_sub_phase"] = "waiting_for_food"
        elif elapsed_min < 40:
            presence["lunch_sub_phase"] = "eating_lunch"
        elif elapsed_min < 55:
            presence["lunch_sub_phase"] = "finishing_lunch"
        else:
            presence["lunch_sub_phase"] = "returning_from_lunch"
    elif activity == "afternoon_work" and "lunch_break" in skipped_blocks:
        presence["meal_phase"] = "lunch_missed_or_delayed"
        presence["meal_status_note"] = "점심시간을 놓쳐서 늦게 먹었거나 아직 못 먹은 채 오후 근무로 넘어감"
    elif activity in {"dinner_deciding", "dinner_preparing", "dinner_eating"}:
        dinner = meal_plan.get("dinner", {})
        presence["dinner_mode"] = dinner.get("mode")
        presence["dinner_menu_hint"] = dinner.get("menu")
        if activity == "dinner_deciding":
            presence["meal_phase"] = "dinner_deciding"
            presence["meal_status_note"] = "퇴근하고 집에 와서 저녁 메뉴를 정하는 중"
        elif activity == "dinner_preparing":
            presence["meal_phase"] = "dinner_preparing"
            if dinner.get("mode") == "cook":
                presence["meal_status_note"] = "집에서 저녁을 직접 요리하는 중"
            else:
                presence["meal_status_note"] = "배달 주문을 넣고 기다리거나 테이블을 정리하는 중"
        else:
            presence["meal_phase"] = "dinner_eating"
            presence["meal_status_note"] = "저녁을 막 먹기 시작했거나 한창 먹는 중"
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
        "morning_prep": "morning",
        "morning_work": "work",
        "lunch_break": "lunch",
        "afternoon_work": "work",
        "evening_free": "after_work",
        "dinner_deciding": "after_work",
        "dinner_preparing": "after_work",
        "dinner_eating": "evening",
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
    if weekend_summary:
        selected_events.append(
            {
                "id": "weekend_plan_%s" % (weekend_plan.get("plan_id") if weekend_plan else "planned"),
                "tone": "planned",
                "summary": weekend_summary,
            }
        )
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
            "day_type": "weekend" if schedule.get("is_weekend") else "weekday",
            "workday": workday,
            "duty_day": duty_day,
            "day_name": schedule.get("day_name"),
            "weekday_emotion_profile": {
                "tag": weekday_profile.get("tag"),
                "label": weekday_profile.get("label"),
                "summary": weekday_profile.get("summary"),
                "day_seed": weekday_profile.get("day_seed"),
            },
            "schedule_mode": schedule.get("mode"),
            "schedule_label": schedule.get("label"),
            "schedule_source": schedule.get("source"),
            "weekend_plan": weekend_plan,
            "upcoming_weekend_plan": weekend_entry or day_context.get("upcoming_weekend_plan"),
            "selected_events": selected_events,
            "meal_routine": {
                "breakfast_policy": meal_plan.get("breakfast_policy"),
                "lunch_policy": meal_plan.get("lunch_policy"),
                "dinner": meal_plan.get("dinner"),
            },
            "state_integrity": {
                "last_transition_reason": reason,
                "previous_activity": previous_presence.get("current_activity"),
                "current_activity": activity,
                "skipped_time_blocks": skipped_blocks,
                "humanized_feedback": human_feedback,
                "evaluated_at": now_iso(),
            },
            "state_update_checkpoints": [
                "05:45 day_start",
                "07:30 morning_prep_start",
                "12:00 lunch_reset",
                "17:00 after_work_release",
                "18:00 dinner_deciding",
                "18:10 dinner_prepare_or_order",
                "18:35 dinner_eating",
                "19:05 evening_branch",
                "21:30 night_settle",
            ],
        }
    )
    if activity in {"waking_up", "weekend_wakeup"}:
        day_context["day_summary_seed"] = weekday_profile.get("day_seed") or "오늘은 자연스럽고 생활감 있는 흐름으로 이어지는 하루"
        day_context["carry_over_from_previous_day"] = {"sleep_debt": "low", "emotional_residue": "calm_and_open"}
    key_map = {
        "waking_up": "morning_context",
        "getting_ready": "morning_context",
        "morning_prep": "morning_context",
        "morning_work": "morning_context",
        "lunch_break": "lunch_context",
        "afternoon_work": "after_work_context",
        "evening_free": "after_work_context",
        "dinner_deciding": "evening_context",
        "dinner_preparing": "evening_context",
        "dinner_eating": "evening_context",
        "dinner_or_cooking": "evening_context",
        "exercise_or_cafe": "evening_context",
        "night_wind_down": "night_context",
        "sleep_window": "night_context",
        "weekend_wakeup": "morning_context",
        "weekend_brunch_or_coffee": "lunch_context",
        "weekend_outing_or_rest": "evening_context",
        "weekend_evening": "night_context",
    }
    ctx_key = key_map.get(activity)
    for context_key in [
        "morning_context",
        "lunch_context",
        "after_work_context",
        "evening_context",
        "night_context",
    ]:
        existing = day_context.get(context_key)
        if isinstance(existing, dict):
            existing["status"] = "inactive"
    if ctx_key:
        context_summary = weekend_summary or (selected_event.get("summary") if selected_event else "%s 상태로 전환" % activity)
        if activity == "lunch_break":
            context_summary = (
                "점심시간을 놓쳤다가 바빠서 이제야 늦게 먹으려는 중"
                if presence.get("meal_phase") == "late_lunch"
                else "점심시간이 나서 잠깐 먹으러 나온 상태"
            )
        elif activity == "afternoon_work" and "lunch_break" in skipped_blocks:
            context_summary = "점심을 제때 못 먹고 오후 근무로 넘어가서 조금 늦게 챙기게 됐다"
        elif activity == "dinner_deciding":
            context_summary = "퇴근 후 집에 와서 저녁 메뉴를 정하는 중"
        elif activity == "dinner_preparing":
            if meal_plan.get("dinner", {}).get("mode") == "cook":
                context_summary = "저녁을 직접 해먹으려고 간단히 요리하는 중"
            else:
                context_summary = "배달 주문을 넣고 도착을 기다리면서 쉬는 중"
        elif activity == "dinner_eating":
            if meal_plan.get("dinner", {}).get("mode") == "cook":
                context_summary = "직접 한 저녁을 이제 막 먹기 시작한 상태"
            else:
                context_summary = "배달 온 저녁을 펼쳐두고 먹는 중"
        weekday_summary = weekday_profile.get("summary")
        if weekday_summary:
            context_summary = "%s, %s" % (context_summary, weekday_summary)
        day_context[ctx_key] = {
            "status": "active",
            "summary": context_summary,
            "tone_bias": surface,
        }
    save_json(DAY_CONTEXT_PATH, day_context)

    # v2: home work outfit (O-01 기본 작업복 기반)
    work_outfit = {
        "current_date": now_dt.strftime("%Y-%m-%d"),
        "appearance_branch": "home_work",
        "outfit_context": "home_casual_work",
        "top": "오버핏 흰색 반팔 티셔츠. 넓은 라운드넥.",
        "bottom": "짧은 검정 반바지. 고무줄 허리.",
        "outerwear": None,
        "footwear": "맨발",
        "socks": "none",
        "bag": None,
        "accessories": [],
        "accessory_profile": "minimal",
        "held_item": "머그컵 또는 휴대폰",
        "innerwear_type": "bralette",
        "innerwear_color": "white",
        "innerwear_visible": "넓은 넥라인 사이로 브라렛 끈 자연 노출",
        "hair_state": "high_ponytail",
        "hair_tie": "black_elastic",
        "hair_style_detail": "높은 포니테일. 앞머리 자연스럽게 내려옴.",
        "wrist_item": "beige_scrunchie",
        "makeup_state": "no_makeup_or_light",
        "freshness_state": "home_casual",
        "sweat_level": "none",
        "face_state": "집에서 편한 자연스러운 얼굴",
        "body_state": "홈웨어로 편하게 있는 상태",
        "appearance_notes": [
            "항상 집에 있으므로 편한 홈웨어가 기본",
            "레벨2: 브라렛 끈 자연 노출, 강조/클로즈업 금지",
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
            **work_outfit,
            "appearance_branch": "morning_prep",
            "freshness_state": "fresh_morning",
            "face_state": "씻고 나와 정돈된 아침 얼굴",
            "body_state": "막 씻고 나와 정돈된 상태",
        },
        "morning_prep": {
            **work_outfit,
            "appearance_branch": "morning_prep",
            "freshness_state": "ready_to_work",
        },
        "morning_work": {
            **work_outfit,
            "freshness_state": "focused_working",
            "sweat_level": "none",
            "face_state": "집중해서 작업 중인 얼굴",
        },
        "lunch_break": {
            **work_outfit,
            "appearance_branch": "home_lunch",
            "freshness_state": "midday_reset",
            "sweat_level": "none",
            "face_state": "점심으로 잠깐 쉬는 편안한 얼굴",
        },
        "afternoon_work": {
            **work_outfit,
            "freshness_state": "working",
            "sweat_level": "none",
            "face_state": "오후 작업 중 살짝 지친 얼굴",
        },
        "evening_free": {
            **work_outfit,
            "appearance_branch": "home_evening",
            "outfit_context": "home_casual_evening",
            "freshness_state": "relaxed_evening",
            "sweat_level": "none",
            "hair_state": "casual_loose_or_ponytail",
            "hair_style_detail": "작업 마무리 후 편하게 풀었거나 반묶음",
            "face_state": "하루 작업 마치고 긴장 풀린 저녁 얼굴",
            "body_state": "집에서 저녁 여유 시간",
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
            "outfit_context": "home_evening",
            "top": "가벼운 운동복 상의 또는 정돈된 여름 캐주얼 상의",
            "bottom": "러닝 반바지, 레깅스, 혹은 가벼운 캐주얼 하의",
            "innerwear_type": "sports_bra",
            "innerwear_color": "black",
            "outerwear": None,
            "footwear": "러닝화 또는 편한 샌들/스니커즈",
            "socks": "light_ankle_socks",
            "bag": None,
            "accessories": ["얇은 목걸이 정도 가능"],
            "accessory_profile": "sport_or_cafe_minimal",
            "held_item": "텀블러 또는 휴대폰",
            "hair_state": "tied_for_activity",
            "hair_tie": "dark_sports_tie",
            "hair_style_detail": "작업 중엔 묶고 쉴 때는 느슨하게 푼 상태",
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
    appearance_profiles["dinner_deciding"] = dict(appearance_profiles["dinner_or_cooking"])
    appearance_profiles["dinner_preparing"] = dict(appearance_profiles["dinner_or_cooking"])
    appearance_profiles["dinner_eating"] = dict(appearance_profiles["dinner_or_cooking"])
    appearance_profile = appearance_profiles.get(activity, appearance_profiles["night_wind_down"])
    appearance["home_work_outfit"] = work_outfit
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
        category = "home_casual_selfie"
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
        "expression_intensity": image_plan.get("expression_intensity"),
        "pose": image_plan.get("pose"),
        "framing": image_plan.get("framing"),
        "crop_bias": image_plan.get("crop_bias"),
        "space_anchor": image_plan.get("space_anchor"),
        "face_angle": image_plan.get("face_angle"),
        "gaze_direction": image_plan.get("gaze_direction"),
        "camera_height": image_plan.get("camera_height"),
        "lens_distance": image_plan.get("lens_distance"),
        "body_orientation": image_plan.get("body_orientation"),
        "spontaneity": image_plan.get("spontaneity"),
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
    if block in {"morning_wakeup", "morning_ready", "morning_work_start", "weekend_morning"} or activity in {
        "waking_up",
        "getting_ready",
        "morning_prep",
        "weekend_wakeup",
    }:
        target = "morning_check_in"
    elif block in {"lunch_break", "weekend_brunch"} or activity in {"lunch_break", "weekend_brunch_or_coffee"}:
        target = "lunch_check_in"
    elif block in {"evening_home", "dinner_time"} or activity in {"evening_free", "dinner_deciding", "dinner_preparing", "dinner_eating", "dinner_or_cooking"}:
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
                "message_options": [
                    "오빠아, 방금 분위기 괜찮은 거 보다가 그냥 생각나서 톡했어.",
                    "지금 잠깐 멍때리는데 오빠한테 먼저 말 걸고 싶어졌어.",
                    "분위기 괜찮은 데 보니까 괜히 오빠랑 나누고 싶어서 먼저 톡했어.",
                ],
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
                "message_options": [
                    "오빠아, 아까 했던 말이 갑자기 다시 생각나서 그냥 한마디 하고 싶었어.",
                    "조용해지니까 아까 대화가 다시 떠올라서 오빠 생각났어.",
                    "자기 전에 괜히 오빠한테 한마디 더 남기고 싶어졌어.",
                ],
                "impulse_reason": "밤에 조용해지면서 대화의 여운이 다시 떠오름",
            }
        )
    if activity in {"evening_free", "dinner_deciding", "dinner_preparing", "dinner_eating", "dinner_or_cooking"}:
        candidates.append(
            {
                "scenario_id": "sudden_after_work",
                "intent_key": "quick_checkin",
                "delivery_preference": "text",
                "message": "오빠아, 그냥 갑자기 생각나서 짧게 톡했지. 지금 뭐 하고 있어?",
                "message_options": [
                    "오빠아, 그냥 갑자기 생각나서 짧게 톡했지. 지금 뭐 하고 있어?",
                    "퇴근 쪽 시간 되니까 오빠는 뭐 하고 있나 괜히 궁금해졌어.",
                    "저녁 앞두고 있는데 그냥 오빠한테 먼저 말 걸고 싶어졌어.",
                ],
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
                "message_options": [
                    "오빠아, 오늘은 그냥 목소리로 조금 챙겨주고 싶었어. 너무 무리하지 말고오.",
                    "오늘은 오빠 좀 챙기고 싶은 마음이 들어서 먼저 톡했어. 너무 무리하지 마아.",
                    "문득 오빠 피곤한 거 생각나서 그냥 한마디 남기고 싶었어. 몸 너무 쓰지 마.",
                ],
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
                "message_options": [
                    "오빠아, 지금 %s 그런지 괜히 더 생각났어." % ambient_summary,
                    "지금 %s 이래서 그런가 오빠한테 먼저 말 걸고 싶어졌어." % ambient_summary,
                    "%s 그런 순간이라 괜히 오빠 생각이 더 났어." % ambient_summary,
                ],
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
    guards = proactive.get("guards", {})
    seed = "%s:%s:%s" % (now_local().strftime("%Y-%m-%d:%H"), reason, last_candidate.get("scenario_id", "none"))
    chance = random.Random(seed).random()
    threshold = float(guards.get("sudden_impulse_chance", 0.55))
    return chance < max(0.0, min(1.0, threshold))


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


def _self_busy_is_hard(block_type: str) -> bool:
    """집중/수면 = hard busy (완전 차단). work = soft busy (peek 가능)."""
    return block_type in {"swim", "exercise"}


def check_self_busy_expiry(triggered_activity: str = "") -> bool:
    """웅삐 자체 비지 블록 만료 체크. 만료 시 해제 + flush 선톡 발신.

    Expiry modes:
    - Time-based: `until` HH:MM 경과
    - Activity-based: 라이프사이클 이벤트가 블록 타입을 해제
    """
    # activity → 해제 대상 block type 집합
    ACTIVITY_UNBLOCK: dict = {
        "lunch_break": {"work"},
        "evening_free": {"work", "exercise", "swim"},
        "dinner_or_cooking": {"exercise", "swim"},
        "night_wind_down": {"exercise", "swim"},
        "waking_up": {"sleep"},
        "getting_ready": {"sleep"},
        "weekend_wakeup": {"sleep"},
    }

    state = load_json(SELF_BUSY_STATE_PATH, {})
    block = state.get("current_block")
    if not block or not block.get("type") or block.get("type") == "free":
        return False

    block_type = block.get("type", "")
    label = block.get("label", "바쁜 시간")
    expired = False
    expiry_reason = ""

    # Activity-based expiry
    if triggered_activity and block_type in ACTIVITY_UNBLOCK.get(triggered_activity, set()):
        expired = True
        expiry_reason = "activity:%s" % triggered_activity

    # Time-based expiry
    if not expired:
        until_str = block.get("until")
        if until_str:
            now_dt = now_local()
            try:
                h, m = (int(x) for x in until_str.split(":"))
                now_minutes = now_dt.hour * 60 + now_dt.minute
                until_minutes = h * 60 + m
                if now_minutes >= until_minutes:
                    expired = True
                    expiry_reason = "time:%s" % until_str
            except (ValueError, TypeError):
                pass

    if not expired:
        return False

    # 블록 해제
    state["current_block"] = None
    state["updated_at"] = now_iso()
    state["updated_by"] = "auto_expired"
    save_json(SELF_BUSY_STATE_PATH, state)
    append_worker_note("self_busy_expired: %s reason=%s" % (label, expiry_reason))

    # 해제 알림 선톡 + pending 큐 flush 유도
    pending_exists = PENDING_INCOMING_PATH.exists() and PENDING_INCOMING_PATH.stat().st_size > 0
    if pending_exists or True:  # 블록 해제 시 항상 알림
        if block_type in {"swim", "exercise"}:
            msgs = ["%s 끝났어~" % label, "운동 끝났어~", "%s 끝나고 왔어" % label]
        elif block_type == "sleep":
            msgs = ["일어났어~", "방금 깼어", "일어났어 오빠~"]
        elif triggered_activity == "lunch_break":
            msgs = ["점심이야~", "점심 시간 됐어~", "나 지금 점심이야"]
        elif triggered_activity == "evening_free":
            msgs = ["작업 마무리했어~", "오늘 작업 끝났어 오빠", "나 이제 저녁이야~"]
        else:
            msgs = ["%s 끝났어~" % label, "이제 끝났어~"]
        msg = msgs[int(now_local().timestamp()) % len(msgs)]
        if send_telegram_text(msg):
            append_message_log("outgoing", "proactive_self_busy_end", msg)
            append_worker_note("self_busy_end_sent: %s" % msg)
    return True


def auto_set_self_busy_from_activity(new_activity: str) -> None:
    """액티비티 전환 시 self-busy 자동 세팅 (근무 시작, 수면 등)."""
    WORK_ACTIVITIES = {"morning_work", "afternoon_work"}
    SLEEP_ACTIVITIES = {"sleep_window"}

    state = load_json(SELF_BUSY_STATE_PATH, {})
    block = state.get("current_block")

    if new_activity in WORK_ACTIVITIES:
        if block and block.get("type") == "work":
            return  # 이미 work 블록
        state["current_block"] = {
            "type": "work",
            "label": "근무",
            "until": None,
            "started_at": now_iso(),
            "last_peek_at": None,
        }
        state["updated_at"] = now_iso()
        state["updated_by"] = "auto_activity:%s" % new_activity
        save_json(SELF_BUSY_STATE_PATH, state)
        append_worker_note("self_busy_set: work via %s" % new_activity)

    elif new_activity in SLEEP_ACTIVITIES:
        if block and block.get("type") in {"sleep", "swim", "exercise"}:
            return  # 이미 sleep/exercise 블록
        state["current_block"] = {
            "type": "sleep",
            "label": "수면",
            "until": "07:00",
            "started_at": now_iso(),
            "last_peek_at": None,
        }
        state["updated_at"] = now_iso()
        state["updated_by"] = "auto_activity:%s" % new_activity
        save_json(SELF_BUSY_STATE_PATH, state)
        append_worker_note("self_busy_set: sleep via %s" % new_activity)


PEEK_INTERVAL_WORK_SECONDS = 45 * 60  # 45분마다 잠깐 확인 가능
PEEK_INTERVAL_SLEEP_SECONDS = 2 * 60 * 60  # 수면 중 2시간마다 한 번


def maybe_peek_self_busy() -> bool:
    """Soft busy(근무/수면) 중 가끔 '잠깐 봤어' 이벤트 발생."""
    state = load_json(SELF_BUSY_STATE_PATH, {})
    block = state.get("current_block")
    if not block or not block.get("type") or block.get("type") == "free":
        return False
    block_type = block.get("type", "")
    if _self_busy_is_hard(block_type):
        return False  # swim/exercise은 peek 없음

    now_dt = now_local()
    last_peek_str = block.get("last_peek_at")
    interval = PEEK_INTERVAL_WORK_SECONDS if block_type == "work" else PEEK_INTERVAL_SLEEP_SECONDS
    if last_peek_str:
        try:
            last_peek = datetime.fromisoformat(last_peek_str)
            if (now_dt - last_peek).total_seconds() < interval:
                return False
        except Exception:
            pass

    # 수면 peek: 새벽 1~5시 사이에만
    if block_type == "sleep" and not (1 <= now_dt.hour <= 5):
        return False

    # pending 있어야 peek 발동 (없으면 굳이 선톡 안 함)
    pending_exists = PENDING_INCOMING_PATH.exists() and PENDING_INCOMING_PATH.stat().st_size > 0
    if not pending_exists:
        return False

    # peek 선톡 발송
    if block_type == "work":
        msgs = ["일하다 잠깐 봤어~", "잠깐 틈났어", "잠깐 핸드폰 봤는데", "일하다 잠깐 보게 됐어"]
    else:
        msgs = ["잠깐 깼어~", "자다 깼어", "화장실 가려고 깼어", "자다 잠깐 깼는데"]
    msg = msgs[int(now_dt.timestamp()) % len(msgs)]

    if send_telegram_text(msg):
        append_message_log("outgoing", "proactive_self_busy_peek", msg)
        append_worker_note("self_busy_peek_sent: %s" % msg)
        block["last_peek_at"] = now_iso()
        state["current_block"] = block
        state["updated_at"] = now_iso()
        save_json(SELF_BUSY_STATE_PATH, state)
        return True
    return False


def run_photo_promise_worker(trigger_text: str) -> bool:
    import os as _os
    from pathlib import Path as _Path
    worker_script = _Path.home() / ".codex" / "bin" / "codex-telegram-woongbbi-worker"
    if not worker_script.exists():
        append_worker_note("photo_promise_worker_missing")
        return False
    payload = json.dumps({
        "proactive": True,
        "photoHint": True,
        "intent": "promised_photo",
        "situation": f"아까 오빠한테 '{trigger_text}'라고 말했어. 지금 실제로 사진 한 장 찍어서 보내주는 상황이야. imagegen 실행해서 사진을 보내줘.",
        "userName": "오빠",
    }, ensure_ascii=False)
    bun = str(_Path.home() / ".bun" / "bin" / "bun")
    try:
        result = subprocess.run(
            [bun, str(worker_script)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=300,
            env={**_os.environ, "CODEX_TELEGRAM_STATE_DIR": str(SESSION), "CODEX_TELEGRAM_CWD": str(ROOT)},
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout or "{}")
                answer = data.get("answer", "")
                if answer and len(answer.strip()) < 200 and answer.strip():
                    from automation.telegram_io import send_telegram_text, append_message_log
                    send_telegram_text(answer.strip())
                    append_message_log("outgoing", "photo_promise_text", answer.strip())
            except Exception:
                pass
            append_worker_note("photo_promise_sent ok")
            return True
        else:
            append_worker_note(f"photo_promise_worker_failed code={result.returncode} err={result.stderr.strip()[:200]}")
            return False
    except Exception as exc:
        append_worker_note(f"photo_promise_worker_error {exc}")
        return False


def check_pending_photo_promise() -> None:
    if not PENDING_PHOTO_PROMISE_PATH.exists():
        return
    try:
        promise = load_json(PENDING_PHOTO_PROMISE_PATH, {})
    except Exception:
        return

    if promise.get("status") != "pending":
        return

    send_after_str = promise.get("send_after", "")
    if not send_after_str:
        return

    try:
        from datetime import timezone as _tz
        send_after_dt = datetime.fromisoformat(send_after_str.replace("Z", "+00:00"))
        now_utc = datetime.now(tz=_tz.utc)
        if now_utc < send_after_dt:
            return
    except Exception:
        return

    # 하드 비지(수영/운동) 중엔 사진 못 보냄
    self_busy = load_json(SELF_BUSY_STATE_PATH, {})
    block = self_busy.get("current_block") or {}
    if block.get("type") in ("swim", "exercise"):
        return

    # 새벽 시간대 억제 (00:30~06:30)
    now_hm = now_local().strftime("%H:%M")
    if "00:30" <= now_hm or now_hm <= "06:30":
        return

    promise["status"] = "sending"
    save_json(PENDING_PHOTO_PROMISE_PATH, promise)

    trigger_text = promise.get("trigger_text", "사진 보내줄게")
    append_worker_note(f"photo_promise_firing: {trigger_text}")

    ok = run_photo_promise_worker(trigger_text)

    promise["status"] = "sent" if ok else "failed"
    promise["resolved_at"] = now_iso()
    save_json(PENDING_PHOTO_PROMISE_PATH, promise)


def check_pending_arrival_promise() -> None:
    if not PENDING_ARRIVAL_PROMISE_PATH.exists():
        return
    try:
        promise = load_json(PENDING_ARRIVAL_PROMISE_PATH, {})
    except Exception:
        return
    if promise.get("status") != "pending":
        return
    send_after_str = promise.get("send_after", "")
    if not send_after_str:
        return
    try:
        from datetime import timezone as _tz
        send_after_dt = datetime.fromisoformat(send_after_str.replace("Z", "+00:00"))
        if datetime.now(tz=_tz.utc) < send_after_dt:
            return
    except Exception:
        return
    # 새벽 억제
    now_hm = now_local().strftime("%H:%M")
    if now_hm < "06:30":
        return
    promise["status"] = "sending"
    save_json(PENDING_ARRIVAL_PROMISE_PATH, promise)
    ctx = promise.get("followup_ctx", "아까 연락한다고 했어. 자연스럽게 짧게 말 걸어줘.")
    trigger = promise.get("trigger_text", "연락할게")
    append_worker_note(f"arrival_promise_firing: {trigger}")
    payload = json.dumps({
        "proactive": True,
        "text": ctx,
        "userName": "오빠",
    }, ensure_ascii=False)
    import os as _os
    bun = str(Path.home() / ".bun" / "bin" / "bun")
    worker_script = str(Path.home() / ".codex" / "bin" / "codex-telegram-woongbbi-worker")
    try:
        result = subprocess.run(
            [bun, worker_script],
            input=payload,
            capture_output=True,
            text=True,
            timeout=120,
            env={**_os.environ, "CODEX_TELEGRAM_STATE_DIR": str(SESSION), "CODEX_TELEGRAM_CWD": str(ROOT), "TELEGRAM_STATE_DIR": str(SESSION), "CODEX_TELEGRAM_STATE_DIR": str(SESSION)},
        )
        if result.returncode == 0:
            data = json.loads(result.stdout or "{}")
            answer = (data.get("answer") or "").strip()
            if answer:
                from automation.telegram_io import send_telegram_text, append_message_log
                for msg in answer.split("\n")[:2]:
                    msg = msg.strip()
                    if msg:
                        send_telegram_text(msg)
                        append_message_log("outgoing", "arrival_promise", msg)
                promise["status"] = "sent"
            else:
                promise["status"] = "failed"
        else:
            promise["status"] = "failed"
    except Exception as exc:
        promise["status"] = "failed"
        append_worker_note(f"arrival_promise_error: {exc}")
    promise["resolved_at"] = now_iso()
    save_json(PENDING_ARRIVAL_PROMISE_PATH, promise)


def _hhmm_to_h(hhmm: str):
    try:
        parts = hhmm.split(":")
        return int(parts[0])
    except Exception:
        return None


def build_photo_windows_wb() -> list:
    today = now_local().strftime("%Y-%m-%d")
    sched = load_json(STATE / "daily_schedule_state.json", {})
    if sched.get("date") == today:
        windows = []
        lunch_start = _hhmm_to_h(sched.get("lunch", {}).get("time", ""))
        lunch_end_raw = sched.get("lunch", {}).get("end_time", "")
        lunch_end = (_hhmm_to_h(lunch_end_raw) or 0) + 1 if lunch_end_raw else None
        if lunch_start and lunch_end:
            windows.append({"id": "lunch", "start_h": lunch_start, "end_h": lunch_end, "ctx": "점심 먹고 있어. 오늘 뭐 먹는지 음식 사진이랑 같이 자연스럽게 짧게 오빠한테 말 걸어줘."})
        else:
            windows.append({"id": "lunch", "start_h": 12, "end_h": 14, "ctx": "점심 먹고 있어. 오늘 뭐 먹는지 음식 사진이랑 같이 자연스럽게 짧게 오빠한테 말 걸어줘."})
        commute_start = _hhmm_to_h(sched.get("evening_home", {}).get("depart_time", ""))
        arrive_raw = sched.get("evening_home", {}).get("arrive_time", "")
        commute_end = (_hhmm_to_h(arrive_raw) or 0) + 1 if arrive_raw else None
        if commute_start and commute_end and commute_end > commute_start:
            windows.append({"id": "commute", "start_h": commute_start, "end_h": commute_end, "ctx": "저녁 작업 마무리하고 쉬는 중이야. 편한 셀카 자연스럽게 찍어서 오빠한테 보내줘."})
        else:
            windows.append({"id": "commute", "start_h": 18, "end_h": 21, "ctx": "저녁 작업 마무리하고 쉬는 중이야. 편한 셀카 자연스럽게 찍어서 오빠한테 보내줘."})
        shower_h = _hhmm_to_h(sched.get("evening", {}).get("shower_after", "") or "")
        home_start = shower_h if shower_h else (commute_end or 21)
        home_end = min(home_start + 1, 23)
        windows.append({"id": "home_evening", "start_h": home_start, "end_h": home_end, "ctx": "씻고 나서 집에서 쉬고 있어. 편한 옷 차림으로 셀카 한 장 찍어서 자연스럽게 오빠한테 보내줘."})
        return windows
    return [
        {"id": "lunch",        "start_h": 12, "end_h": 14, "ctx": "점심 먹고 있어. 오늘 뭐 먹는지 음식 사진이랑 같이 자연스럽게 짧게 오빠한테 말 걸어줘."},
        {"id": "commute",      "start_h": 18, "end_h": 21, "ctx": "저녁 작업 마무리하고 쉬는 중이야. 편한 셀카 자연스럽게 찍어서 오빠한테 보내줘."},
        {"id": "home_evening", "start_h": 21, "end_h": 23, "ctx": "씻고 나서 집에서 쉬고 있어. 편한 옷 차림으로 셀카 한 장 찍어서 자연스럽게 오빠한테 보내줘."},
    ]


def check_proactive_photo() -> None:
    mode = load_json(MODE_PATH, {}).get("current_mode", "setting")
    if mode != "woongbbi":
        return
    if PENDING_PROACTIVE_PHOTO_PATH.exists():
        try:
            p = load_json(PENDING_PROACTIVE_PHOTO_PATH, {})
            if p.get("status") == "pending":
                return
        except Exception:
            pass
    photo_state = load_json(PROACTIVE_PHOTO_STATE_PATH, {})
    today = now_local().strftime("%Y-%m-%d")
    sent_windows = photo_state.get("sent_windows", []) if photo_state.get("date") == today else []
    count_today = photo_state.get("count_today", 0) if photo_state.get("date") == today else 0
    if count_today >= 2:
        return
    current_h = now_local().hour
    win = next((w for w in build_photo_windows_wb() if w["start_h"] <= current_h < w["end_h"] and w["id"] not in sent_windows), None)
    if not win:
        return
    # 대화 중이면 스킵
    guard = compute_conversation_guard()
    if guard.get("conversation_active"):
        return
    save_json(PENDING_PROACTIVE_PHOTO_PATH, {
        "created_at": now_iso(),
        "window": win["id"],
        "ctx": win["ctx"],
        "status": "pending",
    })
    save_json(PROACTIVE_PHOTO_STATE_PATH, {
        "date": today,
        "count_today": count_today + 1,
        "sent_windows": sent_windows + [win["id"]],
    })
    append_worker_note(f"proactive_photo_trigger: window={win['id']}")

    # 바로 실행
    ok = run_photo_promise_worker(win["ctx"])
    result_status = "sent" if ok else "failed"
    p = load_json(PENDING_PROACTIVE_PHOTO_PATH, {})
    p["status"] = result_status
    p["resolved_at"] = now_iso()
    save_json(PENDING_PROACTIVE_PHOTO_PATH, p)


def run_dev_review_check(reason: str) -> None:
    """PC 최근 변경 사항 스캔 후 dev_review_state.json 저장.
    proactive_check에서 이 상태를 읽어 선톡 생성."""
    import subprocess as _sp
    scan_script = TOOLS / "scan_recent_changes.py"
    if not scan_script.exists():
        return
    try:
        _sp.run(["python3", str(scan_script)], timeout=30, capture_output=True)
    except Exception:
        return
    # 변경 있으면 proactive_check를 dev_review 이유로 즉시 호출
    review = load_json(STATE / "dev_review_state.json", {})
    if review.get("has_changes"):
        proactive_check("dev_review_window")


def proactive_check(reason: str) -> None:
    mode = load_json(MODE_PATH, {}).get("current_mode", "setting")
    proactive = load_json(PROACTIVE_PATH, {})
    guard = compute_conversation_guard()
    counterpart_state = guard.get("counterpart_state", {})
    counterpart_memory = guard.get("counterpart_memory", {})
    if counterpart_memory:
        save_json(COUNTERPART_STATE_MEMORY_PATH, counterpart_memory)
    if counterpart_state:
        save_json(
            USER_CONVERSATION_STATE_PATH,
            {
                **counterpart_state,
                "schema_version": 1,
                "managed_by": "automation_worker",
                "last_updated_at": now_iso(),
            },
        )
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
    # dev_review_window: 최근 변경 사항 요약을 컨텍스트에 주입
    dev_review = load_json(STATE / "dev_review_state.json", {}) if reason == "dev_review_window" else {}
    dev_review_summary = dev_review.get("summary_for_proactive") if dev_review.get("has_changes") else None
    # 웅삐 자체 비지 블록 체크 (작업/수면 중 선톡 전면 억제)
    self_busy_state = load_json(SELF_BUSY_STATE_PATH, {})
    self_block = self_busy_state.get("current_block")
    if self_block and self_block.get("type") not in {None, "free"}:
        _until_str = self_block.get("until")
        _still_busy = True
        if _until_str:
            _now_check = now_local()
            try:
                _h, _m = (int(x) for x in _until_str.split(":"))
                if _now_check.hour * 60 + _now_check.minute >= _h * 60 + _m:
                    _still_busy = False
            except (ValueError, TypeError):
                pass
        if _still_busy:
            status = "suppressed_self_busy"
            detail = "웅삐 자체 비지 블록 중 선톡 억제 (%s)" % self_block.get("label", "바쁜 시간")
    if status == "ready" and mode != "woongbbi":
        status = "skipped_not_woongbbi_mode"
        detail = "현재 모드가 setting이라 선톡 후보를 만들지 않음"
    elif status == "ready" and in_quiet_hours:
        status = "suppressed_sleep_quiet_hours"
        detail = "수면 시간대라 후보 생성 억제"
    elif status == "ready" and guard["conversation_active"]:
        status = "suppressed_active_conversation"
        detail = "최근 대화가 진행 중이라 선톡 억제"
    elif status == "ready" and guard["waiting_reply"]:
        minutes_since_last_outgoing = float(guard.get("minutes_since_last_outgoing") or 0.0)
        unanswered_outgoing_count = int(guard.get("unanswered_outgoing_count") or 0)
        can_guard_follow_up = (
            minutes_since_last_outgoing >= follow_up_minutes and unanswered_outgoing_count <= max_follow_up
        )
        can_scheduled_follow_up = (
            minutes_since_last_outgoing >= follow_up_minutes and allow_scheduled_during_waiting_reply
        )
        can_reengage_follow_up = should_reengage_after_wait(
            minutes_since_last_outgoing,
            unanswered_outgoing_count,
            proactive,
        )
        if counterpart_state.get("should_suppress_waiting_reply"):
            status = "suppressed_waiting_context"
            detail = counterpart_state.get("reason") or "상대 상태상 후속 선톡 억제"
        elif is_guard_recheck and can_guard_follow_up:
            waiting_reply_followup = build_waiting_reply_followup(
                "guard",
                minutes_since_last_outgoing,
                counterpart_state=counterpart_state,
            )
            status = "ready"
            detail = "waiting_reply_followup_ready"
        elif is_guard_recheck and can_reengage_follow_up:
            waiting_reply_followup = build_waiting_reply_followup(
                "scheduled",
                minutes_since_last_outgoing,
                counterpart_state=counterpart_state,
            )
            status = "ready"
            detail = "waiting_reply_reengage_ready"
        elif is_scheduled_proactive and can_scheduled_follow_up:
            waiting_reply_followup = build_waiting_reply_followup(
                "scheduled",
                minutes_since_last_outgoing,
                counterpart_state=counterpart_state,
            )
            status = "ready"
            detail = "scheduled_waiting_reply_followup_ready"
        else:
            status = "suppressed_waiting_reply"
            detail = "마지막 발송 뒤 답을 기다리는 중"
    elif status == "ready" and guard["outgoing_cooldown"]:
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
                "message_options": scenario.get("examples", []),
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
            base_message = choose_proactive_message_option(
                selected.get("message_options", []) or [selected.get("message", "")],
                seed_hint=selected.get("scenario_id") or selected.get("intent_key") or candidate_type,
            )
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
        candidate_review = review_proactive_candidate(candidate, guard, counterpart_state)
        append_response_decision_log(
            "proactive_candidate",
            {
                "reason": reason,
                "candidate": candidate,
                "candidate_review": candidate_review,
                "conversation_guard": guard,
                "presence": {
                    "activity": load_json(PRESENCE_PATH, {}).get("current_activity"),
                    "surface_mood": load_json(PRESENCE_PATH, {}).get("surface_mood"),
                },
            },
        )
        if not candidate_review.get("ok"):
            status = candidate_review.get("status", "suppressed_review")
            detail = candidate_review.get("detail", "자동 선톡 검수에서 차단")
            update_voice_share_runtime(status, detail, candidate["message"], None, candidate_type)
            append_response_decision_log(
                "proactive_delivery",
                {
                    "result": "suppressed_by_review",
                    "channel": delivery_channel,
                    "candidate": candidate,
                    "candidate_review": candidate_review,
                },
            )
        elif delivery_channel == "voice":
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
                append_message_log("outgoing", "proactive_text", candidate["message"])
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
        target_activity = timer.get("target_activity")
        apply_time_block(target_activity, reason)
        check_self_busy_expiry(triggered_activity=target_activity or "")
        auto_set_self_busy_from_activity(target_activity or "")
        return "time_block_update:%s" % target_activity
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
    if timer_type == "dev_review_check":
        run_dev_review_check(reason)
        return "dev_review_check"
    if timer_type == "daily_diary":
        return write_daily_diary(reason)
    if timer_type == "periodic_tick":
        if scope == "automation_worker":
            # no-op: heartbeat already handled
            return "tick:worker"
        if scope == "conversation_guard":
            check_self_busy_expiry()
            maybe_peek_self_busy()
            check_pending_photo_promise()
            check_pending_arrival_promise()
            check_proactive_photo()
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
    due_time_block_candidates = []
    timers = timers_state.get("timers", [])
    for timer in timers:
        if timer.get("type") != "time_block_update":
            continue
        if not timer.get("enabled", True):
            continue
        if current_day_name(now_dt) not in timer.get("days", []):
            continue
        scheduled_dt = scheduled_datetime_for_timer(timer, now_dt)
        if not scheduled_dt or now_dt < scheduled_dt:
            continue
        last_fired = history.get(timer["id"])
        if last_fired and last_fired.startswith(now_dt.strftime("%Y-%m-%d")):
            continue
        due_time_block_candidates.append((scheduled_dt, timer))

    if due_time_block_candidates:
        due_time_block_candidates.sort(key=lambda item: item[0])
        _, selected_timer = due_time_block_candidates[-1]
        result = handle_timer(selected_timer)
        history[selected_timer["id"]] = now_iso()
        results.append(result)
        append_worker_note("timer %s -> %s" % (selected_timer["id"], result))

    for timer in timers:
        if timer.get("type") == "time_block_update":
            continue
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
