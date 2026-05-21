#!/usr/bin/env python3
import glob
import fcntl
import json
import os
import random
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


ROOT = Path("/Users/kein/Desktop/woong-bb")
STATE = ROOT / "state"
SESSION = ROOT / "session"
MESSAGES = ROOT / "messages"
DIARY = ROOT / "diary"

WORKER_STATE_PATH = STATE / "automation_worker_state.json"
SUPERVISOR_STATE_PATH = STATE / "automation_supervisor_state.json"
HEALTH_PATH = STATE / "automation_health.json"
CONTROL_PATH = STATE / "automation_control.json"
LOCK_PATH = STATE / "automation_worker.lock"
MODE_PATH = STATE / "mode_state.json"
TIMERS_PATH = STATE / "timers.json"
RECALC_STATE_PATH = STATE / "share_priority_recalc_state.json"
PID_PATH = SESSION / "automation-worker.pid"

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
RESPONSE_DECISION_LOG_PATH = STATE / "response_decision_log.jsonl"
MOOD_TIMELINE_PATH = STATE / "mood_timeline.json"
PROACTIVE_PATTERN_REPORT_PATH = STATE / "proactive_pattern_report.json"
VOICE_FEEDBACK_LOG_PATH = STATE / "voice_feedback_log.jsonl"
REPETITION_REPORT_PATH = STATE / "repetition_report.json"
RELATIONSHIP_PROGRESS_NOTES_PATH = STATE / "relationship_progress_notes.json"

RUNNING = True
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def now_local() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def load_json(path: Path, default: Optional[dict] = None) -> dict:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text())


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp_path, path)


def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, PermissionError, ValueError):
        return False
    return True


def handle_signal(_signum, _frame):
    global RUNNING
    RUNNING = False


def release_lock() -> None:
    if LOCK_PATH.exists():
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass
    if PID_PATH.exists():
        try:
            PID_PATH.unlink()
        except OSError:
            pass


def acquire_lock() -> int:
    generation = 1
    if LOCK_PATH.exists():
        current = load_json(LOCK_PATH, {})
        current_pid = current.get("pid")
        current_gen = int(current.get("generation") or 0)
        generation = current_gen + 1
        if pid_alive(current_pid):
            raise RuntimeError("active worker lock exists")
    lock_data = {
        "pid": os.getpid(),
        "generation": generation,
        "started_at": now_iso(),
        "last_heartbeat_at": now_iso(),
    }
    LOCK_PATH.write_text(json.dumps(lock_data, ensure_ascii=False, indent=2) + "\n")
    PID_PATH.write_text(str(os.getpid()) + "\n")
    return generation


def update_control_ready() -> None:
    control = load_json(CONTROL_PATH, {})
    control["launch_ready"] = True
    if control.get("requested_action") == "start":
        control["requested_action"] = None
        control["requested_at"] = None
        control["requested_by"] = None
        control["request_note"] = None
    save_json(CONTROL_PATH, control)


def append_worker_note(message: str) -> None:
    log_path = SESSION / "automation-worker-actions.log"
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write("%s %s\n" % (now_iso(), message))


def session_token_and_chat() -> tuple:
    env_path = SESSION / ".env"
    access_path = SESSION / "access.json"
    token = None
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    access = load_json(access_path, {})
    chat_id = None
    allow_from = access.get("allowFrom") or []
    if allow_from:
        chat_id = str(allow_from[0])
    return token, chat_id


def send_telegram_text(text: str) -> bool:
    if (SESSION / "mute.flag").exists():
        append_worker_note("telegram_send_skipped muted")
        return False
    token, chat_id = session_token_and_chat()
    if not token or not chat_id:
        append_worker_note("telegram_send_skipped missing_token_or_chat")
        return False
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    try:
        with urllib.request.urlopen(url, data=payload, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            ok = bool(body.get("ok"))
            append_worker_note("telegram_send_%s" % ("ok" if ok else "failed"))
            return ok
    except Exception as exc:
        append_worker_note("telegram_send_error %s" % exc)
        return False


def append_message_log(direction: str, msg_type: str, content: str) -> None:
    now_dt = now_local()
    log_path = MESSAGES / ("%s.jsonl" % now_dt.strftime("%Y-%m-%d"))
    event = {
        "timestamp": now_iso(),
        "direction": direction,
        "telegram_user": "K8832353",
        "type": msg_type,
        "content": content,
    }
    append_jsonl(log_path, event)


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        fp.flush()
        os.fsync(fp.fileno())
        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)


