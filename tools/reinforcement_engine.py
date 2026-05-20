#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path("/Users/kein/Desktop/woong-bb")
MESSAGES = ROOT / "messages"
STATE_PATH = ROOT / "state" / "user_preference_reinforcement.json"

POSITIVE_KEYWORDS = {
    "좋아": 2,
    "행복": 3,
    "기운": 2,
    "고마워": 2,
    "따뜻": 2,
    "귀여": 2,
    "이뻐": 2,
    "예뻐": 2,
    "보고싶": 2,
    "보고 싶": 2,
    "몽글": 2,
    "좋겠": 1,
    "잘 왔": 1,
    "좋다": 2,
}

NEGATIVE_KEYWORDS = {
    "별로": -2,
    "부담": -2,
    "이상": -2,
    "중복": -2,
    "꼬여": -2,
    "안좋": -2,
    "싫": -3,
    "그만": -3,
    "말고": -1,
    "아냐": -1,
}

TOPIC_RULES = {
    "appearance_compliment": ["이뻐", "예뻐", "귀여", "천사", "사진", "프사"],
    "photo_request": ["사진", "프사", "보고싶다", "보고 싶다", "사진보고싶"],
    "daily_checkin": ["뭐해", "출근", "준비", "일어나", "점심", "퇴근", "출근길"],
    "comfort_support": ["따뜻", "위로", "고마워", "기운", "힘이", "포근"],
    "affection_romance": ["행복", "안아", "보고싶", "몽글", "좋아해", "생각"],
    "food_cafe": ["밥", "커피", "카페", "디저트", "브런치", "음료"],
    "exercise_health": ["운동", "수영", "러닝", "자전거", "헬스"],
    "workday_empathy": ["지쳤", "힘들", "출근", "퇴근", "피곤", "회복"],
    "playful_teasing": ["ㅋㅋ", "반칙", "안뇽", "뭐야", "헤헤"],
    "sleep_goodnight": ["잘자", "일어나", "잠", "누워", "자려"],
    "media_watch_talk": ["유튜브", "쇼츠", "릴스", "ott", "넷플릭스", "티빙", "보고 있었"],
    "setting_feedback": ["설정", "세팅", "구성", "추가", "만들자", "규칙"],
}

ACTION_RULES = {
    "send_photo": ["사진", "프사", "보내"],
    "send_text_after_photo": ["메시지", "텍스트"],
    "caption_inside_photo_message": ["캡션", "텍스트 미포함", "중복"],
    "separate_text_message": ["텍스트만", "별도로", "따로", "분리"],
    "warm_comfort_reply": ["따뜻", "고마워", "기운", "위로"],
    "cute_affection_reply": ["귀여", "몽글", "행복", "포근"],
    "daily_context_reply": ["출근", "준비", "점심", "퇴근", "뭐해"],
    "proactive_checkin": ["선톡", "먼저", "인사"],
    "appearance_description": ["어떻게 입고", "상상", "누워", "모습"],
    "preference_learning": ["강화", "상벌점", "알고리즘", "점수", "누적", "패널티"],
}

STYLE_RULES = {
    "half_banmal_affectionate": ["오빠", "ㅎㅎ", "ㅋㅋ"],
    "gentle_comfort": ["따뜻", "고마워", "위로", "기운", "포근"],
    "playful_light": ["ㅋㅋ", "반칙", "안뇽", "헤헤"],
    "concise_setting_mode": ["설정", "세팅"],
    "image_without_caption": ["텍스트 미포함", "캡션 없이", "사진은 텍스트없이"],
    "text_separate_from_image": ["텍스트만", "별도로", "따로", "분리"],
    "initiative_with_context": ["먼저", "상황", "시간대", "자연스럽게"],
}

CONFIG_HINTS = [
    "설정",
    "세팅",
    "구성",
    "파일",
    "프로세스",
    "타이머",
    "worker",
    "guard",
    "json",
    "규칙",
    "룰",
    "상태",
    "엔진",
    "자동화",
    "시스템",
]

