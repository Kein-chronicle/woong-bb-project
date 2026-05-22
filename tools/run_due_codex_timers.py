#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Optional

from automation.io import load_json, now_iso, now_local, save_json
from automation.runtime_state import WORKER_STATE_PATH
from automation.telegram_io import append_worker_note
from project_paths import ROOT, state_path

sys.path.insert(0, str(ROOT / "tools"))
import automation_worker  # noqa: E402


TIMERS_PATH = state_path("timers.json")
DISPATCH_STATE_PATH = state_path("codex_timer_dispatch_state.json")
SKIPPED_PERIODIC_SCOPES = {"automation_worker", "conversation_guard"}


def day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def day_name(dt: datetime) -> str:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt.weekday()]


def parse_timer_datetime(timer: dict, now_dt: datetime) -> Optional[datetime]:
    scheduled = timer.get("time")
    if not scheduled:
        return None
    hour, minute = [int(part) for part in scheduled.split(":", 1)]
    return now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def was_fired_today(dispatch_state: dict, timer_id: str, now_dt: datetime) -> bool:
    last = dispatch_state.get("last_fired_at", {}).get(timer_id)
    return bool(last and last.startswith(day_key(now_dt)))


def fixed_timer_due(timer: dict, dispatch_state: dict, now_dt: datetime, lookback_minutes: int) -> bool:
    if day_name(now_dt) not in timer.get("days", []):
        return False
    scheduled_dt = parse_timer_datetime(timer, now_dt)
    if not scheduled_dt:
        return False
    if was_fired_today(dispatch_state, timer["id"], now_dt):
        return False
    window_start = now_dt - timedelta(minutes=lookback_minutes)
    return window_start <= scheduled_dt <= now_dt


def periodic_timer_due(timer: dict, dispatch_state: dict, now_dt: datetime) -> bool:
    if timer.get("scope") in SKIPPED_PERIODIC_SCOPES:
        return False
    interval = int(timer.get("interval_seconds", 3600))
    minimum_interval = max(interval, 3600)
    last = dispatch_state.get("last_fired_at", {}).get(timer["id"])
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (now_dt - last_dt).total_seconds() >= minimum_interval


def due_timers(timers: list[dict], dispatch_state: dict, now_dt: datetime, lookback_minutes: int) -> list[dict]:
    due = []
    for timer in timers:
        if not timer.get("enabled", True):
            continue
        if timer.get("type") == "periodic_tick":
            if periodic_timer_due(timer, dispatch_state, now_dt):
                due.append(timer)
            continue
        if fixed_timer_due(timer, dispatch_state, now_dt, lookback_minutes):
            due.append(timer)
    return due


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch due woong-bb timers from Codex cron.")
    parser.add_argument("--lookback-minutes", type=int, default=75)
    args = parser.parse_args()

    timers_state = load_json(TIMERS_PATH, {})
    dispatch_state = load_json(
        DISPATCH_STATE_PATH,
        {
            "schema_version": 1,
            "managed_by": "codex_timer_dispatcher",
            "last_checked_at": None,
            "last_fired_at": {},
            "history": [],
            "notes": "Codex cron dispatcher for fixed-time timers and low-frequency maintenance ticks.",
        },
    )
    now_dt = now_local()
    fired = []
    errors = []
    for timer in due_timers(timers_state.get("timers", []), dispatch_state, now_dt, args.lookback_minutes):
        try:
            result = automation_worker.handle_timer(timer)
            fired.append({"timer_id": timer["id"], "result": result})
            dispatch_state.setdefault("last_fired_at", {})[timer["id"]] = now_iso()
            append_worker_note("codex_dispatch_timer %s -> %s" % (timer["id"], result))
        except Exception as exc:
            errors.append({"timer_id": timer.get("id"), "error": str(exc)})

    worker_state = load_json(WORKER_STATE_PATH, {})
    history = worker_state.get("timer_history", {})
    for item in fired:
        history[item["timer_id"]] = now_iso()
    worker_state["timer_history"] = history
    worker_state["enabled"] = False
    worker_state["recommended_runtime"] = "codex_cron_dispatcher"
    worker_state["last_run_at"] = now_iso()
    worker_state["last_result"] = "codex_dispatch:%d_fired:%d_errors" % (len(fired), len(errors))
    save_json(WORKER_STATE_PATH, worker_state)

    dispatch_state["last_checked_at"] = now_iso()
    dispatch_state.setdefault("history", []).append(
        {
            "checked_at": now_iso(),
            "lookback_minutes": args.lookback_minutes,
            "fired": fired,
            "errors": errors,
        }
    )
    dispatch_state["history"] = dispatch_state["history"][-100:]
    save_json(DISPATCH_STATE_PATH, dispatch_state)

    print(json.dumps({"ok": not errors, "fired": fired, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