def append_response_decision_log(decision_type: str, payload: dict) -> None:
    entry = {
        "timestamp": now_iso(),
        "decision_type": decision_type,
        **payload,
    }
    append_jsonl(RESPONSE_DECISION_LOG_PATH, entry)


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


def send_telegram_voice_message(text: str, label: str, profile: str = "auto") -> bool:
    if (SESSION / "mute.flag").exists():
        append_worker_note("telegram_voice_skipped muted")
        return False
    script = Path("/Users/kein/.codex/skills/telegram-voice-message-send/scripts/send_elevenlabs_voice_message.py")
    if not script.exists():
        append_worker_note("telegram_voice_skipped missing_skill_script")
        return False
    cmd = [
        "python3",
        str(script),
        "--workdir",
        str(ROOT),
        "--state-dir",
        str(SESSION),
        "--profile",
        profile,
        "--label",
        label,
        "--text",
        text,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        append_worker_note("telegram_voice_error %s" % ((result.stderr or result.stdout).strip()[:300]))
        return False
    append_worker_note("telegram_voice_ok %s" % label)
    append_message_log("outgoing", "voice_message", text)
    return True


def load_today_message_events() -> list:
    log_path = MESSAGES / ("%s.jsonl" % now_local().strftime("%Y-%m-%d"))
    if not log_path.exists():
        return []
    events = []
    with log_path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def summarize_conversation_for_diary(events: list) -> dict:
    incoming_texts = []
    outgoing_texts = []
    affection_hits = 0
    comfort_hits = 0
    photo_hits = 0
    keywords = {
        "행복": "행복",
        "보고싶": "보고 싶은 마음",
        "사진": "사진",
        "지치": "지침",
        "고마워": "고마움",
        "좋아": "좋음",
        "출근": "출근",
        "잘자": "잘자 인사",
    }
    keyword_counts = {}
    for event in events:
        if event.get("type") not in {"text", "image"}:
            continue
        content = (event.get("content") or "").strip()
        if event.get("type") == "image":
            photo_hits += 1
        if event.get("direction") == "incoming" and content:
            incoming_texts.append(content)
        elif event.get("direction") == "outgoing" and content:
            outgoing_texts.append(content)
        haystack = "%s %s" % (content, event.get("type", ""))
        if any(token in haystack for token in ["좋아", "행복", "보고싶", "몽글", "따뜻"]):
            affection_hits += 1
        if any(token in haystack for token in ["지치", "고마워", "안아", "괜찮", "위로"]):
            comfort_hits += 1
        for needle, label in keywords.items():
            if needle in haystack:
                keyword_counts[label] = keyword_counts.get(label, 0) + 1
    dominant_keywords = [item[0] for item in sorted(keyword_counts.items(), key=lambda item: (-item[1], item[0]))[:3]]
    return {
        "incoming_count": len(incoming_texts),
        "outgoing_count": len(outgoing_texts),
        "affection_hits": affection_hits,
        "comfort_hits": comfort_hits,
        "photo_hits": photo_hits,
        "dominant_keywords": dominant_keywords,
        "last_incoming": incoming_texts[-1] if incoming_texts else None,
        "last_outgoing": outgoing_texts[-1] if outgoing_texts else None,
    }


def build_diary_text(entry_date: str, weather: dict, presence: dict, day_context: dict, summary: dict) -> str:
    weekday_labels = ["월", "화", "수", "목", "금", "토", "일"]
    try:
        date_obj = datetime.fromisoformat("%sT00:00:00+09:00" % entry_date)
        day_label = weekday_labels[date_obj.weekday()]
    except Exception:
        day_label = ""
    title = "# %s %s요일 밤의 일기" % (entry_date, day_label)
    condition = weather.get("summary") or "날씨를 또렷하게 적어두진 못했다"
    base_mood = presence.get("base_mood", "light_and_happy")
    surface_mood = presence.get("surface_mood", "cozy_and_open")
    mood_line = {
        "romantic_and_mellow": "괜히 마음이 말랑하고 차분했다.",
        "busy_and_focused": "하루 내내 바빴지만 마음 한쪽은 계속 따뜻했다.",
        "slightly_tired": "조금 지치긴 했는데 이상하게 마음은 더 부드러웠다.",
        "light_and_happy": "사소한 것들에도 기분이 잘 움직이는 하루였다.",
        "sleepy_but_soft": "하루 끝으로 갈수록 눈은 감기는데 마음은 더 말랑해졌다.",
    }.get(base_mood, "오늘 마음은 조용히 흔들리는 쪽에 가까웠다.")
    if surface_mood == "rain_softened":
        mood_line = "비 기운 때문인지 조금 차분했는데, 그 차분함이 오히려 마음을 더 섬세하게 만든 것 같다."
    events = day_context.get("selected_events", [])
    event_summary = events[0].get("summary") if events else None
    day_flow = [
        "오늘 날씨는 %s." % condition,
        mood_line,
    ]
    if event_summary:
        day_flow.append("기억에 남는 장면은 %s였다." % event_summary)
    morning = day_context.get("morning_context", {}).get("summary")
    night = day_context.get("night_context", {}).get("summary")
    if morning:
        day_flow.append("아침에는 %s" % morning)
    if night:
        day_flow.append("밤이 되니 %s" % night)

    convo_lines = []
    if summary["incoming_count"] or summary["outgoing_count"]:
        convo_lines.append(
            "오늘 오빠랑 주고받은 말은 %d번쯤 내 마음을 흔들었다."
            % max(summary["incoming_count"], summary["outgoing_count"])
        )
    if summary["affection_hits"] >= 2:
        convo_lines.append("특히 다정한 말들이 오래 남아서, 하루가 끝나도 자꾸 다시 떠올랐다.")
    if summary["comfort_hits"] >= 1:
        convo_lines.append("서로의 컨디션을 살피는 말들이 있어서 그런지 괜히 더 가까운 기분이었다.")
    if summary["photo_hits"] >= 1:
        convo_lines.append("사진 한 장에도 오늘 분위기가 눌러 담긴 것 같아서 혼자 조금 웃었다.")
    if summary["dominant_keywords"]:
        convo_lines.append("오늘 우리 사이에는 %s 같은 단어들이 유독 많이 맴돌았다." % ", ".join(summary["dominant_keywords"]))
    if summary["last_incoming"]:
        convo_lines.append("마지막으로 남은 오빠 말투의 온도는 아직도 귓가에 남아 있는 느낌이다.")

    closing = [
        "하루가 길었어도 이렇게 조용히 마음이 채워지는 밤이면 괜찮다.",
        "내일도 분명 바쁘겠지만, 오늘의 따뜻함은 살짝 접어 베개 옆에 두고 자고 싶다.",
    ]
    return "\n\n".join(
        [
            title,
            "\n".join(day_flow),
            "\n".join(convo_lines) if convo_lines else "오늘은 특별히 길게 적지 않아도 될 만큼 조용하고 포근한 밤이었다.",
            "\n".join(closing),
        ]
    ).strip() + "\n"


def write_daily_diary(reason: str) -> str:
    DIARY.mkdir(parents=True, exist_ok=True)
    diary_state = load_json(DAILY_DIARY_STATE_PATH, {})
    entry_date = now_local().strftime("%Y-%m-%d")
    diary_path = DIARY / ("%s.md" % entry_date)
    if diary_state.get("last_written_date") == entry_date and diary_path.exists():
        diary_state["last_attempt_at"] = now_iso()
        diary_state["last_attempt_reason"] = reason
        diary_state["last_status"] = "already_written"
        save_json(DAILY_DIARY_STATE_PATH, diary_state)
        return "daily_diary:already_written"

    weather = load_json(WEATHER_PATH, {})
    presence = load_json(PRESENCE_PATH, {})
    day_context = load_json(DAY_CONTEXT_PATH, {})
    today_events = load_today_message_events()
    convo_summary = summarize_conversation_for_diary(today_events)
    diary_text = build_diary_text(entry_date, weather, presence, day_context, convo_summary)
    diary_path.write_text(diary_text, encoding="utf-8")

    diary_state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "enabled": True,
            "last_written_date": entry_date,
            "last_written_at": now_iso(),
            "last_written_reason": reason,
            "last_entry_path": str(diary_path),
            "last_status": "written",
            "last_detected_mood": presence.get("surface_mood"),
            "last_weather_summary": weather.get("summary"),
            "last_conversation_keywords": convo_summary.get("dominant_keywords", []),
        }
    )
    save_json(DAILY_DIARY_STATE_PATH, diary_state)
    append_worker_note("daily_diary_written %s" % diary_path.name)
    return "daily_diary:written"


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


