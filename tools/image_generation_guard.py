#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


STATE_PATH = Path("/Users/kein/Desktop/woong-bb/state/image_generation_guard.json")
LOCK_PATH = Path("/Users/kein/Desktop/woong-bb/state/image_generation.lock")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "schema_version": 1,
            "managed_by": "image_generation_guard",
            "enabled": True,
            "active": False,
            "owner_tag": None,
            "pid": None,
            "session_kind": None,
            "purpose": None,
            "acquired_at": None,
            "last_touch_at": None,
            "ttl_seconds": 1800,
            "stale": False,
            "last_release_at": None,
            "last_result": None,
            "last_error": None,
        }
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, PermissionError, ValueError):
        return False
    return True


def is_stale(state: dict) -> bool:
    if not state.get("active"):
        return False
    if not pid_alive(state.get("pid")):
        return True
    last_touch = state.get("last_touch_at")
    ttl = int(state.get("ttl_seconds") or 0)
    if not last_touch or ttl <= 0:
        return False
    try:
        touched = datetime.fromisoformat(last_touch)
    except ValueError:
        return True
    age = datetime.now(tz=touched.tzinfo or timezone.utc) - touched
    return age.total_seconds() > ttl


def emit(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return code


def cmd_status(_args) -> int:
    state = load_state()
    state["stale"] = is_stale(state)
    save_state(state)
    return emit(state)


def cmd_acquire(args) -> int:
    state = load_state()
    state["stale"] = is_stale(state)
    owner_tag = args.owner_tag or f"{socket.gethostname()}:{os.getpid()}"
    if state.get("active") and not state.get("stale"):
        return emit(
            {
                "ok": False,
                "reason": "locked",
                "owner_tag": state.get("owner_tag"),
                "pid": state.get("pid"),
                "purpose": state.get("purpose"),
                "last_touch_at": state.get("last_touch_at"),
            },
            2,
        )
    LOCK_PATH.write_text(owner_tag + "\n")
    state.update(
        {
            "active": True,
            "owner_tag": owner_tag,
            "pid": os.getpid(),
            "session_kind": args.session_kind,
            "purpose": args.purpose,
            "acquired_at": now_iso(),
            "last_touch_at": now_iso(),
            "ttl_seconds": args.ttl_seconds,
            "stale": False,
            "last_result": "acquired",
            "last_error": None,
        }
    )
    save_state(state)
    return emit({"ok": True, "result": "acquired", "owner_tag": owner_tag})


def cmd_touch(args) -> int:
    state = load_state()
    if not state.get("active"):
        return emit({"ok": False, "reason": "not_active"}, 3)
    if args.owner_tag and state.get("owner_tag") != args.owner_tag:
        return emit({"ok": False, "reason": "owner_mismatch"}, 4)
    state["last_touch_at"] = now_iso()
    state["stale"] = False
    state["last_result"] = "touched"
    save_state(state)
    return emit({"ok": True, "result": "touched"})


def cmd_release(args) -> int:
    state = load_state()
    if args.owner_tag and state.get("owner_tag") and state.get("owner_tag") != args.owner_tag:
        return emit({"ok": False, "reason": "owner_mismatch"}, 4)
    state.update(
        {
            "active": False,
            "owner_tag": None,
            "pid": None,
            "session_kind": None,
            "purpose": None,
            "acquired_at": None,
            "last_touch_at": None,
            "stale": False,
            "last_release_at": now_iso(),
            "last_result": "released",
            "last_error": None,
        }
    )
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()
    save_state(state)
    return emit({"ok": True, "result": "released"})


def cmd_clear_stale(_args) -> int:
    state = load_state()
    if not is_stale(state):
        return emit({"ok": False, "reason": "not_stale"}, 5)
    state.update(
        {
            "active": False,
            "owner_tag": None,
            "pid": None,
            "session_kind": None,
            "purpose": None,
            "acquired_at": None,
            "last_touch_at": None,
            "stale": False,
            "last_release_at": now_iso(),
            "last_result": "cleared_stale",
            "last_error": None,
        }
    )
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()
    save_state(state)
    return emit({"ok": True, "result": "cleared_stale"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="woong-bb image generation guard")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    acquire = sub.add_parser("acquire")
    acquire.add_argument("--owner-tag", default=None)
    acquire.add_argument("--session-kind", default="telegram_codex")
    acquire.add_argument("--purpose", default="image_request")
    acquire.add_argument("--ttl-seconds", type=int, default=1800)

    touch = sub.add_parser("touch")
    touch.add_argument("--owner-tag", default=None)

    release = sub.add_parser("release")
    release.add_argument("--owner-tag", default=None)

    sub.add_parser("clear-stale")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "status":
        return cmd_status(args)
    if args.command == "acquire":
        return cmd_acquire(args)
    if args.command == "touch":
        return cmd_touch(args)
    if args.command == "release":
        return cmd_release(args)
    if args.command == "clear-stale":
        return cmd_clear_stale(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
