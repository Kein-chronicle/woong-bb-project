#!/usr/bin/env python3
"""
random_event_pool.json에서 오늘의 1~2개 micro-event를 자동 선택.
기상 시 1회 실행 (timers.json에서 wakeup 직후).
선택된 이벤트는 random_event_pool.json의 'selected_today_events'에 저장.
"""
import json
import random
import sys
from datetime import datetime
from pathlib import Path

POOL_PATH = Path("/Users/kein/Projects/woong-bb/state/random_event_pool.json")
TZ_OFFSET_KST_HOURS = 9


def kst_now_iso():
    from datetime import timedelta
    return (datetime.utcnow() + timedelta(hours=TZ_OFFSET_KST_HOURS)).isoformat() + "+09:00"


def kst_date_str():
    from datetime import timedelta
    return (datetime.utcnow() + timedelta(hours=TZ_OFFSET_KST_HOURS)).strftime("%Y-%m-%d")


def main():
    if not POOL_PATH.exists():
        print(f"pool file missing: {POOL_PATH}", file=sys.stderr)
        sys.exit(1)
    pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    rules = pool.get("rules", {})
    cats = pool.get("event_categories", {})
    if not cats:
        print("no event_categories in pool", file=sys.stderr)
        sys.exit(1)

    today = kst_date_str()
    today_seed = int(today.replace("-", ""))
    rng = random.Random(today_seed)

    min_n = rules.get("min_events_per_day", 0)
    max_n = rules.get("max_events_per_day", 2)
    n = rng.randint(min_n, max_n)

    # 카테고리 중복 피하면서 n개 선택
    chosen = []
    used_cats = set()
    cat_list = list(cats.keys())
    rng.shuffle(cat_list)
    for cat in cat_list:
        if len(chosen) >= n:
            break
        if rules.get("avoid_same_category_repeat", True) and cat in used_cats:
            continue
        events = cats[cat]
        if not events:
            continue
        # avoid_heavy_drama 필터
        if rules.get("avoid_heavy_drama", True):
            events = [e for e in events if e.get("tone") not in ("heavy", "dramatic", "negative_heavy")]
        if not events:
            continue
        ev = rng.choice(events)
        chosen.append({
            "category": cat,
            "id": ev.get("id"),
            "tone": ev.get("tone"),
            "summary": ev.get("summary"),
        })
        used_cats.add(cat)

    pool["selected_today_events"] = {
        "date": today,
        "selected_at": kst_now_iso(),
        "events": chosen,
        "seed": today_seed,
    }
    POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"selected {len(chosen)} events for {today}:")
    for e in chosen:
        print(f"  - [{e['category']}] {e['summary']} (tone={e['tone']})")


if __name__ == "__main__":
    main()