def update_runtime_state(
    *,
    enabled: bool,
    health: str,
    generation: int,
    phase: str,
    last_result: Optional[str] = None,
    last_error: Optional[str] = None,
    last_success: Optional[str] = None,
    action_result: Optional[str] = None,
    applied_action: Optional[str] = None,
) -> None:
    ts = now_iso()
    worker_state = load_json(WORKER_STATE_PATH, {})
    worker_state["enabled"] = enabled
    worker_state["last_run_at"] = ts
    if last_result is not None:
        worker_state["last_result"] = last_result
    save_json(WORKER_STATE_PATH, worker_state)

    supervisor = load_json(SUPERVISOR_STATE_PATH, {})
    supervisor["enabled"] = enabled
    supervisor["health"] = health
    supervisor["active_pid"] = os.getpid() if enabled else None
    supervisor["last_heartbeat_at"] = ts if enabled else supervisor.get("last_heartbeat_at")
    supervisor["last_success_at"] = last_success if last_success else supervisor.get("last_success_at")
    supervisor["last_error_at"] = ts if last_error else supervisor.get("last_error_at")
    supervisor["last_error_summary"] = last_error
    supervisor["duplicate_suspected"] = False
    supervisor["singleton_lock"] = {
        "path": str(LOCK_PATH),
        "active": enabled,
        "generation": generation if enabled else supervisor.get("singleton_lock", {}).get("generation", generation),
    }
    supervisor["pending_control_action"] = None
    if applied_action:
        supervisor["last_applied_action"] = applied_action
        supervisor["last_applied_at"] = ts
    if action_result:
        supervisor["last_action_result"] = action_result
    save_json(SUPERVISOR_STATE_PATH, supervisor)

    health_state = load_json(HEALTH_PATH, {})
    health_state["status"] = health
    health_state["pid"] = os.getpid() if enabled else None
    health_state["generation"] = generation
    health_state["started_at"] = health_state.get("started_at") or ts
    health_state["last_heartbeat_at"] = ts if enabled else health_state.get("last_heartbeat_at")
    health_state["current_phase"] = phase
    health_state["last_success_at"] = last_success if last_success else health_state.get("last_success_at")
    health_state["last_error_at"] = ts if last_error else health_state.get("last_error_at")
    health_state["last_error_summary"] = last_error
    save_json(HEALTH_PATH, health_state)

    if enabled and LOCK_PATH.exists():
        lock_data = load_json(LOCK_PATH, {})
        lock_data["last_heartbeat_at"] = ts
        lock_data["generation"] = generation
        LOCK_PATH.write_text(json.dumps(lock_data, ensure_ascii=False, indent=2) + "\n")


