from __future__ import annotations

import glob
import json
import re
from datetime import datetime
from typing import Optional

from project_paths import MESSAGES, STATE

from .io import load_json, now_local


PROACTIVE_PATH = STATE / "proactive_messages.json"
AUTOMATED_OUTGOING_TYPES = {"proactive_text", "event_trigger_text", "voice_message", "voice"}
ANY_OUTGOING_TYPES = AUTOMATED_OUTGOING_TYPES | {"text"}

SLEEP_PATTERNS = ["잠들", "잘자", "잘 자", "눈감긴", "자야", "자러", "졸려", "졸리", "푹 자", "잘게", "이제 잘래"]
WAKE_PATTERNS = ["일어났", "깼어", "잠 깼", "기상", "눈 떴", "방금 일어"]
WORK_PATTERNS = ["일하", "근무", "업무", "회의", "바빠", "바쁜", "출근", "퇴근 전", "회사", "일 중", "작업 중"]
WORK_END_PATTERNS = ["퇴근", "일 끝", "업무 끝", "끝났", "한가", "마무리", "집 가는 중"]
DRIVE_PATTERNS = ["운전", "이동 중", "가는 중", "도착할", "휴게소", "차 타", "지하철", "버스", "기차", "비행기"]
ARRIVAL_PATTERNS = ["도착했", "도착했어", "도착함", "집 왔", "집에 왔", "돌아왔", "내렸", "내려서", "왔어", "와서"]
REST_PATTERNS = ["쉬는 중", "누워있", "누워 있어", "누워서", "침대", "쉬고 있어", "뻗었"]
REST_END_PATTERNS = ["일어났", "나왔", "나가는 중", "준비했", "준비 중"]
MEAL_PATTERNS = ["밥 먹", "저녁 먹", "점심 먹", "식사", "먹는 중", "밥준비", "밥 준비", "식사 중", "브런치"]
MEAL_END_PATTERNS = ["다 먹", "먹었", "식사 끝", "밥 다", "배불", "치웠"]
SICK_PATTERNS = ["아프", "몸살", "감기", "열나", "열 나", "두통", "컨디션 안", "속 안 좋", "병원 다녀", "약 먹"]
RECOVERY_PATTERNS = ["괜찮아졌", "이제 괜찮", "나았", "회복", "멀쩡", "좀 나아", "다 나았"]
TRAVEL_PATTERNS = ["출장", "여행", "타지", "지방", "해외", "숙소", "호텔", "비행기 타"]
RETURN_PATTERNS = ["돌아왔", "복귀", "집 도착", "귀가", "다녀왔", "한국 왔", "서울 왔"]
GOODNIGHT_PATTERNS = ["잘 자", "좋은 꿈", "푹 자", "편하게 쉬어", "조용히 옆에", "잠들면 돼"]
WEEKEND_PLAN_PATTERNS = ["주말", "토요일", "일요일", "이번주말", "이번 주말"]
PLAN_COMMIT_PATTERNS = ["가기로", "가자", "보기로", "만나기로", "약속", "예약", "놀러", "먹기로", "보기로 했", "하기로"]
LOCATION_HINT_PATTERNS = ["지금", "방금", "오늘", "어제", "도착했", "와있", "와 있어", "있어", "있는 중"]
CONFIG_SIGNAL_PATTERNS = [
    "/users/",
    ".json",
    ".jsonl",
    ".md",
    "세팅모드",
    "설정파일",
    "폴더",
    "파일",
    "automation",
    "worker",
    "이미지 생성",
    "image generation",
    "state/",
    "profile/",
    "tools/",
    "프로젝트",
    "코드",
    "스크립트",
    "깃허브",
]
NON_STATE_REQUEST_PATTERNS = ["해줘", "보여줘", "얘기해줘", "설정", "구성", "만들어", "상상", "궁금", "있으면 좋겠", "하자"]
SELF_STATE_MARKERS = ["나 ", "난 ", "내가", "오빠 ", "오빠가", "지금", "방금", "오늘", "어제", "이제", "곧"]
SPECULATIVE_PATTERNS = ["가보네", "같네", "같아", "인가", "아냐", "일까"]
FUTURE_INTENT_PATTERNS = ["야겠다", "하려고", "할거야", "할 거야", "갈거야", "갈 거야"]