CONFIG_TOPIC_WHITELIST = {"setting_feedback"}
CONFIG_ACTION_WHITELIST = {
    "preference_learning",
    "send_text_after_photo",
    "caption_inside_photo_message",
    "separate_text_message",
    "proactive_checkin",
}
CONFIG_STYLE_WHITELIST = {
    "concise_setting_mode",
    "image_without_caption",
    "text_separate_from_image",
    "initiative_with_context",
}

CORRECTION_PATTERNS = {
    "image_without_caption": {
        "image_without_caption": 4,
        "action:caption_inside_photo_message": -4,
        "action:separate_text_message": 2,
    },
    "text_separate_from_image": {
        "text_separate_from_image": 3,
        "action:send_text_after_photo": 2,
        "action:caption_inside_photo_message": -3,
    },
    "preference_learning": {
        "action:preference_learning": 4,
    },
}


def load_state() -> dict:
    if not STATE_PATH.exists():
        return default_state()
    raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if raw.get("schema_version") == 2:
        return raw
    return migrate_state(raw)


def default_state() -> dict:
    return {
        "schema_version": 2,
        "managed_by": "reinforcement_engine",
        "last_run_at": None,
        "last_processed": {"file": None, "line": 0, "timestamp": None},
        "processed_offsets": {},
        "message_stats": {
            "incoming_text_processed": 0,
            "positive_messages": 0,
            "negative_messages": 0,
            "neutral_messages": 0,
        },
        "topic_scores": {},
        "action_scores": {},
        "style_scores": {},
        "bias_summary": {
            "prefer_topics": [],
            "prefer_actions": [],
            "prefer_styles": [],
            "avoid_actions": [],
            "avoid_styles": [],
        },
        "evidence_log": [],
        "top_preferences": {"topics": [], "actions": [], "styles": []},
        "notes": "사용자 반응을 주제/행동/스타일별 점수와 빈도로 누적한다",
    }


def migrate_state(old: dict) -> dict:
    state = default_state()
    state["last_processed"] = old.get("last_processed", state["last_processed"])
    for bucket_name in ("topic_scores", "action_scores", "style_scores"):
        old_bucket = old.get(bucket_name, {})
        for key, score in old_bucket.items():
            state[bucket_name][key] = new_entry(score=int(score))
    state["evidence_log"] = old.get("evidence_log", [])[-120:]
    state["top_preferences"] = old.get("top_preferences", state["top_preferences"])
    return state


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sorted_message_files() -> List[Path]:
    return sorted(MESSAGES.glob("*.jsonl"))


def sentiment_delta(text: str) -> int:
    score = 0
    for kw, val in POSITIVE_KEYWORDS.items():
        if kw in text:
            score += val
    for kw, val in NEGATIVE_KEYWORDS.items():
        if kw in text:
            score += val
    return score


def matching_keys(text: str, rules: dict) -> List[str]:
    matched = []
    for key, words in rules.items():
        if any(word in text for word in words):
            matched.append(key)
    return matched


def new_entry(score: int = 0) -> dict:
    return {
        "score": score,
        "positive_hits": 0,
        "negative_hits": 0,
        "neutral_hits": 0,
        "total_hits": 0,
        "first_seen_at": None,
        "last_seen_at": None,
        "last_delta": 0,
        "last_reason": None,
        "examples": [],
    }


def update_bucket(bucket: Dict[str, dict], key: str, delta: int, timestamp: str, reason: str, text: str) -> None:
    entry = bucket.get(key) or new_entry()
    if entry["first_seen_at"] is None:
        entry["first_seen_at"] = timestamp
    entry["last_seen_at"] = timestamp
    entry["score"] = int(entry.get("score", 0)) + delta
    entry["total_hits"] = int(entry.get("total_hits", 0)) + 1
    if delta > 0:
        entry["positive_hits"] = int(entry.get("positive_hits", 0)) + 1
    elif delta < 0:
        entry["negative_hits"] = int(entry.get("negative_hits", 0)) + 1
    else:
        entry["neutral_hits"] = int(entry.get("neutral_hits", 0)) + 1
    entry["last_delta"] = delta
    entry["last_reason"] = reason
    examples = list(entry.get("examples", []))
    examples.append({"timestamp": timestamp, "delta": delta, "text": text[:120]})
    entry["examples"] = examples[-5:]
    bucket[key] = entry


