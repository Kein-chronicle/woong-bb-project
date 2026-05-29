#!/usr/bin/env python3
"""
Daily schedule generator for woong-bb.
Triggered at wakeup time (05:45 weekday / 08:30 weekend).
Generates a concrete, human-feeling daily schedule and saves to state/daily_schedule_state.json.
"""

import json
import random
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY_CONTEXT_PATH = os.path.join(ROOT, "state", "day_context.json")
OUTPUT_PATH = os.path.join(ROOT, "state", "daily_schedule_state.json")
MEDIA_HISTORY_PATH = os.path.join(ROOT, "state", "media_pick_history.json")


def pick_without_repeat(pool: list, history_key: str, days_avoid: int = 7) -> dict:
    """날짜 시드 + 최근 사용 이력 기반으로 반복 없이 항목 선택."""
    try:
        with open(MEDIA_HISTORY_PATH) as f:
            history = json.load(f)
    except Exception:
        history = {}
    today = datetime.date.today().isoformat()
    recent = history.get(history_key, [])
    # days_avoid일 이내 사용된 title 제외
    cutoff = (datetime.date.today() - datetime.timedelta(days=days_avoid)).isoformat()
    recent_titles = {r["title"] for r in recent if r.get("date", "") >= cutoff}
    candidates = [p for p in pool if p.get("title", "") not in recent_titles]
    if not candidates:
        candidates = pool  # 모두 최근 사용이면 전체에서 선택
    # 날짜 기반 시드로 결정론적 선택
    seed = int(today.replace("-", "")) % len(candidates)
    chosen = candidates[seed]
    # 이력 저장
    recent.append({"date": today, "title": chosen.get("title", "")})
    history[history_key] = recent[-30:]  # 최근 30개 보관
    try:
        with open(MEDIA_HISTORY_PATH, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return chosen

# ── Data pools ─────────────────────────────────────────────────────────────────

WEEKDAY_BREAKFAST = [
    {"menu": "없음 (커피만)", "time_offset": 0},
    {"menu": "바나나 + 우유", "time_offset": 5},
    {"menu": "토스트 + 커피", "time_offset": 10},
    {"menu": "그래놀라 + 요거트", "time_offset": 8},
    {"menu": "샌드위치 (어제 만든 거)", "time_offset": 5},
]

WEEKDAY_LUNCH = [
    {"menu": "된장찌개", "location": "집 부엌"},
    {"menu": "제육볶음", "location": "집 부엌"},
    {"menu": "순두부찌개", "location": "집 부엌"},
    {"menu": "비빔밥", "location": "집 부엌"},
    {"menu": "김치찌개", "location": "집 부엌"},
    {"menu": "돈까스", "location": "집 부엌"},
    {"menu": "쌀국수", "location": "집 부엌"},
    {"menu": "컵라면 + 냉장고 있던 거", "location": "집 부엌 (바빠서)"},
    {"menu": "샌드위치", "location": "집 부엌"},
    {"menu": "비빔국수", "location": "집 부엌"},
]

WEEKDAY_DINNER = [
    {"menu": "파스타 (토마토 소스)", "cook": "면 삶고 소스 볶기", "prep_min": 25},
    {"menu": "닭가슴살 샐러드", "cook": "닭가슴살 삶아서 채소 섞기", "prep_min": 20},
    {"menu": "볶음밥", "cook": "냉장고 재료 털어서 볶기", "prep_min": 15},
    {"menu": "된장찌개 + 밥", "cook": "된장찌개 끓이기", "prep_min": 25},
    {"menu": "제육볶음 + 밥", "cook": "돼지고기 재워서 볶기", "prep_min": 30},
    {"menu": "오므라이스", "cook": "볶음밥 싸서 달걀 부치기", "prep_min": 20},
    {"menu": "닭가슴살 오븐구이 + 브로콜리", "cook": "오븐 190도 20분", "prep_min": 30},
    {"menu": "참치 김치 볶음밥", "cook": "참치랑 김치 볶기", "prep_min": 15},
    {"menu": "계란국 + 밥", "cook": "계란 풀어서 끓이기", "prep_min": 15},
    {"menu": "냉동 만두 + 계란프라이", "cook": "팬에 굽기", "prep_min": 15},
]

WEEKDAY_EXERCISE = [
    {"type": "그림 그리기", "location": "집 데스크", "duration_min": 60},
    {"type": "러닝", "location": "한강변", "duration_min": 45, "shower": True},
    {"type": "그림 그리기", "location": "집 데스크", "duration_min": 60},
    {"type": "자전거", "location": "한강 자전거도로", "duration_min": 50, "shower": True},
    {"type": "그림 그리기", "location": "집 데스크", "duration_min": 40},
    {"type": "드라마 보기", "location": "집 침대", "duration_min": 90},
    {"type": "없음 (집)", "location": "집", "duration_min": 0, "shower": False},
]

# 간호사 오전 근무(07:59~점심) 세부 업무 풀 — 시간순으로 몇 개 뽑아 타임라인 구성
MORNING_SHIFT_TASKS = [
    "오전 작업 시작 (이전 작업 이어서)",
    "이슈 트래커 확인 및 오늘 작업 목록 정리",
    "오전 집중 작업 시작",
    "어제 남긴 코드 이어서 작업",
    "버그 확인 및 코드 리뷰",
    "새 기능 작업 시작",
    "PR 리뷰 또는 코드 검토",
    "작업 내용 정리 및 기록",
    "오빠한테 작업 진행상황 공유",
    "새 기능 구현",
]

# 오후 근무(점심 후~퇴근) 세부 업무 풀
AFTERNOON_SHIFT_TASKS = [
    "오후 집중 작업",
    "작업 마무리 및 커밋",
    "오후 작업 이어가기",
    "테스트 실행 및 버그 확인",
    "오후 작업 마무리",
    "오늘 작업 커밋 및 정리",
    "오후 코드 리뷰",
    "다음 작업 계획 메모",
]

# 그날 근무가 바빴/평범/한가했던 구체적 이유 풀 (물어보면 답할 수 있게)
BUSY_REASONS_HEAVY = [
    "오전에 예상 못한 이슈가 둘이나 터져서 대응하느라 정신없었어",
    "버그가 생각보다 복잡해서 거기 계속 붙어 있었어",
    "작업 마감이 겹쳐서 우선순위 맞추느라 밀렸어",
    "혼자 여러 작업 처리해야 해서 평소보다 많이 움직였어",
    "미팅(오빠 피드백)이 길어져서 그 뒤 작업이 다 밀렸어",
    "구현이랑 버그 수정이 겹쳐서 손이 모자랐어",
]
BUSY_REASONS_NORMAL = [
    "딱 평소만큼이라 루틴대로 흘러갔어",
    "바쁜 구간이랑 한가한 구간이 적당히 섞였어",
    "큰 사건 없이 무난하게 돌아갔어",
]
BUSY_REASONS_LIGHT = [
    "오늘은 작업이 잘 돌아가서 생각보다 여유 있었어",
    "이슈가 적어서 평소보다 여유 있었어",
    "작업이 빠르게 끝나고 밀린 게 없어서 편했어",
]
WARD_NOTABLE = [
    "오래 붙잡고 있던 기능이 오늘 완성돼서 뿌듯했어",
    "오늘 작업이 생각보다 깔끔하게 됐어",
    "새 이슈가 좀 까다로워서 분석하느라 시간 좀 썼어",
    "오빠가 방향 잡아줘서 한결 수월했어",
    "특별한 일은 없었어",
    "점심 메뉴가 의외로 괜찮아서 그게 작은 낙이었어",
]

# 퇴근 후~취침 세부 활동 풀
EVENING_AFTER_DINNER = [
    "설거지하고 주방 정리",
    "잠깐 소파에 늘어져서 폰 보기",
    "빨래 돌려놓기",
    "택배 온 거 풀기",
    "내일 입을 옷이랑 가방 미리 챙겨두기",
]
NIGHT_OTT_PICKS = [
    # 드라마/영화
    {"platform": "넷플릭스", "title": "보던 한드 다음 화", "kind": "k_drama", "detail": ""},
    {"platform": "넷플릭스", "title": "찜해둔 로맨스 영화 한 편", "kind": "movie", "detail": ""},
    {"platform": "웨이브", "title": "못 본 한드 1화부터", "kind": "k_drama", "detail": ""},
    # 예능/버라이어티
    {"platform": "유튜브", "title": "유 퀴즈 클립 몰아보기", "kind": "variety", "detail": "유퀴즈온더블럭 하이라이트 클립"},
    {"platform": "유튜브", "title": "런닝맨 명장면 쇼츠", "kind": "variety", "detail": "런닝맨 웃긴 장면 모음"},
    {"platform": "티빙", "title": "주말 못 본 예능 몰아보기", "kind": "variety", "detail": ""},
    {"platform": "유튜브", "title": "나는 솔로 클립 정주행", "kind": "variety", "detail": "나는솔로 명장면"},
    # 뷰티/라이프스타일
    {"platform": "유튜브", "title": "올리브영 신상 하울 영상", "kind": "beauty", "detail": "스킨케어 하울 리뷰"},
    {"platform": "유튜브", "title": "개발자 일상 브이로그", "kind": "vlog", "detail": "코딩 일상 vlog"},
    {"platform": "유튜브", "title": "자취방 인테리어 영상 구경", "kind": "vlog", "detail": "원룸 꾸미기 브이로그"},
    {"platform": "유튜브", "title": "개발자 일상 브이로그", "kind": "vlog", "detail": "코딩하는 일상 vlog"},
    {"platform": "유튜브", "title": "데일리 메이크업 튜토리얼", "kind": "beauty", "detail": "출근 메이크업 영상"},
    # 먹방/음식
    {"platform": "유튜브", "title": "집밥 레시피 영상", "kind": "food", "detail": "간단 요리 레시피 모음"},
    {"platform": "유튜브", "title": "혼자 먹는 분식 먹방", "kind": "food", "detail": "떡볶이 순대 먹방"},
    {"platform": "유튜브", "title": "간단 자취 요리 레시피", "kind": "food", "detail": "간단 자취 밥 레시피"},
    # 아이돌/음악
    {"platform": "유튜브", "title": "최애 아이돌 신곡 뮤비", "kind": "kpop", "detail": "케이팝 신곡 뮤직비디오"},
    {"platform": "유튜브", "title": "아이돌 쇼츠 모음 보기", "kind": "kpop", "detail": "직캠 쇼츠 모음"},
    {"platform": "유튜브", "title": "플레이리스트 틀어놓고 폰 보기", "kind": "music", "detail": "감성 팝 플레이리스트"},
    # ASMR/힐링
    {"platform": "유튜브", "title": "카페 빗소리 ASMR", "kind": "asmr", "detail": "카페 소음 ASMR 집중"},
    {"platform": "유튜브", "title": "잠 오는 ASMR 틀어놓기", "kind": "asmr", "detail": "수면 유도 ASMR"},
    {"platform": "유튜브", "title": "자연 소리 배경음 영상", "kind": "asmr", "detail": "빗소리 파도소리 힐링"},
]
NIGHT_READING_PICKS = [
    "읽던 에세이 몇 장",
    "자기계발서 조금",
    "웹툰 밀린 거 정주행",
    "잡지 가볍게 넘기기",
]
NIGHT_WINDDOWN_ACTIVITIES = [
    "스킨케어 꼼꼼히 하기",
    "가벼운 스트레칭",
    "핸드크림 바르고 폰 만지작",
    "내일 일정 캘린더 확인",
    "인스타 잠깐 둘러보기",
    "오빠랑 톡하다가 스르륵",
    "물 한 잔 마시고 불 끄기 전 뒹굴기",
    "다이어리/메모 잠깐 끄적이기",
]

# 주말 오후 활동별 구체적 세부 (물어보면 답할 수 있게)
WEEKEND_AFTERNOON_DETAIL = {
    "그림 그리기": ["디지털 드로잉 한 시간", "스케치 연습", "좋아하는 장면 그리기"],
    "음악 감상": ["플레이리스트 새로 만들기", "좋아하는 앨범 처음부터 듣기", "오빠한테 추천할 노래 찾기"],
    "서점": ["베스트셀러 코너 구경", "에세이 코너에서 한참 서서 읽기", "읽고 싶던 책 한 권 사기"],
    "전시": ["미술 전시 천천히 둘러보기", "사진전 구경하고 굿즈 사기", "팝업 전시 구경"],
    "쇼핑": ["옷 구경하면서 피팅", "화장품이랑 소품 구경", "신발 보러 돌아다니기"],
    "집에서 쉬기": ["밀린 빨래랑 청소", "침대에서 뒹굴뒹굴 영화", "방 정리하고 향초 켜기"],
    "그림 그리기": ["디지털 드로잉 집중", "스케치 연습", "오빠한테 보여줄 그림 구상"],
    "영상 보기": ["새 드라마 보기 시작", "오빠한테 추천받은 영화", "좋아하는 브이로그 몰아보기"],
}
WEEKEND_BRUNCH_WITH = ["혼자 느긋하게", "친구랑", "동생이랑", "혼자 책 보면서"]
WEEKEND_MORNING_FLOW = [
    "일어나서 물 마시고 한참 폰 보기",
    "커튼 열고 환기시키고 침구 정리",
    "느긋하게 스트레칭하고 세수",
    "알람 끄고 다시 누웠다가 천천히 일어나기",
]
WEEKEND_NOTABLE = [
    "오랜만에 늦잠 자서 개운했어",
    "날씨가 좋아서 괜히 기분이 들떴어",
    "주말이라 사람이 좀 많았어",
    "오빠 생각하면서 다음에 같이 오면 좋겠다 싶었어",
    "딱히 일정 없이 흘러가는 게 좋았어",
]

OUTFIT_WEEKDAY = [
    "기본 작업복 (흰 티셔츠 + 반바지)",
    "후디 + 반바지",
]

OUTFIT_CASUAL = [
    "흰 크롭 티 + 와이드 슬랙스",
    "린넨 셔츠 + 청바지",
    "스트라이프 블라우스 + 슬랙스",
    "니트 + 미디 스커트",
    "오버사이즈 티 + 반바지",
    "캐주얼 원피스",
    "맨투맨 + 조거 팬츠",
]

WEEKEND_BRUNCH = [
    {"menu": "아보카도 토스트 + 아메리카노", "location": "집 식탁", "time": "10:40"},
    {"menu": "팬케이크 + 라떼", "location": "집 식탁", "time": "10:30"},
    {"menu": "에그베네딕트 + 오렌지 주스", "location": "집 식탁", "time": "11:00"},
    {"menu": "오믈렛 + 빵 + 커피", "location": "집 (직접 만든 거)", "time": "10:20"},
    {"menu": "샌드위치 + 라떼", "location": "집 식탁", "time": "10:45"},
    {"menu": "그래놀라 + 요거트 + 과일", "location": "집", "time": "10:00"},
    {"menu": "크로플 + 아이스라떼", "location": "집 식탁", "time": "11:10"},
]

WEEKEND_DINNER = [
    {"menu": "파스타 (크림 소스)", "location": "집", "prep_min": 30},
    {"menu": "스테이크 + 샐러드", "location": "집", "prep_min": 35},
    {"menu": "치킨 시켜먹기", "location": "집", "prep_min": 0},
    {"menu": "초밥 (배달)", "location": "집", "prep_min": 0},
    {"menu": "삼겹살 구워먹기", "location": "집 근처 고깃집", "prep_min": 0},
    {"menu": "냉면", "location": "냉면 맛집", "prep_min": 0},
    {"menu": "마라탕", "location": "마라탕 가게", "prep_min": 0},
    {"menu": "된장찌개 + 밥", "location": "집", "prep_min": 25},
    {"menu": "제육볶음 + 밥", "location": "집", "prep_min": 30},
    {"menu": "스파게티 + 마늘빵", "location": "집", "prep_min": 30},
]

WEEKEND_EXERCISE = [
    {"type": "그림 그리기", "location": "집 데스크", "duration_min": 60},
    {"type": "러닝", "location": "한강변", "duration_min": 50},
    {"type": "자전거", "location": "한강 자전거도로", "duration_min": 70},
    {"type": "요가", "location": "집", "duration_min": 40},
    {"type": "드라마 보기", "location": "집 침대", "duration_min": 60},
    {"type": "없음", "location": "", "duration_min": 0},
]


def rand_minute(base_hhmm: str, spread: int = 10) -> str:
    """Add a small random offset to hh:mm string."""
    h, m = map(int, base_hhmm.split(":"))
    total = h * 60 + m + random.randint(-spread // 2, spread // 2)
    total = max(0, min(total, 23 * 60 + 59))
    return f"{total // 60:02d}:{total % 60:02d}"


def add_minutes(hhmm: str, minutes: int) -> str:
    h, m = map(int, hhmm.split(":"))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def generate_weekday(date_str: str, now_iso: str) -> dict:
    breakfast = random.choice(WEEKDAY_BREAKFAST)
    wakeup = rand_minute("06:00", 5)
    shower_done = add_minutes(wakeup, 15)
    breakfast_time = add_minutes(shower_done, breakfast["time_offset"])
    # 화장·헤어·옷 입기 prep 시간
    skincare_done = add_minutes(shower_done, random.randint(8, 10))
    makeup_done = add_minutes(skincare_done, random.randint(18, 22))
    dress_done = add_minutes(makeup_done, random.randint(8, 10))
    depart = add_minutes(dress_done, random.randint(2, 5))  # 작업 시작 시간 (~08:00)
    arrive_work = add_minutes(depart, 58)

    lunch = random.choice(WEEKDAY_LUNCH)
    lunch_time = rand_minute("12:10", 15)
    lunch_end = add_minutes(lunch_time, 35)

    depart_home = rand_minute("17:05", 10)
    arrive_home = add_minutes(depart_home, 60)

    dinner = random.choice(WEEKDAY_DINNER)
    dinner_start_cook = add_minutes(arrive_home, 10)
    dinner_eat = add_minutes(dinner_start_cook, dinner["prep_min"])
    dinner_end = add_minutes(dinner_eat, 30)

    exercise = random.choice(WEEKDAY_EXERCISE)
    exercise_start = add_minutes(dinner_end, 15)
    exercise_end = add_minutes(exercise_start, exercise["duration_min"]) if exercise["duration_min"] > 0 else exercise_start
    if exercise["shower"]:
        shower_after = add_minutes(exercise_end, 5)
        hair_dry = add_minutes(shower_after, 20)
        night_start = hair_dry
    else:
        shower_after = None
        hair_dry = None
        # 저녁 자유 활동은 끝나고 바로 야간 루틴 시작
        night_start = exercise_end if exercise["duration_min"] > 0 else add_minutes(dinner_end, 30)
    sleep_target = rand_minute("23:50", 15)

    # 퇴근 후~취침 세부 타임라인 구성
    ott = pick_without_repeat(NIGHT_OTT_PICKS, "night_ott")
    after_dinner_act = random.choice(EVENING_AFTER_DINNER)
    # night_start(머리 말린 직후)부터 sleep_target까지를 채우는 활동 순서
    ns_m = int(night_start.split(":")[0]) * 60 + int(night_start.split(":")[1])
    st_m = int(sleep_target.split(":")[0]) * 60 + int(sleep_target.split(":")[1])
    if st_m <= ns_m:
        st_m = ns_m + 120
    night_timeline = []
    # 스킨케어 → OTT/독서 → 마무리 winddown 순으로 배치
    skincare_t = ns_m
    night_timeline.append({"time": "%02d:%02d" % (skincare_t // 60, skincare_t % 60), "activity": "스킨케어 하고 잠옷으로 갈아입기"})
    content_t = ns_m + 15
    if random.random() < 0.7:
        night_timeline.append({"time": "%02d:%02d" % (content_t // 60, content_t % 60),
                               "activity": "%s에서 %s 보기" % (ott["platform"], ott["title"])})
        night_content_label = "%s %s" % (ott["platform"], ott["title"])
    else:
        reading = random.choice(NIGHT_READING_PICKS)
        night_timeline.append({"time": "%02d:%02d" % (content_t // 60, content_t % 60),
                               "activity": "%s" % reading})
        night_content_label = reading
    # 취침 30~40분 전 마무리 활동
    winddown_t = max(content_t + 30, st_m - 35)
    night_timeline.append({"time": "%02d:%02d" % (winddown_t // 60, winddown_t % 60),
                           "activity": random.choice(NIGHT_WINDDOWN_ACTIVITIES)})
    night_timeline.append({"time": sleep_target, "activity": "잠자리에 누워서 폰 보다가 잠들기"})

    outfit_work = random.choice(OUTFIT_WEEKDAY)
    outfit_casual = random.choice(OUTFIT_CASUAL)

    commute_options = [
        "지하철 2호선 → 버스 환승",
        "지하철 직통",
        "버스 → 지하철",
        "지하철 2호선 → 도보",
    ]

    # 오전 근무 세부 타임라인 (도착~점심 사이를 3~4개 업무로 분할)
    def build_shift_timeline(start_hhmm: str, end_hhmm: str, task_pool: list, count: int) -> list:
        start_m = int(start_hhmm.split(":")[0]) * 60 + int(start_hhmm.split(":")[1])
        end_m = int(end_hhmm.split(":")[0]) * 60 + int(end_hhmm.split(":")[1])
        span = max(end_m - start_m, count)
        tasks = random.sample(task_pool, min(count, len(task_pool)))
        slot = span // len(tasks)
        timeline = []
        for i, t in enumerate(tasks):
            tm = start_m + i * slot
            timeline.append({"time": "%02d:%02d" % (tm // 60, tm % 60), "task": t})
        return timeline

    morning_tasks = build_shift_timeline(arrive_work, lunch_time, MORNING_SHIFT_TASKS, random.choice([4, 4, 4, 3]))
    afternoon_tasks = build_shift_timeline(lunch_end, depart_home, AFTERNOON_SHIFT_TASKS, random.choice([4, 4, 3]))

    # 그날 근무 강도 + 구체적 이유 (date seed로 결정)
    busy_roll = random.random()
    if busy_roll < 0.35:
        busy_level, busy_reason = "heavy", random.choice(BUSY_REASONS_HEAVY)
    elif busy_roll < 0.75:
        busy_level, busy_reason = "normal", random.choice(BUSY_REASONS_NORMAL)
    else:
        busy_level, busy_reason = "light", random.choice(BUSY_REASONS_LIGHT)
    work_note = random.choice(WARD_NOTABLE)

    return {
        "date": date_str,
        "generated_at": now_iso,
        "day_type": "weekday",
        "morning": {
            "wakeup_time": wakeup,
            "shower_time": wakeup,
            "shower_done": shower_done,
            "morning_prep": {
                "skincare_done": skincare_done,
                "makeup_done": makeup_done,
                "dress_done": dress_done,
                "note": "세수 → 커피 → 컴퓨터 켜기 순서",
            },
            "outfit": outfit_work,
            "casual_outfit": outfit_casual,
            "breakfast": {
                "menu": breakfast["menu"],
                "time": breakfast_time,
            },
            "depart_time": depart,
        },
        "morning_prep": {
            "route": "집 컴퓨터 앞",
            "depart_time": depart,
            "arrive_time": arrive_work,
        },
        "work": {
            "busy_level": busy_level,
            "busy_reason": busy_reason,
            "work_note": work_note,
            "morning_tasks": morning_tasks,
            "afternoon_tasks": afternoon_tasks,
        },
        "lunch": {
            "menu": lunch["menu"],
            "location": lunch["location"],
            "time": lunch_time,
            "end_time": lunch_end,
            "with": "혼자",
        },
        "evening_free": {
            "depart_time": depart_home,
            "arrive_time": arrive_home,
            "note": random.choice(["작업 마무리", "컴퓨터 끄고 쉬기", "저녁 준비 시작"]),
        },
        "dinner": {
            "menu": dinner["menu"],
            "location": "집",
            "cook_note": dinner.get("cook", ""),
            "cook_start": dinner_start_cook,
            "eat_time": dinner_eat,
            "end_time": dinner_end,
        },
        "evening": {
            "activity_type": exercise["type"],
            "location": exercise["location"],
            "start_time": exercise_start,
            "duration_min": exercise["duration_min"],
            "end_time": exercise_end,
            "shower_after": shower_after,
            "hair_dry_time": hair_dry,
            "after_dinner": after_dinner_act,
        },
        "night": {
            "wind_down_start": night_start,
            "content": night_content_label,
            "ott_platform": ott["platform"],
            "ott_title": ott["title"],
            "timeline": night_timeline,
            "sleep_target": sleep_target,
        },
    }


def generate_weekend(date_str: str, now_iso: str, day_context: dict) -> dict:
    wakeup = rand_minute("08:30", 20)
    brunch = random.choice(WEEKEND_BRUNCH)
    exercise = random.choice(WEEKEND_EXERCISE)

    afternoon_options = ["그림 그리기", "드라마 보기", "요리", "집에서 쉬기", "음악 감상", "새 프로젝트 탐색"]
    afternoon = random.choice(afternoon_options)
    afternoon_detail = random.choice(WEEKEND_AFTERNOON_DETAIL.get(afternoon, ["느긋하게 보내기"]))

    dinner = random.choice(WEEKEND_DINNER)
    dinner_time = rand_minute("19:00", 30)
    if dinner["prep_min"] > 0:
        dinner_cook = add_minutes(dinner_time, -dinner["prep_min"])
        dinner_end = add_minutes(dinner_time, 35)
    else:
        dinner_cook = None
        dinner_end = add_minutes(dinner_time, 40)

    shower = rand_minute("21:00", 20)
    hair_dry = add_minutes(shower, 25)
    sleep_target = rand_minute("00:10", 20)

    outfit = random.choice(OUTFIT_CASUAL)

    # 오후 타임라인 (브런치 후~저녁 전)
    brunch_m = int(brunch["time"].split(":")[0]) * 60 + int(brunch["time"].split(":")[1])
    afternoon_start = "%02d:%02d" % ((brunch_m + 90) // 60, (brunch_m + 90) % 60)
    afternoon_timeline = [
        {"time": afternoon_start, "activity": "%s — %s" % (afternoon, afternoon_detail)},
    ]
    if exercise["type"] != "없음":
        ex_start = "%02d:%02d" % ((brunch_m + 240) // 60 % 24, (brunch_m + 240) % 60)
        afternoon_timeline.append({"time": ex_start, "activity": "%s (%s)" % (exercise["type"], exercise["location"])})

    # 야간 타임라인 (주말도 평일과 동일 구조)
    ott = pick_without_repeat(NIGHT_OTT_PICKS, "night_ott")
    hd_m = int(hair_dry.split(":")[0]) * 60 + int(hair_dry.split(":")[1])
    st_m = int(sleep_target.split(":")[0]) * 60 + int(sleep_target.split(":")[1])
    if st_m <= hd_m:
        st_m = hd_m + 120
    night_timeline = [
        {"time": hair_dry, "activity": "스킨케어 하고 잠옷으로 갈아입기"},
    ]
    content_t = hd_m + 15
    if random.random() < 0.7:
        night_timeline.append({"time": "%02d:%02d" % (content_t // 60 % 24, content_t % 60),
                               "activity": "%s에서 %s 보기" % (ott["platform"], ott["title"])})
        night_content_label = "%s %s" % (ott["platform"], ott["title"])
    else:
        reading = random.choice(NIGHT_READING_PICKS)
        night_timeline.append({"time": "%02d:%02d" % (content_t // 60 % 24, content_t % 60), "activity": reading})
        night_content_label = reading
    winddown_t = max(content_t + 30, st_m - 35)
    night_timeline.append({"time": "%02d:%02d" % (winddown_t // 60 % 24, winddown_t % 60),
                           "activity": random.choice(NIGHT_WINDDOWN_ACTIVITIES)})
    night_timeline.append({"time": sleep_target, "activity": "잠자리에 누워서 폰 보다가 잠들기"})

    weekend_note = random.choice(WEEKEND_NOTABLE)

    return {
        "date": date_str,
        "generated_at": now_iso,
        "day_type": "weekend",
        "morning": {
            "wakeup_time": wakeup,
            "stretch_or_lazy": random.choice(["스트레칭 좀 하고 일어남", "한참 누워 있다가 일어남", "알람 끄고 좀 더 있다가"]),
            "morning_flow": random.choice(WEEKEND_MORNING_FLOW),
            "outfit": outfit,
        },
        "brunch": {
            "menu": brunch["menu"],
            "location": brunch["location"],
            "time": brunch["time"],
            "with": random.choice(WEEKEND_BRUNCH_WITH),
        },
        "afternoon": {
            "plan": afternoon,
            "detail": afternoon_detail,
            "timeline": afternoon_timeline,
            "note": random.choice(["혼자", "느긋하게", "가볍게"]),
            "weekend_note": weekend_note,
        },
        "exercise": {
            "type": exercise["type"],
            "location": exercise["location"],
            "duration_min": exercise["duration_min"],
        } if exercise["type"] != "없음" else None,
        "dinner": {
            "menu": dinner["menu"],
            "location": dinner["location"],
            "cook_start": dinner_cook,
            "eat_time": dinner_time,
            "end_time": dinner_end,
        },
        "night": {
            "shower_time": shower,
            "hair_dry_time": hair_dry,
            "content": night_content_label,
            "ott_platform": ott["platform"],
            "ott_title": ott["title"],
            "timeline": night_timeline,
            "sleep_target": sleep_target,
        },
    }


def main():
    now_kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    date_str = now_kst.strftime("%Y-%m-%d")
    now_iso = now_kst.isoformat()

    # Load day context
    day_type = "weekday"
    day_context = {}
    if os.path.exists(DAY_CONTEXT_PATH):
        with open(DAY_CONTEXT_PATH, "r", encoding="utf-8") as f:
            day_context = json.load(f)
        day_type = day_context.get("day_type", "weekday")

    # Use date seed for reproducibility within same day
    seed = int(date_str.replace("-", ""))
    random.seed(seed)

    if day_type == "weekend":
        schedule = generate_weekend(date_str, now_iso, day_context)
    else:
        schedule = generate_weekday(date_str, now_iso)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)

    print(f"[daily_schedule] {date_str} ({day_type}) 일정 생성 완료 → {OUTPUT_PATH}")

    # 오늘의 YouTube picks 실제 검색
    try:
        import subprocess as _sp
        _sp.Popen(
            [sys.executable, os.path.join(os.path.dirname(__file__), "fetch_youtube_picks.py")],
            stdout=open(os.path.join(ROOT, "state", "youtube_fetch.log"), "a"),
            stderr=subprocess.STDOUT,
        )
        print("[daily_schedule] YouTube picks 검색 시작 (백그라운드)")
    except Exception as e:
        print(f"[daily_schedule] YouTube picks 검색 실패: {e}")


if __name__ == "__main__":
    main()
