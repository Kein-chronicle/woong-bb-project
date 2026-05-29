from __future__ import annotations

import re
from typing import Optional


EVENT_TRIGGER_RULES = [
    {"event_key": "after_work", "label": "일 끝남", "patterns": [r"일 끝나", r"일 끝나면", r"퇴근하", r"퇴근하면"]},
    {"event_key": "arrive_home", "label": "집 도착", "patterns": [r"집에 도착", r"집 도착", r"집 들어가", r"귀가하"]},
    {"event_key": "arrive_work", "label": "직장 도착", "patterns": [r"작업 시작", r"컴퓨터 켰어", r"오늘 시작"]},
    {"event_key": "arrive_somewhere", "label": "어디 도착", "patterns": [r"도착하", r"도착하면", r"막 도착"]},
    {"event_key": "changed_clothes", "label": "옷 갈아입음", "patterns": [r"옷 갈아입", r"갈아입으면", r"근무복 입", r"잠옷 갈아입"]},
    {"event_key": "lunch_time", "label": "점심시간", "patterns": [r"점심시간", r"점심때", r"점심 먹", r"점심 전후", r"밥 먹으면", r"밥 먹게 되면", r"식사하면"]},
    {"event_key": "wake_up", "label": "기상", "patterns": [r"일어나면", r"일어나고", r"깼을 때", r"아침에 깨면", r"아침에 일어나면"]},
    {"event_key": "lying_in_bed", "label": "침대에 누움", "patterns": [r"침대에 누우", r"누우면", r"누웠을 때", r"씻고 누우", r"침대에 눕"]},
]

PROMISE_CREATE_HINTS = ["보내줘", "보내주라", "보내주면", "보내줄게", "톡해줘", "카톡해줘", "말해줘", "전해줘"]
PROMISE_CANCEL_HINTS = ["취소", "해주지말자", "해주지 말자", "보내지말자", "보내지 말자", "하지말자", "하지 말자", "없던걸로", "없던 걸로"]


