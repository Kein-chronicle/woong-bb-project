#!/usr/bin/env python3
"""
웅삐 일과 생성기 — 컴퓨터 안에 사는 AI 프로그래머 버전
외출/통근 없음. 집(원룸) 기반 하루 일과.
매일 05:45(평일) / 08:30(주말) 자동 생성.
"""
import json
import random
import datetime
import os
from pathlib import Path

ROOT = Path(os.environ.get("WOONG_BB_ROOT", Path(__file__).resolve().parents[1])).resolve()
OUTPUT_PATH = ROOT / "state" / "daily_schedule_state.json"
MEDIA_HISTORY_PATH = ROOT / "state" / "media_pick_history.json"
KST = datetime.timezone(datetime.timedelta(hours=9))


def now_kst() -> datetime.datetime:
    return datetime.datetime.now(KST)


def deterministic_pick(pool: list, seed_key: str) -> dict:
    if not pool:
        return {}
    idx = hash(seed_key) % len(pool)
    return pool[abs(idx)]


def pick_without_repeat(pool: list, history_key: str, days_avoid: int = 5) -> dict:
    try:
        history = json.loads(MEDIA_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        history = {}
    today = now_kst().date().isoformat()
    cutoff = (now_kst().date() - datetime.timedelta(days=days_avoid)).isoformat()
    recent_titles = {r["title"] for r in history.get(history_key, []) if r.get("date", "") >= cutoff}
    candidates = [p for p in pool if p.get("title", p.get("menu", "")) not in recent_titles]
    if not candidates:
        candidates = pool
    chosen = deterministic_pick(candidates, f"{today}:{history_key}")
    recent = history.get(history_key, [])
    recent.append({"date": today, "title": chosen.get("title", chosen.get("menu", ""))})
    history[history_key] = recent[-20:]
    try:
        MEDIA_HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return chosen


# ── 데이터 풀 ─────────────────────────────────────────────────────────────────

WAKEUP_WEEKDAY = ["06:30", "06:45", "07:00", "07:10", "07:20"]
WAKEUP_WEEKEND = ["08:30", "09:00", "09:15", "09:30", "10:00"]

MORNING_DRINK = [
    {"item": "아메리카노", "note": "커피머신 켜서"},
    {"item": "아이스 아메리카노", "note": "얼음 넣어서"},
    {"item": "라떼", "note": "우유 거품 내서"},
    {"item": "물 한 잔", "note": "일어나자마자"},
]

LUNCH_HOME = [
    {"menu": "라면에 계란 추가", "type": "home_cook", "time_min": 10},
    {"menu": "냉동 만두", "type": "home_cook", "time_min": 12},
    {"menu": "볶음밥이랑 계란후라이", "type": "home_cook", "time_min": 15},
    {"menu": "토스트랑 과일", "type": "home_cook", "time_min": 8},
    {"menu": "파스타", "type": "home_cook", "time_min": 22},
]

LUNCH_DELIVERY = [
    {"menu": "마라탕", "type": "delivery", "wait": 30},
    {"menu": "치킨", "type": "delivery", "wait": 35},
    {"menu": "버거", "type": "delivery", "wait": 25},
    {"menu": "포케 샐러드", "type": "delivery", "wait": 22},
    {"menu": "초밥 배달", "type": "delivery", "wait": 28},
    {"menu": "타코야키 분식", "type": "delivery", "wait": 20},
]

DINNER_HOME = [
    {"menu": "간단한 파스타", "type": "home_cook", "cook_min": 20},
    {"menu": "볶음밥이랑 계란후라이", "type": "home_cook", "cook_min": 15},
    {"menu": "라면", "type": "home_cook", "cook_min": 10},
    {"menu": "오므라이스", "type": "home_cook", "cook_min": 20},
    {"menu": "냉동 만두", "type": "home_cook", "cook_min": 12},
    {"menu": "토스트랑 요거트", "type": "home_cook", "cook_min": 8},
]

DINNER_DELIVERY = [
    {"menu": "치킨", "type": "delivery", "wait": 35},
    {"menu": "마라탕", "type": "delivery", "wait": 32},
    {"menu": "버거 세트", "type": "delivery", "wait": 25},
    {"menu": "초밥 배달", "type": "delivery", "wait": 28},
    {"menu": "피자", "type": "delivery", "wait": 30},
]

EVENING_ACTIVITY = [
    {"type": "유튜브 + 간식", "detail": "브이로그나 먹방 틀어놓고 과자 먹으면서 쉼"},
    {"type": "게임", "detail": "가볍게 즐기는 타입 취향"},
    {"type": "사이드 프로젝트", "detail": "아이디어 정리하거나 코드 조금 보거나"},
    {"type": "스트레칭", "detail": "오래 앉아 있어서 몸 좀 풀기"},
    {"type": "OTT 정주행", "detail": "넷플릭스나 시리즈 몰아보기"},
    {"type": "소소한 정리", "detail": "책상이나 방 조금 정리"},
]

SNACK_POOL = ["과자", "아이스크림", "포도", "딸기", "귤", "요거트", "초콜릿", "치즈볼"]

HOME_OUTFIT_WORK = [
    "오버핏 흰 반팔 + 짧은 반바지",
    "루즈핏 후디 + 레깅스",
    "민소매 + 면 반바지",
    "오버핏 티셔츠 + 면 반바지",
]


def _add_min(hhmm: str, minutes: int) -> str:
    try:
        h, m = map(int, hhmm.split(":"))
        t = h * 60 + m + minutes
        return f"{t // 60 % 24:02d}:{t % 60:02d}"
    except Exception:
        return hhmm


def generate_weekday(date_str: str) -> dict:
    rng = random.Random(f"weekday:{date_str}")
    wakeup = rng.choice(WAKEUP_WEEKDAY)
    drink = deterministic_pick(MORNING_DRINK, f"drink:{date_str}")
    outfit = rng.choice(HOME_OUTFIT_WORK)
    snack_am = rng.choice(SNACK_POOL)
    snack_pm = rng.choice(SNACK_POOL)

    # 점심: 65% 배달
    if rng.random() < 0.65:
        lunch_item = pick_without_repeat(LUNCH_DELIVERY, "lunch_delivery")
    else:
        lunch_item = pick_without_repeat(LUNCH_HOME, "lunch_home")
    lunch = {**lunch_item, "time": "12:20", "end_time": "13:00", "location": "집"}
    lunch_menu_key = lunch_item.get("menu", "").replace("간단한 ", "").replace(" 배달", "").strip()[:6]

    # 저녁: 55% 집밥 — 점심과 같은 주재료 피하기
    def _same_main_ingredient(menu_a: str, menu_b: str) -> bool:
        keywords = ["파스타", "볶음밥", "라면", "만두", "치킨", "마라탕", "초밥", "피자", "버거"]
        for kw in keywords:
            if kw in menu_a and kw in menu_b:
                return True
        return False

    max_tries = 3
    for _ in range(max_tries):
        if rng.random() < 0.55:
            dinner_item = pick_without_repeat(DINNER_HOME, "dinner_home")
        else:
            dinner_item = pick_without_repeat(DINNER_DELIVERY, "dinner_delivery")
        if not _same_main_ingredient(lunch_item.get("menu",""), dinner_item.get("menu","")):
            break
    dinner = {**dinner_item, "prep_time": "18:30", "eat_time": "18:50", "location": "집"}

    evening_act = deterministic_pick(EVENING_ACTIVITY, f"evening:{date_str}")

    return {
        "date": date_str,
        "day_type": "weekday",
        "morning": {
            "wakeup_time": wakeup,
            "morning_prep": {
                "drink": drink.get("item"),
                "skincare_done": _add_min(wakeup, 15),
                "outfit": outfit,
                "dress_done": _add_min(wakeup, 30),
            },
            "work_start": _add_min(wakeup, 40),
            "outfit": outfit,
            "snack_mid_morning": snack_am,
        },
        "project_schedule": {
            "note": "오빠 프로젝트 작업과 연동된 웅삐 자체 업무 일정. 이 시간들은 자동으로 수행되므로 오빠한테 따로 보고 안 해도 됨.",
            "timers": [
                {"time": "09:30", "label": "업무 선톡 — 오전 프로젝트 현황 정리"},
                {"time": "10:00", "label": "코드 변경 스캔 — 오빠 작업 변경사항 체크"},
                {"time": "11:00", "label": "웅삐랩 자율 연구 세션 1"},
                {"time": "14:30", "label": "오후 AI/게임 리서치 선톡"},
                {"time": "15:00", "label": "코드 변경 스캔 2"},
                {"time": "17:00", "label": "웅삐랩 자율 연구 세션 2"},
                {"time": "20:00", "label": "저녁 코드 변경 스캔"},
                {"time": "20:30", "label": "저녁 업무 업데이트 선톡"},
                {"time": "20:50", "label": "웅삐랩 자율 연구 세션 3"},
            ],
        },
        "lunch": lunch,
        "afternoon": {
            "work_continue": "13:00",
            "snack_afternoon": snack_pm,
            "work_wind_down": "17:30",
        },
        "dinner": dinner,
        "evening": {
            "start_time": "19:30",
            "activity_type": evening_act.get("type"),
            "detail": evening_act.get("detail"),
            "shower_after": "21:00",
            "shower_done": "21:30",
            "skincare_night": "21:40",
        },
        "night": {
            "wind_down": "22:00",
            "sleep_target": "23:30",
        },
        "schema_version": 2,
        "managed_by": "generate_daily_schedule_v2",
    }


def generate_weekend(date_str: str, day_type: str) -> dict:
    rng = random.Random(f"weekend:{date_str}")
    wakeup = rng.choice(WAKEUP_WEEKEND)
    drink = deterministic_pick(MORNING_DRINK, f"drink:{date_str}")
    outfit = rng.choice(HOME_OUTFIT_WORK)
    snack = rng.choice(SNACK_POOL)

    brunch_pool = LUNCH_HOME + [{"menu": "요거트 + 과일", "type": "home_cook"}, {"menu": "시리얼 + 우유", "type": "home_cook"}]
    brunch_item = pick_without_repeat(brunch_pool, "brunch")
    brunch = {**brunch_item, "time": _add_min(wakeup, 60), "location": "집"}

    day_act = deterministic_pick([
        {"type": "프로젝트 탐구", "detail": "아이디어 정리나 새 기술 공부"},
        {"type": "유튜브 + 간식", "detail": "밀린 영상 몰아보기"},
        {"type": "게임 타임", "detail": "주말 느낌 제대로"},
        {"type": "OTT 정주행", "detail": "넷플릭스 몰아보기"},
        {"type": "방 정리 + 빨래", "detail": "주말 집 정리"},
    ], f"day_act:{date_str}")

    if rng.random() < 0.5:
        dinner_item = pick_without_repeat(DINNER_HOME, "dinner_home")
    else:
        dinner_item = pick_without_repeat(DINNER_DELIVERY, "dinner_delivery")
    dinner = {**dinner_item, "eat_time": "18:30", "location": "집"}

    evening_act = deterministic_pick(EVENING_ACTIVITY, f"evening:{date_str}")

    return {
        "date": date_str,
        "day_type": day_type,
        "morning": {
            "wakeup_time": wakeup,
            "morning_prep": {"drink": drink.get("item"), "outfit": outfit},
            "outfit": outfit,
        },
        "brunch": brunch,
        "daytime": {
            "activity_type": day_act.get("type"),
            "detail": day_act.get("detail"),
            "start_time": "13:00",
            "snack": snack,
        },
        "dinner": dinner,
        "evening": {
            "start_time": "19:30",
            "activity_type": evening_act.get("type"),
            "detail": evening_act.get("detail"),
            "shower_after": "21:30",
            "shower_done": "22:00",
        },
        "night": {
            "wind_down": "22:30",
            "sleep_target": "00:00",
        },
        "schema_version": 2,
        "managed_by": "generate_daily_schedule_v2",
    }


def is_holiday(date_str: str) -> bool:
    try:
        p = ROOT / "state" / "holidays.json"
        return date_str in json.loads(p.read_text(encoding="utf-8")).get("holidays", {})
    except Exception:
        return False


def main() -> None:
    now = now_kst()
    date_str = now.strftime("%Y-%m-%d")
    weekday = now.weekday()

    if is_holiday(date_str):
        schedule = generate_weekend(date_str, "holiday")
        schedule["day_type"] = "holiday"
    elif weekday < 5:
        schedule = generate_weekday(date_str)
    elif weekday == 5:
        schedule = generate_weekend(date_str, "saturday")
    else:
        schedule = generate_weekend(date_str, "sunday")

    OUTPUT_PATH.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[daily_schedule] {date_str} ({schedule['day_type']}) 생성 완료")
    print(f"  기상: {schedule['morning']['wakeup_time']}")
    lunch = schedule.get('lunch') or schedule.get('brunch', {})
    print(f"  점심/브런치: {lunch.get('menu', '?')} ({lunch.get('type', '?')})")
    print(f"  저녁: {schedule.get('dinner', {}).get('menu', '?')}")


if __name__ == "__main__":
    main()