STATE_SPECS = [
    {
        "key": "sleeping_or_falling_asleep",
        "start_patterns": SLEEP_PATTERNS,
        "end_patterns": WAKE_PATTERNS + WORK_PATTERNS + DRIVE_PATTERNS + MEAL_PATTERNS + ARRIVAL_PATTERNS,
        "summary": "자는 중이거나 잠드는 흐름",
        "availability": "offline",
        "followup_policy": "suppress",
        "tone_hint": "quiet_reassuring",
        "confidence": 0.97,
        "priority": 100,
    },
    {
        "key": "sick_or_unwell",
        "start_patterns": SICK_PATTERNS,
        "end_patterns": RECOVERY_PATTERNS,
        "summary": "아프거나 컨디션이 안 좋은 상태",
        "availability": "limited",
        "followup_policy": "soft_only",
        "tone_hint": "caring",
        "confidence": 0.93,
        "priority": 95,
    },
    {
        "key": "driving_or_in_transit",
        "start_patterns": DRIVE_PATTERNS,
        "end_patterns": ARRIVAL_PATTERNS,
        "summary": "운전 중이거나 이동 중",
        "availability": "limited",
        "followup_policy": "soft_only",
        "tone_hint": "low_pressure",
        "confidence": 0.9,
        "priority": 90,
    },
    {
        "key": "traveling_or_on_business_trip",
        "start_patterns": TRAVEL_PATTERNS,
        "end_patterns": RETURN_PATTERNS,
        "summary": "출장/여행 등으로 평소 위치를 벗어난 상태",
        "availability": "limited",
        "followup_policy": "soft_only",
        "tone_hint": "patient",
        "confidence": 0.88,
        "priority": 80,
    },
    {
        "key": "working_or_busy",
        "start_patterns": WORK_PATTERNS,
        "end_patterns": WORK_END_PATTERNS + ARRIVAL_PATTERNS,
        "summary": "일하거나 바쁜 상태",
        "availability": "limited",
        "followup_policy": "soft_only",
        "tone_hint": "patient",
        "confidence": 0.84,
        "priority": 70,
    },
    {
        "key": "resting",
        "start_patterns": REST_PATTERNS,
        "end_patterns": REST_END_PATTERNS + WORK_PATTERNS + DRIVE_PATTERNS,
        "summary": "쉬는 중이거나 누워 있는 상태",
        "availability": "limited",
        "followup_policy": "soft_only",
        "tone_hint": "gentle",
        "confidence": 0.78,
        "priority": 60,
    },
    {
        "key": "eating",
        "start_patterns": MEAL_PATTERNS,
        "end_patterns": MEAL_END_PATTERNS,
        "summary": "식사 중이거나 식사 준비 중",
        "availability": "limited",
        "followup_policy": "soft_only",
        "tone_hint": "casual",
        "confidence": 0.72,
        "priority": 50,
    },
]
STATE_SPEC_BY_KEY = {spec["key"]: spec for spec in STATE_SPECS}