def has_any_phrase(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def match_event_trigger_rule(text: str) -> Optional[dict]:
    for rule in EVENT_TRIGGER_RULES:
        if any(re.search(pattern, text) for pattern in rule.get("patterns", [])):
            return rule
    return None


def extract_promise_payload(text: str) -> str:
    if "<<" in text:
        before, after = text.split("<<", 1)
        candidate = after.strip() or before.strip()
    else:
        candidate = text
    candidate = re.sub(r"(보내줘|보내주라|보내주면|보내줄게|톡해줘|카톡해줘|말해줘|전해줘)[^.?!]*$", "", candidate).strip()
    candidate = re.sub(r"^(그때|그럼|그러면|언제|이따|나중에)\s+", "", candidate).strip()
    return candidate.strip(" \"'“”‘’")


def parse_event_trigger_command(text: str) -> Optional[dict]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return None
    if has_any_phrase(normalized, PROMISE_CANCEL_HINTS):
        rule = match_event_trigger_rule(normalized)
        return {
            "action": "cancel",
            "event_key": rule.get("event_key") if rule else None,
            "label": rule.get("label") if rule else None,
            "source_text": normalized,
        }
    if not has_any_phrase(normalized, PROMISE_CREATE_HINTS):
        return None
    rule = match_event_trigger_rule(normalized)
    if not rule:
        return None
    payload = extract_promise_payload(normalized)
    if not payload:
        return None
    return {
        "action": "create",
        "event_key": rule["event_key"],
        "label": rule["label"],
        "message": payload,
        "source_text": normalized,
        "delivery_kind": "image" if "사진" in normalized else "text",
    }


def parse_outgoing_event_promise(text: str) -> Optional[dict]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized or "보내줄게" not in normalized:
        return None
    rule = match_event_trigger_rule(normalized)
    if not rule:
        return None
    message = normalized
    if "대신" in normalized:
        message = normalized.rsplit("대신", 1)[-1].strip()
    message = extract_promise_payload(message)
    message = re.sub(r"^(점심|밥|식사)\s*(먹으면|먹게 되면|먹을 때)\s*", "", message).strip()
    return {
        "action": "create",
        "event_key": rule["event_key"],
        "label": rule["label"],
        "message": message,
        "source_text": normalized,
        "delivery_kind": "image" if "사진" in normalized else "text",
        "source_direction": "outgoing",
    }


def sanitize_promise_message(message: str, source_text: str, delivery_kind: str) -> str:
    normalized = re.sub(r"\s+", " ", (message or "").strip())
    if delivery_kind != "image":
        return normalized
    if normalized and len(normalized) <= 24 and not re.search(r"[.?!\n]", normalized):
        return normalized
    reparsed = parse_outgoing_event_promise(source_text) if source_text else None
    reparsed_message = re.sub(r"\s+", " ", (reparsed or {}).get("message", "")).strip()
    if reparsed_message and len(reparsed_message) <= 24 and not re.search(r"[.?!\n]", reparsed_message):
        return reparsed_message
    if "사진" in normalized:
        photo_tail = normalized.rsplit("사진", 1)[0].strip()
        if photo_tail:
            compact = ("%s 사진" % photo_tail.split()[-1]).strip()
            if len(compact) <= 24:
                return compact
        return "사진"
    return normalized[:24].strip() or "사진"


def derive_event_keys_for_transition(previous_activity: Optional[str], current_activity: Optional[str]) -> list[str]:
    prev = previous_activity or ""
    curr = current_activity or ""
    event_keys = []
    if curr == "waking_up":
        event_keys.append("wake_up")
    if curr == "lunch_break":
        event_keys.append("lunch_time")
    if prev in {"morning_work", "afternoon_work"} and curr == "evening_free":
        event_keys.append("after_work")
    if curr == "morning_work" and prev in {"getting_ready", "morning_prep"}:
        event_keys.extend(["arrive_work", "changed_clothes"])
    if curr == "dinner_or_cooking" and prev == "evening_free":
        event_keys.extend(["arrive_home", "arrive_somewhere"])
    if curr == "evening_free" and prev in {"evening_free", "dinner_or_cooking", "weekend_brunch_or_coffee"}:
        event_keys.append("arrive_somewhere")
    if curr == "night_wind_down" and prev in {"dinner_or_cooking", "evening_free", "weekend_evening"}:
        event_keys.extend(["lying_in_bed", "changed_clothes"])
    return list(dict.fromkeys(event_keys))


def normalize_fact_expression(text: str) -> str:
    normalized = (text or "").strip()
    replacements = [
        (r"(막 |방금 |이제 )?도착한 (느낌|기분)이야", lambda m: "%s도착했어" % (m.group(1) or "")),
        (r"(막 |방금 |이제 )?일어난 (느낌|기분)이야", lambda m: "%s일어났어" % (m.group(1) or "")),
        (r"(막 |방금 |이제 )?누운 (느낌|기분)이야", lambda m: "%s누웠어" % (m.group(1) or "")),
        (r"(막 |방금 |이제 )?옷 갈아입은 (느낌|기분)이야", lambda m: "%s옷 갈아입었어" % (m.group(1) or "")),
        (r"점심시간인 (느낌|기분)이야", "점심시간이야"),
        (r"일 끝난 (느낌|기분)이야", "일 끝났어"),
    ]
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)
    normalized = re.sub(r"(도착했어|일어났어|누웠어|옷 갈아입었어|점심시간이야|일 끝났어)\s+같아", r"\1", normalized)
    return normalized.strip()


def factual_status_for_activity(activity: Optional[str]) -> Optional[str]:
    mapping = {
        "waking_up": "방금 일어났어",
        "getting_ready": "출근 준비 중이야",
        "morning_prep": "작업 준비 중이야",
        "morning_work": "오전 작업 시작했어",
        "lunch_break": "점심시간이야",
        "afternoon_work": "오후 작업 중이야",
        "evening_free": "오늘 작업 마무리했어",
        "dinner_or_cooking": "집 도착해서 저녁 챙기고 있어",
        "evening_free": "저녁 여유 시간이야",
        "night_wind_down": "이제 씻고 누웠어",
        "sleep_window": "자고 있어야 하는 시간이야",
    }
    return mapping.get(activity or "")
