#!/usr/bin/env python3
"""
웅삐 근무시간 자동 비지 세터
launchd에서 매일 08:00 KST에 호출됨 (시스템 타임존 KST 기준)
평일(월~금)에만 self_busy_state.json 설정, 주말은 스킵
"""
import json
import sys
import datetime
import os

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "self_busy_state.json")
KST = datetime.timezone(datetime.timedelta(hours=9))

def main():
    # 병원 근무 캐릭터 설정 제거됨 — 이 스크립트 비활성화
    print("[set_work_busy] disabled: hospital_work character removed", file=sys.stderr)
    return

    now_kst = datetime.datetime.now(KST)
    weekday = now_kst.weekday()  # 0=Mon, 6=Sun

    # 주말 스킵
    if weekday >= 5:
        print(f"[set_work_busy] weekend (weekday={weekday}), skipping", file=sys.stderr)
        return

    # 현재 시간 확인 — 08:00~17:00 사이일 때만 세팅
    hour = now_kst.hour
    if hour < 7 or hour >= 17:
        print(f"[set_work_busy] outside work window (hour={hour} KST), skipping", file=sys.stderr)
        return

    now_iso = now_kst.astimezone(datetime.timezone.utc).isoformat()

    data = {
        "current_block": {
            "type": "hospital_work",
            "label": "병원 근무",
            "until": "17:00",
            "started_at": now_iso,
        },
        "updated_at": now_iso,
        "updated_by": "work_busy_scheduler",
    }

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[set_work_busy] set hospital_work busy until 17:00 KST (weekday={weekday})", file=sys.stderr)

if __name__ == "__main__":
    main()
