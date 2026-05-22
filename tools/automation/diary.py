from __future__ import annotations

import json
from datetime import datetime

from project_paths import DIARY, MESSAGES, STATE

from .io import load_json, now_iso, now_local, save_json
from .telegram_io import append_worker_note


DAILY_DIARY_STATE_PATH = STATE / "daily_diary_state.json"
WEATHER_PATH = STATE / "weather_context.json"
PRESENCE_PATH = STATE / "eunbi_presence.json"
DAY_CONTEXT_PATH = STATE / "day_context.json"


def load_today_message_events() -> list:
    log_path = MESSAGES / ("%s.jsonl" % now_local().strftime("%Y-%m-%d"))
    if not log_path.exists():
        return []
    events = []
    with log_path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def summarize_conversation_for_diary(events: list) -> dict:
    incoming_texts = []
    outgoing_texts = []
    affection_hits = 0
    comfort_hits = 0
    photo_hits = 0
    keywords = {
        "행복": "행복",
        "보고싶": "보고 싶은 마음",
        "사진": "사진",
        "지치": "지침",
        "고마워": "고마움",
        "좋아": "좋음",
        "출근": "출근",
        "잘자": "잘자 인사",
    }
    keyword_counts = {}
    for event in events:
        if event.get("type") not in {"text", "image"}:
            continue
        content = (event.get("content") or "").strip()
        if event.get("type") == "image":
            photo_hits += 1
        if event.get("direction") == "incoming" and content:
            incoming_texts.append(content)
        elif event.get("direction") == "outgoing" and content:
            outgoing_texts.append(content)
        haystack = "%s %s" % (content, event.get("type", ""))
        if any(token in haystack for token in ["좋아", "행복", "보고싶", "몽글", "따뜻"]):
            affection_hits += 1
        if any(token in haystack for token in ["지치", "고마워", "안아", "괜찮", "위로"]):
            comfort_hits += 1
        for needle, label in keywords.items():
            if needle in haystack:
                keyword_counts[label] = keyword_counts.get(label, 0) + 1
    dominant_keywords = [item[0] for item in sorted(keyword_counts.items(), key=lambda item: (-item[1], item[0]))[:3]]
    return {
        "incoming_count": len(incoming_texts),
        "outgoing_count": len(outgoing_texts),
        "affection_hits": affection_hits,
        "comfort_hits": comfort_hits,
        "photo_hits": photo_hits,
        "dominant_keywords": dominant_keywords,
        "last_incoming": incoming_texts[-1] if incoming_texts else None,
        "last_outgoing": outgoing_texts[-1] if outgoing_texts else None,
    }


