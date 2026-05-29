#!/usr/bin/env python3
"""
실제 YouTube 영상 검색 후 오늘의 picks를 state/daily_youtube_picks.json에 저장.
generate_daily_schedule.py에서 호출됨.
웅삐(강은비, 31세, 프로그래머) 캐릭터 취향 기반.
"""
import json, subprocess, datetime, os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(ROOT, "state", "daily_youtube_picks.json")

SEARCH_QUERIES = [
    # 뷰티/라이프
    ("뷰티", "올리브영 신상 스킨케어 하울 2025"),
    ("뷰티", "출근 데일리 메이크업 튜토리얼"),
    ("브이로그", "개발자 일상 브이로그 2025"),
    ("브이로그", "자취 일상 브이로그 서울"),
    ("브이로그", "주말 카페 브이로그 감성"),
    # 먹방/음식
    ("먹방", "편의점 신상 후기 2025"),
    ("먹방", "분식 먹방 혼자 먹기"),
    ("먹방", "자취 요리 간단 레시피"),
    # 예능/엔터
    ("예능", "유퀴즈온더블럭 하이라이트"),
    ("예능", "나는솔로 명장면 모음"),
    ("예능", "웃긴 개그 쇼츠 모음"),
    # 아이돌/음악
    ("아이돌", "케이팝 신곡 뮤직비디오 2025"),
    ("아이돌", "아이돌 쇼츠 모음 직캠"),
    # ASMR
    ("ASMR", "카페 빗소리 ASMR 집중"),
    ("ASMR", "수면 유도 ASMR 자연소리"),
]

PROACTIVE_TEMPLATES = [
    "{title} 보다가 오빠 생각났어",
    "이거 보는 중인데 ㅋㅋ 한번 봐봐 → {url}",
    "오빠 이거 알아? 진짜 웃긴데 → {url}",
    "나 지금 이거 보고 있어 ㅋㅋ {title}",
    "이거 같이 보고 싶어서 → {url}",
    "{title} 보다가 문득 보여주고 싶어서",
]

def search_youtube(query: str, max_results: int = 3) -> list:
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "--flat-playlist",
                "--print", "%(title)s\t%(url)s\t%(channel)s\t%(duration)s",
                f"ytsearch{max_results}:{query}",
                "--no-warnings",
                "--quiet",
            ],
            capture_output=True, text=True, timeout=20
        )
        picks = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            title = parts[0].strip()
            url = parts[1].strip()
            channel = parts[2].strip() if len(parts) > 2 else ""
            duration_s = float(parts[3]) if len(parts) > 3 and parts[3].replace(".", "").isdigit() else 0
            # 너무 길거나 너무 짧은 영상 제외 (30초~30분)
            if duration_s and (duration_s < 30 or duration_s > 1800):
                continue
            is_shorts = duration_s > 0 and duration_s <= 65
            picks.append({
                "title": title,
                "url": url,
                "channel": channel,
                "duration_s": int(duration_s),
                "is_shorts": is_shorts,
            })
        return picks
    except Exception:
        return []


def run():
    today = datetime.date.today().isoformat()
    # 날짜 시드로 오늘 검색할 쿼리 5개 선택
    random.seed(int(today.replace("-", "")))
    selected_queries = random.sample(SEARCH_QUERIES, min(5, len(SEARCH_QUERIES)))

    all_picks = []
    for category, query in selected_queries:
        results = search_youtube(query, max_results=2)
        for r in results:
            r["category"] = category
            r["query"] = query
            all_picks.append(r)

    # 각 영상마다 성격에 맞는 proactive 템플릿 붙이기
    random.shuffle(all_picks)
    for pick in all_picks:
        tmpl = random.choice(PROACTIVE_TEMPLATES)
        pick["proactive_hint"] = tmpl.format(title=pick["title"], url=pick["url"])

    output = {
        "date": today,
        "character": "woongbbi",
        "picks": all_picks[:8],  # 최대 8개
        "generated_at": datetime.datetime.now().isoformat(),
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[youtube_picks] {len(all_picks)} videos fetched → {OUTPUT_PATH}")


if __name__ == "__main__":
    run()
