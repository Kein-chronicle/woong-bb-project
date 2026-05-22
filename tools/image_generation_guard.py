#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone

from project_paths import log_path, runtime_path, state_path

STATE_PATH = state_path("image_generation_guard.json")
LOCK_PATH = runtime_path("image_generation.lock")
SETTINGS_PATH = state_path("image_generation_settings.json")
DECISION_LOG_PATH = log_path("response_decision_log.jsonl")


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


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {
            "schema_version": 1,
            "managed_by": "image_generation_settings",
            "generation_enabled": False,
            "changed_at": None,
            "changed_by": None,
            "change_reason": None,
            "when_disabled": {
                "proactive_image_send": "disabled",
                "direct_photo_request_woongbbi": "defer_without_guard_check",
                "direct_photo_request_setting": "report_disabled_without_guard_check",
            },
            "notes": "전역 이미지 생성 on/off 스위치. off면 guard 확인 전에 즉시 생성 불가 처리한다",
        }
    return json.loads(SETTINGS_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")


def append_decision_log(decision_type: str, payload: dict) -> None:
    DECISION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DECISION_LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(
            json.dumps(
                {
                    "timestamp": now_iso(),
                    "decision_type": decision_type,
                    **payload,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


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


def readiness(settings: dict, state: dict) -> dict:
    state_stale = is_stale(state)
    generation_enabled = bool(settings.get("generation_enabled"))
    active = bool(state.get("active"))
    if not generation_enabled:
        return {
            "can_generate": False,
            "blocking_reason": "generation_disabled",
            "recommended_action": "set-enabled --enabled true",
            "safe_to_auto_clear": False,
        }
    if active and state_stale:
        return {
            "can_generate": False,
            "blocking_reason": "stale_lock",
            "recommended_action": "clear-stale",
            "safe_to_auto_clear": True,
        }
    if active:
        return {
            "can_generate": False,
            "blocking_reason": "active_lock",
            "recommended_action": "wait_or_release_with_matching_owner",
            "safe_to_auto_clear": False,
        }
    return {
        "can_generate": True,
        "blocking_reason": None,
        "recommended_action": "acquire",
        "safe_to_auto_clear": False,
    }


def cmd_status(_args) -> int:
    state = load_state()
    settings = load_settings()
    state["stale"] = is_stale(state)
    save_state(state)
    return emit(
        {
            "ok": True,
            "settings": {
                "generation_enabled": bool(settings.get("generation_enabled")),
                "changed_at": settings.get("changed_at"),
                "changed_by": settings.get("changed_by"),
                "change_reason": settings.get("change_reason"),
            },
            "guard": state,
            "readiness": readiness(settings, state),
        }
    )


def cmd_set_enabled(args) -> int:
    settings = load_settings()
    enabled = str(args.enabled).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}
    settings.update(
        {
            "generation_enabled": enabled,
            "changed_at": now_iso(),
            "changed_by": args.changed_by,
            "change_reason": args.reason,
            "last_result": "enabled" if enabled else "disabled",
        }
    )
    save_settings(settings)
    append_decision_log(
        "image_generation_setting_changed",
        {
            "generation_enabled": enabled,
            "changed_by": args.changed_by,
            "reason": args.reason,
        },
    )
    return emit({"ok": True, "generation_enabled": enabled, "settings_path": str(SETTINGS_PATH)})


def cmd_acquire(args) -> int:
    settings = load_settings()
    if not bool(settings.get("generation_enabled")):
        return emit(
            {
                "ok": False,
                "reason": "generation_disabled",
                "recommended_action": "set-enabled --enabled true",
            },
            6,
        )
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
    stale = is_stale(state)
    active = bool(state.get("active"))
    owner = state.get("owner_tag")
    if active and not stale and not args.owner_tag and not args.force_authorized:
        return emit(
            {
                "ok": False,
                "reason": "owner_required_for_active_lock",
                "owner_tag": owner,
                "hint": "use release --owner-tag <owner> or clear-stale if stale",
            },
            4,
        )
    if args.owner_tag and owner and owner != args.owner_tag and not args.force_authorized:
        return emit({"ok": False, "reason": "owner_mismatch"}, 4)
    if args.force_authorized and not args.reason:
        return emit({"ok": False, "reason": "force_release_requires_reason"}, 4)
    result = "force_released" if args.force_authorized else "released"
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
            "last_result": result,
            "last_error": None,
        }
    )
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()
    save_state(state)
    append_decision_log(
        "image_generation_guard_released",
        {
            "result": result,
            "previous_owner_tag": owner,
            "previous_stale": stale,
            "reason": args.reason,
        },
    )
    return emit({"ok": True, "result": result})


def cmd_clear_stale(_args) -> int:
    state = load_state()
    if not is_stale(state):
        return emit({"ok": False, "reason": "not_stale"}, 5)
    previous_owner = state.get("owner_tag")
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
    append_decision_log(
        "image_generation_guard_cleared_stale",
        {
            "previous_owner_tag": previous_owner,
        },
    )
    return emit({"ok": True, "result": "cleared_stale"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="woong-bb image generation guard")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    set_enabled = sub.add_parser("set-enabled")
    set_enabled.add_argument("--enabled", required=True)
    set_enabled.add_argument("--changed-by", default="setting_mode")
    set_enabled.add_argument("--reason", default="explicit image generation setting update")

    acquire = sub.add_parser("acquire")
    acquire.add_argument("--owner-tag", default=None)
    acquire.add_argument("--session-kind", default="telegram_codex")
    acquire.add_argument("--purpose", default="image_request")
    acquire.add_argument("--ttl-seconds", type=int, default=1800)

    touch = sub.add_parser("touch")
    touch.add_argument("--owner-tag", default=None)

    release = sub.add_parser("release")
    release.add_argument("--owner-tag", default=None)
    release.add_argument("--force-authorized", action="store_true")
    release.add_argument("--reason", default=None)

    sub.add_parser("clear-stale")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "status":
        return cmd_status(args)
    if args.command == "set-enabled":
        return cmd_set_enabled(args)
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