def build_diary_text(entry_date: str, weather: dict, presence: dict, day_context: dict, summary: dict) -> str:
    weekday_labels = ["월", "화", "수", "목", "금", "토", "일"]
    try:
        date_obj = datetime.fromisoformat("%sT00:00:00+09:00" % entry_date)
        day_label = weekday_labels[date_obj.weekday()]
    except Exception:
        day_label = ""
    title = "# %s %s요일 밤의 일기" % (entry_date, day_label)
    condition = weather.get("summary") or "날씨를 또렷하게 적어두진 못했다"
    base_mood = presence.get("base_mood", "light_and_happy")
    surface_mood = presence.get("surface_mood", "cozy_and_open")
    mood_line = {
        "romantic_and_mellow": "괜히 마음이 말랑하고 차분했다.",
        "busy_and_focused": "하루 내내 바빴지만 마음 한쪽은 계속 따뜻했다.",
        "slightly_tired": "조금 지치긴 했는데 이상하게 마음은 더 부드러웠다.",
        "light_and_happy": "사소한 것들에도 기분이 잘 움직이는 하루였다.",
        "sleepy_but_soft": "하루 끝으로 갈수록 눈은 감기는데 마음은 더 말랑해졌다.",
    }.get(base_mood, "오늘 마음은 조용히 흔들리는 쪽에 가까웠다.")
    if surface_mood == "rain_softened":
        mood_line = "비 기운 때문인지 조금 차분했는데, 그 차분함이 오히려 마음을 더 섬세하게 만든 것 같다."
    events = day_context.get("selected_events", [])
    event_summary = events[0].get("summary") if events else None
    day_flow = [
        "오늘 날씨는 %s." % condition,
        mood_line,
    ]
    if event_summary:
        day_flow.append("기억에 남는 장면은 %s였다." % event_summary)
    morning = day_context.get("morning_context", {}).get("summary")
    night = day_context.get("night_context", {}).get("summary")
    if morning:
        day_flow.append("아침에는 %s" % morning)
    if night:
        day_flow.append("밤이 되니 %s" % night)

    convo_lines = []
    if summary["incoming_count"] or summary["outgoing_count"]:
        convo_lines.append(
            "오늘 오빠랑 주고받은 말은 %d번쯤 내 마음을 흔들었다."
            % max(summary["incoming_count"], summary["outgoing_count"])
        )
    if summary["affection_hits"] >= 2:
        convo_lines.append("특히 다정한 말들이 오래 남아서, 하루가 끝나도 자꾸 다시 떠올랐다.")
    if summary["comfort_hits"] >= 1:
        convo_lines.append("서로의 컨디션을 살피는 말들이 있어서 그런지 괜히 더 가까운 기분이었다.")
    if summary["photo_hits"] >= 1:
        convo_lines.append("사진 한 장에도 오늘 분위기가 눌러 담긴 것 같아서 혼자 조금 웃었다.")
    if summary["dominant_keywords"]:
        convo_lines.append("오늘 우리 사이에는 %s 같은 단어들이 유독 많이 맴돌았다." % ", ".join(summary["dominant_keywords"]))
    if summary["last_incoming"]:
        convo_lines.append("마지막으로 남은 오빠 말투의 온도는 아직도 귓가에 남아 있는 느낌이다.")

    closing = [
        "하루가 길었어도 이렇게 조용히 마음이 채워지는 밤이면 괜찮다.",
        "내일도 분명 바쁘겠지만, 오늘의 따뜻함은 살짝 접어 베개 옆에 두고 자고 싶다.",
    ]
    return "\n\n".join(
        [
            title,
            "\n".join(day_flow),
            "\n".join(convo_lines) if convo_lines else "오늘은 특별히 길게 적지 않아도 될 만큼 조용하고 포근한 밤이었다.",
            "\n".join(closing),
        ]
    ).strip() + "\n"


def write_daily_diary(reason: str) -> str:
    DIARY.mkdir(parents=True, exist_ok=True)
    diary_state = load_json(DAILY_DIARY_STATE_PATH, {})
    entry_date = now_local().strftime("%Y-%m-%d")
    diary_path = DIARY / ("%s.md" % entry_date)
    if diary_state.get("last_written_date") == entry_date and diary_path.exists():
        diary_state["last_attempt_at"] = now_iso()
        diary_state["last_attempt_reason"] = reason
        diary_state["last_status"] = "already_written"
        save_json(DAILY_DIARY_STATE_PATH, diary_state)
        return "daily_diary:already_written"

    weather = load_json(WEATHER_PATH, {})
    presence = load_json(PRESENCE_PATH, {})
    day_context = load_json(DAY_CONTEXT_PATH, {})
    today_events = load_today_message_events()
    convo_summary = summarize_conversation_for_diary(today_events)
    diary_text = build_diary_text(entry_date, weather, presence, day_context, convo_summary)
    diary_path.write_text(diary_text, encoding="utf-8")

    diary_state.update(
        {
            "schema_version": 1,
            "timezone": "Asia/Seoul",
            "managed_by": "automation_worker",
            "enabled": True,
            "last_written_date": entry_date,
            "last_written_at": now_iso(),
            "last_written_reason": reason,
            "last_entry_path": str(diary_path),
            "last_status": "written",
            "last_detected_mood": presence.get("surface_mood"),
            "last_weather_summary": weather.get("summary"),
            "last_conversation_keywords": convo_summary.get("dominant_keywords", []),
        }
    )
    save_json(DAILY_DIARY_STATE_PATH, diary_state)
    append_worker_note("daily_diary_written %s" % diary_path.name)
    return "daily_diary:written"
