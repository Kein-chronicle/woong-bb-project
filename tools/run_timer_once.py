#!/usr/bin/env python3
import argparse
import json
import sys

from automation.io import load_json, now_iso, save_json
from automation.runtime_state import WORKER_STATE_PATH
from automation.telegram_io import append_worker_note
from project_paths import ROOT, state_path

sys.path.insert(0, str(ROOT / "tools"))
import automation_worker  # noqa: E402


TIMERS_PATH = state_path("timers.json")


def load_timer(timer_id: str) -> dict:
    timers_state = load_json(TIMERS_PATH, {})
    for timer in timers_state.get("timers", []):
        if timer.get("id") == timer_id:
            return timer
    raise KeyError(timer_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one woong-bb timer without starting the sidecar worker loop.")
    parser.add_argument("timer_id")
    parser.add_argument("--force", action="store_true", help="Run even if the timer is disabled.")
    args = parser.parse_args()

    timer = load_timer(args.timer_id)
    if not timer.get("enabled", True) and not args.force:
        print(json.dumps({"ok": False, "timer_id": args.timer_id, "reason": "timer_disabled"}, ensure_ascii=False))
        return 2

    result = automation_worker.handle_timer(timer)
    worker_state = load_json(WORKER_STATE_PATH, {})
    history = worker_state.get("timer_history", {})
    history[args.timer_id] = now_iso()
    worker_state["timer_history"] = history
    worker_state["last_run_at"] = now_iso()
    worker_state["last_result"] = "oneshot:%s:%s" % (args.timer_id, result)
    save_json(WORKER_STATE_PATH, worker_state)
    append_worker_note("oneshot_timer %s -> %s" % (args.timer_id, result))
    print(json.dumps({"ok": True, "timer_id": args.timer_id, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