def refresh_top_preferences(state: dict) -> None:
    for src, target in [
        ("topic_scores", "topics"),
        ("action_scores", "actions"),
        ("style_scores", "styles"),
    ]:
        items = sorted(
            state[src].items(),
            key=lambda kv: (kv[1].get("score", 0), kv[1].get("positive_hits", 0), -kv[1].get("negative_hits", 0)),
            reverse=True,
        )
        state["top_preferences"][target] = [
            {
                "key": key,
                "score": value.get("score", 0),
                "positive_hits": value.get("positive_hits", 0),
                "negative_hits": value.get("negative_hits", 0),
            }
            for key, value in items[:7]
        ]


def refresh_bias_summary(state: dict) -> None:
    def summarize(bucket_name: str, score_min: int) -> List[dict]:
        items = []
        for key, value in state[bucket_name].items():
            score = int(value.get("score", 0))
            if score >= score_min:
                items.append({"key": key, "score": score})
        return sorted(items, key=lambda item: item["score"], reverse=True)[:5]

    def avoid(bucket_name: str, score_max: int) -> List[dict]:
        items = []
        for key, value in state[bucket_name].items():
            score = int(value.get("score", 0))
            if score <= score_max:
                items.append({"key": key, "score": score})
        return sorted(items, key=lambda item: item["score"])[:5]

    state["bias_summary"] = {
        "prefer_topics": summarize("topic_scores", 4),
        "prefer_actions": summarize("action_scores", 4),
        "prefer_styles": summarize("style_scores", 4),
        "avoid_actions": avoid("action_scores", -2),
        "avoid_styles": avoid("style_scores", -2),
    }


def classify_message_stats(state: dict, delta: int) -> None:
    stats = state["message_stats"]
    stats["incoming_text_processed"] = int(stats.get("incoming_text_processed", 0)) + 1
    if delta > 0:
        stats["positive_messages"] = int(stats.get("positive_messages", 0)) + 1
    elif delta < 0:
        stats["negative_messages"] = int(stats.get("negative_messages", 0)) + 1
    else:
        stats["neutral_messages"] = int(stats.get("neutral_messages", 0)) + 1


def context_action_bonus(previous_event: dict, delta: int) -> List[Tuple[str, int, str]]:
    bonuses: List[Tuple[str, int, str]] = []
    if not previous_event or previous_event.get("direction") != "outgoing" or delta <= 0:
        return bonuses
    event_type = previous_event.get("type")
    if event_type == "image":
        bonuses.append(("action", "send_photo", 2, "previous_outgoing_image_positive_feedback"))
        caption = previous_event.get("caption") or ""
        if not caption:
            bonuses.append(("style", "image_without_caption", 2, "captionless_image_positive_feedback"))
    elif event_type == "text":
        text = previous_event.get("content", "")
        if any(word in text for word in ["따뜻", "포근", "안아", "위로", "기운"]):
            bonuses.append(("action", "warm_comfort_reply", 2, "comfort_text_positive_feedback"))
            bonuses.append(("style", "gentle_comfort", 1, "comfort_text_positive_feedback"))
        if any(word in text for word in ["ㅋㅋ", "헤헤", "안뇽"]):
            bonuses.append(("style", "playful_light", 1, "playful_text_positive_feedback"))
    return bonuses


def parse_corrections(text: str) -> List[Tuple[str, str, int, str]]:
    changes: List[Tuple[str, str, int, str]] = []
    if any(word in text for word in STYLE_RULES["image_without_caption"]):
        for target, delta in CORRECTION_PATTERNS["image_without_caption"].items():
            bucket_name, key = split_target(target, default_bucket="style")
            changes.append((bucket_name, key, delta, "explicit_delivery_format_correction"))
    if any(word in text for word in STYLE_RULES["text_separate_from_image"]):
        for target, delta in CORRECTION_PATTERNS["text_separate_from_image"].items():
            bucket_name, key = split_target(target, default_bucket="style")
            changes.append((bucket_name, key, delta, "explicit_delivery_format_correction"))
    if any(word in text for word in ACTION_RULES["preference_learning"]):
        for target, delta in CORRECTION_PATTERNS["preference_learning"].items():
            bucket_name, key = split_target(target, default_bucket="action")
            changes.append((bucket_name, key, delta, "explicit_preference_learning_request"))
    return changes