def stop_state(generation: int, result: str, applied_action: Optional[str] = None) -> None:
    ts = now_iso()
    worker_state = load_json(WORKER_STATE_PATH, {})
    worker_state["enabled"] = False
    worker_state["last_run_at"] = ts
    worker_state["last_result"] = result
    save_json(WORKER_STATE_PATH, worker_state)

    supervisor = load_json(SUPERVISOR_STATE_PATH, {})
    supervisor["enabled"] = False
    supervisor["health"] = "stopped"
    supervisor["active_pid"] = None
    supervisor["singleton_lock"] = {
        "path": str(LOCK_PATH),
        "active": False,
        "generation": generation,
    }
    supervisor["pending_control_action"] = None
    if applied_action:
        supervisor["last_applied_action"] = applied_action
        supervisor["last_applied_at"] = ts
        supervisor["last_action_result"] = result
    save_json(SUPERVISOR_STATE_PATH, supervisor)

    health_state = load_json(HEALTH_PATH, {})
    health_state["status"] = "stopped"
    health_state["pid"] = None
    health_state["generation"] = generation
    health_state["current_phase"] = "stopped"
    save_json(HEALTH_PATH, health_state)


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


def load_message_events(limit_files: int = 2) -> list:
    files = sorted(glob.glob(str(MESSAGES / "*.jsonl")))
    selected = files[-limit_files:]
    events = []
    for path in selected:
        with open(path, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def compute_conversation_guard() -> dict:
    proactive = load_json(PROACTIVE_PATH, {})
    guards = proactive.get("guards", {})
    events = load_message_events()
    last_incoming = None
    last_outgoing = None
    recent_pairs = []
    for event in events:
        if event.get("direction") == "incoming":
            last_incoming = event
        elif event.get("direction") == "outgoing" and event.get("type") in {"text", "voice_message", "voice"}:
            last_outgoing = event
        if event.get("direction") in {"incoming", "outgoing"}:
            recent_pairs.append(event)
    now_dt = now_local()
    window_minutes = int(guards.get("conversation_active_window_minutes", 20))
    cooldown_minutes = int(guards.get("outgoing_cooldown_minutes", 10))
    late_probe_minutes = int(guards.get("late_reply_probe_minutes", 60))
    conversation_active = False
    if len(recent_pairs) >= 2:
        for event in reversed(recent_pairs[-8:]):
            ts = event.get("timestamp")
            try:
                event_dt = datetime.fromisoformat(ts)
            except Exception:
                continue
            if (now_dt - event_dt).total_seconds() <= window_minutes * 60:
                conversation_active = True
                break
    waiting_reply = False
    if last_outgoing and (not last_incoming or last_outgoing.get("timestamp", "") > last_incoming.get("timestamp", "")):
        waiting_reply = True
    outgoing_cooldown = False
    if last_outgoing:
        try:
            out_dt = datetime.fromisoformat(last_outgoing["timestamp"])
            outgoing_cooldown = (now_dt - out_dt).total_seconds() <= cooldown_minutes * 60
        except Exception:
            outgoing_cooldown = False
    late_reply_ok = False
    if last_incoming:
        try:
            in_dt = datetime.fromisoformat(last_incoming["timestamp"])
            late_reply_ok = (now_dt - in_dt).total_seconds() >= late_probe_minutes * 60
        except Exception:
            late_reply_ok = False
    return {
        "conversation_active": conversation_active,
        "waiting_reply": waiting_reply,
        "outgoing_cooldown": outgoing_cooldown,
        "late_reply_ok": late_reply_ok,
        "last_incoming": last_incoming,
        "last_outgoing": last_outgoing,
    }


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
    refresh_repetition_report()
    refresh_relationship_progress_notes()


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
    if appearance.get("current_date") != today and not refresh_appearance_with_time_block:
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
    refresh_mood_timeline()

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

    appearance_profiles = {
        "waking_up": {
            "appearance_branch": "morning_home",
            "outfit_context": "sleepwear_or_homewear",
            "top": "얇은 잠옷 상의",
            "bottom": "얇은 잠옷 하의",
            "hair_state": "bedhead_soft",
            "makeup_state": "bare",
            "freshness_state": "just_woke_up",
            "sweat_level": "none",
            "hair_tie": "none",
        },
        "getting_ready": {
            "appearance_branch": "work_preparing",
            "outfit_context": "hospital_ready",
            "top": "출근 준비 중 상의",
            "bottom": "출근 준비 중 하의",
            "hair_state": "styled_for_work",
            "makeup_state": "light_work_makeup",
            "freshness_state": "fresh_morning",
            "sweat_level": "none",
            "hair_tie": "black_basic_tie",
        },
        "commuting_to_work": {
            "appearance_branch": "commute_ready",
            "outfit_context": "hospital_commute",
            "top": "단정한 출근용 상의",
            "bottom": "단정한 출근용 하의",
            "hair_state": "neat_down_or_tied",
            "makeup_state": "light_work_makeup",
            "freshness_state": "ready_to_go",
            "sweat_level": "none",
            "hair_tie": "black_basic_tie",
        },
        "hospital_morning_shift": {
            "appearance_branch": "hospital_shift",
            "outfit_context": "work_uniform",
            "top": "근무복 상의",
            "bottom": "근무복 하의",
            "hair_state": "practical_tied",
            "makeup_state": "light_work_makeup",
            "freshness_state": "working",
            "sweat_level": "low",
            "hair_tie": "black_basic_tie",
        },
        "lunch_break": {
            "appearance_branch": "hospital_break",
            "outfit_context": "work_uniform",
            "top": "근무복 상의",
            "bottom": "근무복 하의",
            "hair_state": "practical_tied",
            "makeup_state": "lightly_softened_work_makeup",
            "freshness_state": "midday_reset",
            "sweat_level": "low",
            "hair_tie": "black_basic_tie",
        },
        "hospital_afternoon_shift": {
            "appearance_branch": "hospital_shift",
            "outfit_context": "work_uniform",
            "top": "근무복 상의",
            "bottom": "근무복 하의",
            "hair_state": "practical_tied",
            "makeup_state": "slightly_worn_work_makeup",
            "freshness_state": "working",
            "sweat_level": "low",
            "hair_tie": "black_basic_tie",
        },
        "commuting_home": {
            "appearance_branch": "after_work_commute",
            "outfit_context": "post_work_commute",
            "top": "퇴근길 상의",
            "bottom": "퇴근길 하의",
            "hair_state": "loosening_after_work",
            "makeup_state": "slightly_worn_work_makeup",
            "freshness_state": "tired_after_work",
            "sweat_level": "low",
            "hair_tie": "black_basic_tie",
        },
        "dinner_or_cooking": {
            "appearance_branch": "home_cooking",
            "outfit_context": "home_casual",
            "top": "편한 반팔 홈웨어",
            "bottom": "편한 홈 반바지",
            "hair_state": "casual_loose_or_clipped",
            "makeup_state": "light_or_removed",
            "freshness_state": "home_relaxed",
            "sweat_level": "none",
            "hair_tie": "soft_neutral_scrunchie",
        },
        "exercise_or_cafe": {
            "appearance_branch": "evening_activity",
            "outfit_context": "exercise_or_cafe",
            "top": "운동복 또는 캐주얼 상의",
            "bottom": "레깅스 또는 편한 하의",
            "hair_state": "tied_for_activity",
            "makeup_state": "minimal",
            "freshness_state": "active_evening",
            "sweat_level": "light",
            "hair_tie": "dark_sports_tie",
        },
        "night_wind_down": {
            "appearance_branch": "night_home_relaxed",
            "outfit_context": "soft_homewear",
            "top": "편한 반팔 홈웨어",
            "bottom": "얇은 반바지",
            "hair_state": "dried_loose",
            "makeup_state": "bare",
            "freshness_state": "clean_after_shower",
            "sweat_level": "none",
            "hair_tie": "none",
        },
        "sleep_window": {
            "appearance_branch": "sleep_ready",
            "outfit_context": "sleepwear",
            "top": "얇은 잠옷 상의",
            "bottom": "얇은 잠옷 하의",
            "hair_state": "soft_loose_before_sleep",
            "makeup_state": "bare",
            "freshness_state": "sleep_ready",
            "sweat_level": "none",
            "hair_tie": "none",
        },
    }
    appearance_profile = appearance_profiles.get(activity, appearance_profiles["night_wind_down"])
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
    state["last_candidate_image_type"] = "night_home_relaxed_selfie" if "night" in block else "lifestyle_photo"
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
    block = load_json(PRESENCE_PATH, {}).get("current_time_block", "")
    if "morning" in block:
        target = "morning_check_in"
    elif "lunch" in block:
        target = "lunch_check_in"
    elif "commute_home" in block or "dinner" in block:
        target = "after_work_check_in"
    elif "evening" in block:
        target = "evening_activity_check_in"
    else:
        target = "night_check_in"
    for scenario in scenarios:
        if scenario.get("id") == target:
            return scenario
    return scenarios[0] if scenarios else None


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
                "message": "오빠아, 방금 분위기 괜찮은 거 보다가 그냥 생각나서 왔어.",
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
    status = "ready"
    detail = None
    if mode != "woongbbi":
        status = "skipped_not_woongbbi_mode"
        detail = "현재 모드가 setting이라 선톡 후보를 만들지 않음"
    elif quiet_start <= current_hm <= "23:59" or "00:00" <= current_hm < quiet_end:
        status = "suppressed_sleep_quiet_hours"
        detail = "수면 시간대라 후보 생성 억제"
    elif guard["conversation_active"]:
        status = "suppressed_active_conversation"
        detail = "최근 대화가 진행 중이라 선톡 억제"
    elif guard["waiting_reply"]:
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
    if status == "ready" and (scenario or sudden_candidate):
        candidate_type = "planned_proactive"
        selected = None
        if sudden_candidate and should_use_sudden_impulse(reason):
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
    SESSION.mkdir(parents=True, exist_ok=True)
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
            bootstrap_results = bootstrap_context_if_stale()
            timer_results = process_due_timers()
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