def load_message_events(limit_files: int = 2) -> list:
    files = sorted(glob.glob(str(MESSAGES / "*.jsonl")))
    selected = files[-limit_files:]
    events = []
    for path in selected:
        with open(path, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    def event_sort_key(event: dict) -> tuple:
        timestamp = event.get("timestamp", "")
        dt = parse_event_timestamp(timestamp)
        if not dt:
            return (float("-inf"), timestamp)
        return (dt.timestamp(), timestamp)

    events.sort(key=event_sort_key)
    return events


def parse_event_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return None


def event_text(event: Optional[dict]) -> str:
    if not event:
        return ""
    content = event.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    caption = event.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    return ""


def contains_any(text: str, patterns: list[str]) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    compact = normalized.replace(" ", "")
    return any(pattern.replace(" ", "") in compact for pattern in patterns)


def is_human_state_signal(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(token in lowered for token in CONFIG_SIGNAL_PATTERNS):
        return False
    if len(text) > 260 and any(token in text for token in ["설정", "규칙", "로직", "구성", "시스템"]):
        return False
    return True


def is_direct_state_statement(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return False
    if "?" in normalized:
        return False
    if any(token in normalized for token in NON_STATE_REQUEST_PATTERNS):
        return False
    if any(token in normalized for token in FUTURE_INTENT_PATTERNS):
        return False
    if any(token in normalized for token in SELF_STATE_MARKERS):
        return True
    if any(token in normalized for token in SPECULATIVE_PATTERNS):
        return False
    return normalized.endswith(("했어", "이야", "야", "중이야", "중", "왔어", "갈게"))


def is_direct_fact_statement(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized or "?" in normalized:
        return False
    if any(token in normalized for token in NON_STATE_REQUEST_PATTERNS):
        return False
    if any(token in normalized for token in SELF_STATE_MARKERS):
        return True
    return any(token in normalized for token in FUTURE_INTENT_PATTERNS)


def _trim_excerpt(text: str, limit: int = 120) -> Optional[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text[:limit] or None


def _extract_sentence_fragment(text: str, patterns: list[str]) -> Optional[str]:
    for raw in re.split(r"[\n!?。]+", text or ""):
        sentence = raw.strip(" .,!?\t")
        if sentence and contains_any(sentence, patterns):
            return sentence[:160]
    return _trim_excerpt(text, 160)


def _split_sentences(text: str) -> list[str]:
    return [
        sentence.strip(" .,!?\t")
        for sentence in re.split(r"[\n!?。]+", text or "")
        if sentence.strip(" .,!?\t")
    ]


def _clean_fact_value(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    value = re.sub(r"^(지금|방금|오늘|어제)\s+", "", value)
    value = re.sub(r"^[은는이가]\s*", "", value)
    value = re.sub(r"\s*쪽$", "", value)
    value = re.sub(r"\s*(이야|야|이네|네|였어|했어|왔어|가는 중이야|가는 중)$", "", value)
    return value.strip(" ,.")


def _detect_date_hint(text: str) -> Optional[str]:
    if "이번 주말" in text or "이번주말" in text:
        return "this_weekend"
    if "다음 주말" in text or "다음주말" in text:
        return "next_weekend"
    if "토요일" in text:
        return "saturday"
    if "일요일" in text:
        return "sunday"
    return None


def _extract_place_candidate(text: str) -> Optional[str]:
    composite_patterns = [
        r"([가-힣A-Za-z0-9]{2,12}\s*[가-힣A-Za-z0-9]{0,12}(?:카페거리|롯데월드몰|한강공원|공원|해변|바다|서점|카페|시장|백화점|몰|역|동|리조트|호텔))",
        r"((?:강릉|부산|제주|속초|여수|전주|성수|한강|잠실|홍대|해운대)\s*[가-힣A-Za-z0-9]{0,12})",
    ]
    for pattern in composite_patterns:
        match = re.search(pattern, text)
        if match:
            value = _clean_fact_value(match.group(1))
            if value and len(value) >= 2:
                return value
    patterns = [
        r"(강릉|부산|제주|속초|여수|전주|성수|한강|잠실|홍대|카페|공원|시골|부모님댁|본가)",
        r"([^,.!?]{2,24}?)(?:에|으로)\s*(?:가기로|갈거야|갈 거야|가는 중|다녀올)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = _clean_fact_value(match.group(1))
            if value and len(value) >= 2:
                return value
    return None


def _extract_activity_candidates(text: str) -> list[str]:
    activity_map = [
        ("산책", "walk"),
        ("브런치", "brunch"),
        ("베이커리", "bakery"),
        ("디저트", "dessert"),
        ("한강", "riverside"),
        ("해변", "beach"),
        ("바다", "beach"),
        ("등산", "hike"),
        ("영화", "movie"),
        ("극장", "movie"),
        ("드라마", "drama"),
        ("전시", "exhibition"),
        ("공연", "concert"),
        ("책 읽", "reading"),
        ("독서", "reading"),
        ("서점", "bookstore"),
        ("맛집", "dining_out"),
        ("드라이브", "drive"),
        ("수영", "swim"),
        ("러닝", "run"),
        ("달리기", "run"),
        ("자전거", "bike"),
        ("필라테스", "pilates"),
        ("헬스", "gym"),
        ("요가", "yoga"),
        ("장보기", "grocery"),
        ("쇼핑", "shopping"),
        ("여행", "travel"),
        ("데이트", "date"),
        ("카페", "cafe"),
        ("커피", "coffee"),
        ("빵", "bakery"),
        ("공원", "park"),
        ("점심", "meal"),
        ("저녁", "meal"),
        ("밥", "meal"),
        ("먹", "meal"),
        ("운동", "workout"),
        ("마트", "grocery"),
        ("정리", "reset"),
        ("쉬고", "rest"),
        ("쉴거", "rest"),
        ("쉴 거", "rest"),
    ]
    found = []
    for token, label in activity_map:
        if token in text and label not in found:
            found.append(label)
    return found


def _extract_companion_hint(text: str) -> Optional[str]:
    if "오빠" in text:
        return "user"
    if "부모님" in text:
        return "parents"
    if "친구" in text:
        return "friends"
    return None


def _extract_location_fact(text: str) -> Optional[str]:
    for sentence in _split_sentences(text):
        normalized = re.sub(r"\s+", " ", sentence)
        location_patterns = [
            r"(한강공원|롯데월드몰|카페거리|해운대 해변|부모님댁|본가|시골|강릉 카페거리|성수 카페거리)\s*(?:와있어|와 있어|왔어|도착했어|도착했|가는 중이야|가는 중)",
            r"(?:지금|방금|오늘|어제)\s+([^,.!?]{1,30}?)\s*(?:에|에서)\s*(?:있어|있는 중|와있어|와 있어|놀고 있어|머무는 중)",
            r"([^,.!?]{1,20}?)(?:에|에서)\s*(?:도착했어|도착했|와있어|와 있어)",
            r"((?:서울|부산|대구|인천|제주|강릉|속초|여수|전주|성수|잠실|홍대|해운대)(?:\s+[가-힣A-Za-z0-9]{1,12}){0,2})\s*(?:왔어|와서|도착했어|도착했|와있어|와 있어)",
            r"([^,.!?]{1,24}?)(?:가는 중이야|가는 중)\b",
        ]
        for pattern in location_patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            value = _clean_fact_value(match.group(1))
            if value and len(value) >= 2 and not any(token in value for token in ["오빠", "웅삐", "질문듣고", "잘거", "누어"]):
                return value
    return None


def _extract_weekend_plan_fact(text: str) -> Optional[str]:
    for sentence in _split_sentences(text):
        if not contains_any(sentence, WEEKEND_PLAN_PATTERNS):
            continue
        if contains_any(sentence, PLAN_COMMIT_PATTERNS):
            return sentence[:160]
        if re.search(r"(주말|토요일|일요일).{0,40}(할 거야|할거야|갈 거야|갈거야|보기로 했어|먹을 거야|먹을거야)", sentence):
            return sentence[:160]
    return None


def _extract_weekend_plan_attributes(text: str) -> dict:
    summary = _extract_weekend_plan_fact(text)
    if not summary:
        return {}
    return {
        "summary": summary,
        "date_hint": _detect_date_hint(summary),
        "place": _extract_place_candidate(summary),
        "activities": _extract_activity_candidates(summary),
        "companion_hint": _extract_companion_hint(summary),
    }


def _extract_recent_place_fact(text: str) -> Optional[str]:
    for sentence in _split_sentences(text):
        normalized = re.sub(r"\s+", " ", sentence)
        recent_patterns = [
            r"(?:어제|오늘|방금)\s+([^,.!?]{1,24}?)(?:에|에서)\s*(?:갔어|다녀왔어|들렀어|왔어)",
            r"(?:어제|오늘|방금)\s+([^,.!?]{1,24}?)(?:\s*)(?:갔다|다녀왔다|들렀다)",
            r"(?:어제|오늘|방금)\s+([^,.!?]{1,24}?)(?:\s*)(?:들렀어|갔어|다녀왔어)",
            r"(?:어제|오늘|방금)\s+([^,.!?]{1,24}?)(?:\s*)(?:들러서|가서|와서)",
        ]
        for pattern in recent_patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            value = _clean_fact_value(match.group(1))
            if value and len(value) >= 2:
                return value
    return None


def _new_state_entry(spec: dict, event: dict, text: str) -> dict:
    return {
        "key": spec["key"],
        "summary": spec["summary"],
        "status": "active",
        "started_at": event.get("timestamp"),
        "last_mentioned_at": event.get("timestamp"),
        "resolved_at": None,
        "source_excerpt": _trim_excerpt(text),
        "source_event_type": event.get("type"),
    }


def _mark_resolved(entry: dict, event: dict, reason: str) -> dict:
    resolved = dict(entry)
    resolved["status"] = "resolved"
    resolved["resolved_at"] = event.get("timestamp")
    resolved["resolution_reason"] = reason
    return resolved


def _upsert_fact(facts: dict, fact_key: str, value: str, event: dict, attributes: Optional[dict] = None) -> None:
    previous = facts.get(fact_key, {})
    facts[fact_key] = {
        "key": fact_key,
        "value": value,
        "status": "active",
        "first_seen_at": previous.get("first_seen_at") or event.get("timestamp"),
        "last_updated_at": event.get("timestamp"),
        "source_excerpt": _trim_excerpt(event_text(event), 160),
        "attributes": attributes or previous.get("attributes") or {},
    }


def build_counterpart_state_memory(events: Optional[list] = None) -> dict:
    events = events or load_message_events(limit_files=30)
    incoming_events = [event for event in events if event.get("direction") == "incoming"]
    active_states = {}
    resolved_states = []
    facts = {}

    for event in incoming_events:
        text = event_text(event)
        if not is_human_state_signal(text):
            continue

        for state_key, entry in list(active_states.items()):
            spec = STATE_SPEC_BY_KEY.get(state_key)
            if spec and contains_any(text, spec["end_patterns"]):
                resolved_states.append(_mark_resolved(entry, event, "explicit_or_implied_resolution"))
                active_states.pop(state_key, None)

        weekend_plan = _extract_weekend_plan_fact(text) if is_direct_fact_statement(text) else None
        if weekend_plan:
            _upsert_fact(
                facts,
                "weekend_plan",
                weekend_plan,
                event,
                attributes=_extract_weekend_plan_attributes(text),
            )

        location_fact = _extract_location_fact(text) if is_direct_state_statement(text) else None
        if location_fact:
            _upsert_fact(
                facts,
                "current_location",
                location_fact,
                event,
                attributes={
                    "place": location_fact,
                    "date_hint": _detect_date_hint(text),
                    "companion_hint": _extract_companion_hint(text),
                },
            )

        if is_direct_fact_statement(text) and contains_any(text, ["어제", "오늘", "방금"]) and contains_any(text, ["갔", "다녀왔", "왔", "들렀", "들러"]):
            recent_place = _extract_recent_place_fact(text)
            if recent_place:
                _upsert_fact(
                    facts,
                    "recent_place",
                    recent_place,
                    event,
                    attributes={
                        "place": recent_place,
                        "date_hint": _detect_date_hint(text) or ("today" if "오늘" in text else "yesterday" if "어제" in text else "recent"),
                        "activities": _extract_activity_candidates(text),
                        "companion_hint": _extract_companion_hint(text),
                    },
                )

        for spec in STATE_SPECS:
            if not contains_any(text, spec["start_patterns"]) or not is_direct_state_statement(text):
                continue
            if contains_any(text, spec["end_patterns"]):
                continue
            existing = active_states.get(spec["key"])
            if existing:
                existing["last_mentioned_at"] = event.get("timestamp")
                existing["source_excerpt"] = _trim_excerpt(text)
            else:
                active_states[spec["key"]] = _new_state_entry(spec, event, text)

    active_state_list = sorted(
        active_states.values(),
        key=lambda item: (-STATE_SPEC_BY_KEY.get(item["key"], {}).get("priority", 0), item.get("started_at") or ""),
    )
    active_fact_list = sorted(facts.values(), key=lambda item: item.get("last_updated_at") or "")
    latest_incoming = incoming_events[-1] if incoming_events else None

    return {
        "schema_version": 1,
        "managed_by": "counterpart_state_memory",
        "last_refreshed_at": now_local().isoformat(timespec="seconds"),
        "source_window": {
            "event_count": len(incoming_events),
            "last_incoming_at": latest_incoming.get("timestamp") if latest_incoming else None,
        },
        "active_states": active_state_list,
        "resolved_states": resolved_states[-20:],
        "sticky_facts": active_fact_list,
        "summary": {
            "active_state_keys": [item.get("key") for item in active_state_list],
            "active_fact_keys": [item.get("key") for item in active_fact_list],
        },
        "notes": "상대가 직접 말한 상태는 해제 신호가 들어오기 전까지 유지하고, 주말 약속/위치 같은 사실도 sticky fact로 보존한다.",
    }


def infer_counterpart_state(events: Optional[list] = None, memory: Optional[dict] = None) -> dict:
    events = events or load_message_events()
    memory = memory or build_counterpart_state_memory(events)
    incoming_events = [event for event in events if event.get("direction") == "incoming"]
    outgoing_events = [event for event in events if event.get("direction") == "outgoing"]
    if not incoming_events:
        return {
            "state_key": "unknown",
            "availability": "unknown",
            "followup_policy": "default",
            "tone_hint": "neutral",
            "confidence": 0.0,
            "reason": "최근 incoming 메시지가 없어 상대 상태를 추론하지 못함",
            "source_timestamp": None,
            "source_excerpt": None,
            "applies_until": None,
            "should_suppress_waiting_reply": False,
            "active_state_keys": [],
            "active_state_summaries": [],
            "sticky_fact_summaries": [],
        }

    last_incoming = incoming_events[-1]
    last_incoming_text = event_text(last_incoming)
    last_outgoing = outgoing_events[-1] if outgoing_events else None
    last_outgoing_text = event_text(last_outgoing)
    active_states = memory.get("active_states", [])
    sticky_facts = memory.get("sticky_facts", [])

    if active_states:
        lead_state = active_states[0]
        spec = STATE_SPEC_BY_KEY.get(lead_state.get("key"), {})
        reason = "%s 상태가 아직 해제되지 않음" % (lead_state.get("summary") or lead_state.get("key"))
        if lead_state.get("key") == "sleeping_or_falling_asleep":
            last_incoming_dt = parse_event_timestamp(last_incoming.get("timestamp"))
            last_outgoing_dt = parse_event_timestamp(last_outgoing.get("timestamp")) if last_outgoing else None
            if last_outgoing_dt and last_incoming_dt and last_outgoing_dt >= last_incoming_dt and contains_any(last_outgoing_text, GOODNIGHT_PATTERNS):
                reason = "상대가 잠드는 흐름을 말했고 잘 자 인사로 대화가 마무리된 뒤 아직 기상 신호가 없음"
        return {
            "state_key": lead_state.get("key"),
            "availability": spec.get("availability", "limited"),
            "followup_policy": spec.get("followup_policy", "soft_only"),
            "tone_hint": spec.get("tone_hint", "neutral"),
            "confidence": spec.get("confidence", 0.8),
            "reason": reason,
            "source_timestamp": lead_state.get("last_mentioned_at") or last_incoming.get("timestamp"),
            "source_excerpt": lead_state.get("source_excerpt") or _trim_excerpt(last_incoming_text),
            "applies_until": None,
            "should_suppress_waiting_reply": spec.get("followup_policy") == "suppress",
            "active_state_keys": [item.get("key") for item in active_states],
            "active_state_summaries": [item.get("summary") for item in active_states],
            "sticky_fact_summaries": [item.get("value") for item in sticky_facts if item.get("value")],
        }

    return {
        "state_key": "available",
        "availability": "open",
        "followup_policy": "default",
        "tone_hint": "neutral",
        "confidence": 0.35,
        "reason": "현재 유지 중인 상대 상태는 없고 최근 메시지 기준으로 기본 응답 가능 상태",
        "source_timestamp": last_incoming.get("timestamp"),
        "source_excerpt": _trim_excerpt(last_incoming_text),
        "applies_until": None,
        "should_suppress_waiting_reply": False,
        "active_state_keys": [],
        "active_state_summaries": [],
        "sticky_fact_summaries": [item.get("value") for item in sticky_facts if item.get("value")],
    }


def compute_conversation_guard() -> dict:
    proactive = load_json(PROACTIVE_PATH, {})
    guards = proactive.get("guards", {})
    events = load_message_events()
    last_incoming = None
    last_outgoing = None
    recent_pairs = []
    for event in events:
        if event.get("direction") == "incoming":
            last_incoming = event
        elif event.get("direction") == "outgoing" and event.get("type") in ANY_OUTGOING_TYPES:
            last_outgoing = event
        if event.get("direction") in {"incoming", "outgoing"}:
            recent_pairs.append(event)
    now_dt = now_local()
    counterpart_memory = build_counterpart_state_memory(events)
    counterpart_state = infer_counterpart_state(events, counterpart_memory)
    window_minutes = int(guards.get("conversation_active_window_minutes", 20))
    cooldown_minutes = int(guards.get("outgoing_cooldown_minutes", 10))
    late_probe_minutes = int(guards.get("late_reply_probe_minutes", 60))
    follow_up_gap_minutes = float(guards.get("waiting_reply_followup_minutes", 3))
    reply_burst_grace_minutes = float(guards.get("reply_burst_grace_minutes", follow_up_gap_minutes))
    conversation_active = False
    last_incoming_dt = parse_event_timestamp(last_incoming.get("timestamp")) if last_incoming else None
    last_outgoing_dt = parse_event_timestamp(last_outgoing.get("timestamp")) if last_outgoing else None
    if last_incoming_dt and last_outgoing_dt:
        conversation_active = (
            (now_dt - last_incoming_dt).total_seconds() <= window_minutes * 60
            and (now_dt - last_outgoing_dt).total_seconds() <= window_minutes * 60
            and abs((last_outgoing_dt - last_incoming_dt).total_seconds()) <= window_minutes * 60
        )
    waiting_reply = False
    if last_outgoing_dt and (not last_incoming_dt or last_outgoing_dt > last_incoming_dt):
        waiting_reply = True
    outgoing_cooldown = False
    if last_outgoing_dt:
        outgoing_cooldown = (now_dt - last_outgoing_dt).total_seconds() <= cooldown_minutes * 60
    late_reply_ok = False
    if last_incoming_dt:
        late_reply_ok = (now_dt - last_incoming_dt).total_seconds() >= late_probe_minutes * 60
    unanswered_outgoing_count = 0
    if waiting_reply:
        last_incoming_dt = parse_event_timestamp(last_incoming.get("timestamp")) if last_incoming else None
        last_followup_cluster_dt = None
        for event in events:
            if event.get("direction") != "outgoing" or event.get("type") not in AUTOMATED_OUTGOING_TYPES:
                continue
            event_dt = parse_event_timestamp(event.get("timestamp"))
            if not event_dt:
                continue
            if last_incoming_dt and event_dt <= last_incoming_dt:
                continue
            if last_incoming_dt:
                minutes_from_incoming = (event_dt - last_incoming_dt).total_seconds() / 60.0
                if minutes_from_incoming < reply_burst_grace_minutes:
                    continue
            if last_followup_cluster_dt is None:
                unanswered_outgoing_count += 1
                last_followup_cluster_dt = event_dt
                continue
            minutes_from_last_cluster = (event_dt - last_followup_cluster_dt).total_seconds() / 60.0
            if minutes_from_last_cluster >= follow_up_gap_minutes:
                unanswered_outgoing_count += 1
                last_followup_cluster_dt = event_dt
    minutes_since_last_outgoing = None
    if last_outgoing_dt:
        minutes_since_last_outgoing = (now_dt - last_outgoing_dt).total_seconds() / 60.0
    return {
        "conversation_active": conversation_active,
        "waiting_reply": waiting_reply,
        "outgoing_cooldown": outgoing_cooldown,
        "late_reply_ok": late_reply_ok,
        "last_incoming": last_incoming,
        "last_outgoing": last_outgoing,
        "unanswered_outgoing_count": unanswered_outgoing_count,
        "minutes_since_last_outgoing": minutes_since_last_outgoing,
        "counterpart_state": counterpart_state,
        "counterpart_memory": counterpart_memory,
    }