def split_target(raw_target: str, default_bucket: str) -> Tuple[str, str]:
    if ":" not in raw_target:
        return default_bucket, raw_target
    bucket_name, key = raw_target.split(":", 1)
    return bucket_name, key


def is_config_message(text: str) -> bool:
    return sum(1 for word in CONFIG_HINTS if word in text) >= 2


def process_event(state: dict, event: dict, previous_event: dict) -> None:
    text = event.get("content", "")
    timestamp = event.get("timestamp")
    base_delta = sentiment_delta(text)
    if base_delta == 0 and any(word in text for word in ["좋겠", "유지", "그렇게", "그걸로", "하면 돼"]):
        base_delta = 1

    topics = matching_keys(text, TOPIC_RULES)
    actions = matching_keys(text, ACTION_RULES)
    styles = matching_keys(text, STYLE_RULES)
    if is_config_message(text):
        topics = [topic for topic in topics if topic in CONFIG_TOPIC_WHITELIST]
        actions = [action for action in actions if action in CONFIG_ACTION_WHITELIST]
        styles = [style for style in styles if style in CONFIG_STYLE_WHITELIST]
    corrections = parse_corrections(text)
    bonuses = context_action_bonus(previous_event, max(base_delta, 1))

    classify_message_stats(state, base_delta)

    for topic in topics:
        update_bucket(state["topic_scores"], topic, base_delta or 1, timestamp, "message_topic_match", text)
    for action in actions:
        update_bucket(state["action_scores"], action, base_delta or 1, timestamp, "message_action_match", text)
    for style in styles:
        update_bucket(state["style_scores"], style, base_delta or 1, timestamp, "message_style_match", text)

    for bucket_name, key, delta, reason in corrections:
        bucket = state["style_scores"] if bucket_name == "style" else state["action_scores"]
        update_bucket(bucket, key, delta, timestamp, reason, text)

    for bucket_name, key, delta, reason in bonuses:
        bucket = state["style_scores"] if bucket_name == "style" else state["action_scores"]
        update_bucket(bucket, key, delta, timestamp, reason, text)

    state["evidence_log"].append(
        {
            "timestamp": timestamp,
            "text": text[:200],
            "base_delta": base_delta,
            "topics": topics,
            "actions": actions,
            "styles": styles,
            "corrections": [{"bucket": b, "key": k, "delta": d, "reason": r} for b, k, d, r in corrections],
            "context_bonuses": [{"bucket": b, "key": k, "delta": d, "reason": r} for b, k, d, r in bonuses],
        }
    )
    state["evidence_log"] = state["evidence_log"][-180:]


def run() -> None:
    state = load_state()
    processed_offsets = dict(state.get("processed_offsets", {}))

    previous_event = None
    last_processed_file = None
    last_processed_line = 0
    last_processed_timestamp = None

    for file_path in sorted_message_files():
        file_key = str(file_path)
        start_line = int(processed_offsets.get(file_key, 0))
        line_no = 0
        for raw in file_path.read_text(encoding="utf-8").splitlines():
            line_no += 1
            try:
                event = json.loads(raw)
            except Exception:
                continue
            if line_no <= start_line:
                previous_event = event
                continue
            if event.get("direction") == "incoming" and event.get("type") == "text":
                process_event(state, event, previous_event)
                last_processed_file = file_key
                last_processed_line = line_no
                last_processed_timestamp = event.get("timestamp")
            previous_event = event
        processed_offsets[file_key] = line_no

    state["processed_offsets"] = processed_offsets
    state["last_run_at"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
    if last_processed_file:
        state["last_processed"] = {
            "file": last_processed_file,
            "line": last_processed_line,
            "timestamp": last_processed_timestamp,
        }
    refresh_top_preferences(state)
    refresh_bias_summary(state)
    save_state(state)
    print(
        json.dumps(
            {
                "ok": True,
                "last_processed": state["last_processed"],
                "message_stats": state["message_stats"],
                "bias_summary": state["bias_summary"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    run()
