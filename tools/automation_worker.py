#!/usr/bin/env python3
import glob
import json
import os
import random
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
IMAGE_SETTINGS_PATH = STATE / "image_generation_settings.json"
IMAGE_GUARD_PATH = STATE / "image_generation_guard.json"
REINFORCEMENT_STATE_PATH = STATE / "user_preference_reinforcement.json"

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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


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
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(event, ensure_ascii=False) + "\n")


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
        elif event.get("direction") == "outgoing" and event.get("type") == "text":
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
    day_context = load_json(DAY_CONTEXT_PATH, {})
    random_pool = load_json(RANDOM_EVENT_POOL_PATH, {})
    appearance = load_json(APPEARANCE_PATH, {})

    day_name = current_day_name(now_dt)
    workday = day_name in {"mon", "tue", "wed", "thu", "fri"}
    profile = activity_profile(activity, workday)
    energy = profile["energy"]
    if weather.get("current_condition") == "rain":
        energy -= 4
    if weather.get("current_condition") == "cloudy":
        energy -= 1
    affection = max(78, int(presence.get("affection_level", 82)))
    care_bias = max(80, int(presence.get("care_bias", 82))) + int(weather.get("care_bias_bonus", 0))
    surface = profile["surface"]
    if weather.get("current_condition") == "rain" and activity in {"waking_up", "night_wind_down", "commuting_home"}:
        surface = "rain_softened"

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
            "generated_at": now_iso(),
            "valid_until": (now_dt + timedelta(hours=2)).isoformat(timespec="seconds"),
        }
    )
    save_json(PRESENCE_PATH, presence)

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

    scenario = choose_proactive_scenario()
    candidate = None
    if status == "ready" and scenario:
        candidate = {
            "scenario_id": scenario.get("id"),
            "intent": scenario.get("intent"),
            "message": scenario.get("examples", [""])[0],
            "created_at": now_iso(),
            "reason": reason,
        }
        if send_telegram_text(candidate["message"]):
            append_message_log("outgoing", "text", candidate["message"])
            status = "sent"
            detail = "자동 선톡 발송 완료"
        else:
            status = "deferred"
            detail = "자동 선톡 전송 실패 또는 보류"
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
