#!/usr/bin/env python3
"""
Update specific fields in daily_schedule_state.json during conversation.
Usage:
  python3 update_daily_schedule.py <section> <key> <value> [--reason "..."]
  python3 update_daily_schedule.py --patch '{"dinner": {"menu": "삼겹살", "location": "고깃집"}}'
  python3 update_daily_schedule.py --show
  python3 update_daily_schedule.py --show-section dinner

Examples:
  python3 update_daily_schedule.py dinner menu "삼겹살" --reason "오빠랑 외식하기로"
  python3 update_daily_schedule.py dinner location "집 근처 고깃집"
  python3 update_daily_schedule.py dinner eat_time "19:30"
  python3 update_daily_schedule.py evening activity_type "없음 (집)" --reason "운동 취소"
  python3 update_daily_schedule.py night sleep_target "01:00" --reason "늦게 자기로"
  python3 update_daily_schedule.py morning outfit "린넨 셔츠 + 청바지" --reason "옷 바꿔 입음"
"""

import json
import argparse
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "state", "daily_schedule_state.json")


def load_state():
    if not os.path.exists(STATE_PATH):
        print(f"[ERROR] 파일 없음: {STATE_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def now_kst_iso():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=9))
    ).isoformat()


def apply_update(state, section, key, value, reason=""):
    if section not in state:
        state[section] = {}
    old_value = state[section].get(key, None)
    state[section][key] = value

    # Append to changelog
    if "changelog" not in state:
        state["changelog"] = []
    state["changelog"].append({
        "at": now_kst_iso(),
        "section": section,
        "key": key,
        "old": old_value,
        "new": value,
        "reason": reason,
    })
    return old_value


def apply_patch(state, patch: dict, reason=""):
    for section, updates in patch.items():
        if isinstance(updates, dict):
            for key, value in updates.items():
                apply_update(state, section, key, value, reason)
        else:
            # Top-level field
            old = state.get(section)
            state[section] = updates
            if "changelog" not in state:
                state["changelog"] = []
            state["changelog"].append({
                "at": now_kst_iso(),
                "section": section,
                "key": None,
                "old": old,
                "new": updates,
                "reason": reason,
            })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("section", nargs="?")
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--reason", default="", help="변경 이유")
    parser.add_argument("--patch", default="", help="JSON 패치 문자열")
    parser.add_argument("--show", action="store_true", help="현재 일정 출력")
    parser.add_argument("--show-section", default="", help="특정 섹션 출력")

    args = parser.parse_args()
    state = load_state()

    if args.show:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return

    if args.show_section:
        section_data = state.get(args.show_section, {})
        print(json.dumps(section_data, ensure_ascii=False, indent=2))
        return

    if args.patch:
        patch = json.loads(args.patch)
        apply_patch(state, patch, args.reason)
        save_state(state)
        print(f"[update_daily_schedule] 패치 적용 완료")
        return

    if not all([args.section, args.key, args.value]):
        parser.print_help()
        sys.exit(1)

    # Auto-type conversion
    value = args.value
    if value.lower() in ("true", "false"):
        value = value.lower() == "true"
    elif value.replace(":", "").isdigit() and ":" in value:
        pass  # keep as time string
    else:
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass  # keep as string

    old = apply_update(state, args.section, args.key, value, args.reason)
    save_state(state)
    print(f"[update_daily_schedule] {args.section}.{args.key}: {repr(old)} → {repr(value)}"
          + (f" ({args.reason})" if args.reason else ""))


if __name__ == "__main__":
    main()
