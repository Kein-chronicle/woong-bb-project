#!/usr/bin/env python3
import glob
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from project_paths import ROOT
RAW_DIR = ROOT / "couple_script_sample" / "raw"
MESSAGES_DIR = ROOT / "messages"
MANIFEST_PATH = ROOT / "couple_script_sample" / "manifest.json"
STATE_PATH = ROOT / "state" / "conversation_pattern_catalog.json"
PROFILE_PATH = ROOT / "profile" / "woongbbi_conversation_pattern_catalog_ko.md"
QUALITY_REPORT_PATH = ROOT / "couple_script_sample" / "source_quality_report.json"
APPROVED_PATTERNS_PATH = ROOT / "state" / "approved_conversation_patterns.json"
REJECTED_PATTERNS_PATH = ROOT / "state" / "rejected_conversation_patterns.json"

PATTERN_RULES = [
    ("current_state_check", ["지금 뭐", "뭐하고", "뭐 해", "어디쯤", "어디야", "가는 중", "도착했", "뭐 하고 있어"]),
    ("meal_routine", ["밥", "점심", "저녁", "먹었어", "먹을거야", "커피", "챙겨 먹"]),
    ("emotion_check", ["힘들", "지쳤", "피곤", "괜찮아", "기분 어때", "오늘 어땠"]),
    ("photo_request", ["사진", "보여주", "찍어줘", "지금 모습"]),
    ("affection_imagination", ["같이", "옆에", "안고", "안기", "보고 싶", "보고싶", "같이 있었으면"]),
    ("self_update", ["나 지금", "방금", "나는 지금", "나 이제", "지금은 나는"]),
    ("thought_of_you", ["오빠 생각", "문득", "갑자기", "궁금해서 먼저", "생각하고 있었어"]),
    ("care_offer", ["물 마셔", "천천히", "쉬어", "무리하지", "챙겨", "조심히 가"]),
    ("playful_tease", ["모야", "ㅋㅋ", "반칙", "왜케", "헤헤", "ㅎㅎ", "또 왔어"]),
    ("scene_share", ["조용", "공기", "날씨", "바람", "협탁", "머그컵", "밤", "퇴근길", "창밖"]),
]

MESSAGE_EXCLUDE_PATTERNS = [
    r"^마스터[, ]",
    r"^/설정온$",
    r"^/세팅온$",
    r"^/웅삐온$",
    r"^/goal$",
    r"/Users/",
    r"\.jsonl",
    r"\.json",
    r"\.md",
    r"세팅모드",
    r"설정파일",
    r"폴더",
    r"파일",
    r"캘린더",
    r"이미지 생성",
    r"프로세스",
    r"타이머",
    r"스킬",
    r"루트",
    r"시간대별",
    r"생활 패턴",
    r"설정",
    r"대답할때 참조",
    r"채팅은 할 수",
    r"트리거",
    r"기능 구성",
    r"먼저 그런 톡",
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def classify(text: str) -> list:
    matched = []
    for key, needles in PATTERN_RULES:
        if any(needle in text for needle in needles):
            matched.append(key)
    return matched


def dedupe_keep_order(values: list) -> list:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def percentile(values: list, ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * ratio)
    return ordered[max(0, min(index, len(ordered) - 1))]


def text_length_profile(texts: list) -> dict:
    if not texts:
        return {
            "sample_count": 0,
            "char_min": 0,
            "char_p50": 0,
            "char_p75": 0,
            "char_p90": 0,
            "sentence_p50": 0,
            "question_ratio": 0.0,
        }
    char_lengths = [len(text) for text in texts]
    sentence_counts = [max(1, len([part for part in re.split(r"[.!?\n]+", text) if part.strip()])) for text in texts]
    question_ratio = round(sum(1 for text in texts if "?" in text or "어?" in text or "까" in text[-3:]) / len(texts), 3)
    return {
        "sample_count": len(texts),
        "char_min": min(char_lengths),
        "char_p50": percentile(char_lengths, 0.50),
        "char_p75": percentile(char_lengths, 0.75),
        "char_p90": percentile(char_lengths, 0.90),
        "sentence_p50": percentile(sentence_counts, 0.50),
        "question_ratio": question_ratio,
    }


def korean_ratio(text: str) -> float:
    if not text:
        return 0.0
    hangul = len(re.findall(r"[가-힣]", text))
    return hangul / max(len(text), 1)


def has_noise_repetition(text: str) -> bool:
    compact = text.replace(" ", "")
    return bool(re.search(r"(.)\1\1\1", compact))


def clean_example(text: str) -> bool:
    if not text or len(text) < 6:
        return False
    if re.fullmatch(r"[\W_]+", text):
        return False
    if text.lower() == "vs":
        return False
    return True


def raw_quality_score(text: str) -> int:
    score = 0
    if 6 <= len(text) <= 42:
        score += 1
    if korean_ratio(text) >= 0.45:
        score += 1
    if not has_noise_repetition(text):
        score += 1
    if not re.search(r"(구군|우이도|따$|^\w{1,2}$)", text):
        score += 1
    if classify(text):
        score += 1
    return score


def message_quality_score(text: str) -> int:
    score = 0
    if 8 <= len(text) <= 120:
        score += 1
    if korean_ratio(text) >= 0.45:
        score += 1
    if not any(re.search(pattern, text) for pattern in MESSAGE_EXCLUDE_PATTERNS):
        score += 2
    if classify(text):
        score += 1
    return score


def is_romantic_runtime_text(text: str) -> bool:
    if not clean_example(text):
        return False
    if len(text) > 140:
        return False
    if any(re.search(pattern, text) for pattern in MESSAGE_EXCLUDE_PATTERNS):
        return False
    return message_quality_score(text) >= 4


def collect_from_raw():
    buckets = {}
    source_rows = []
    total_kept = 0
    for path_str in glob.glob(str(RAW_DIR / "*.json")):
        path = Path(path_str)
        data = json.loads(path.read_text(encoding="utf-8"))
        kept = 0
        scores = []
        for event in data.get("events", []):
            text = normalize(event.get("text", ""))
            if not clean_example(text):
                continue
            score = raw_quality_score(text)
            scores.append(score)
            if score < 3:
                continue
            tags = classify(text)
            if not tags:
                continue
            kept += 1
            for key in tags:
                buckets.setdefault(key, [])
                buckets[key].append(text)
        total_kept += kept
        source_rows.append(
            {
                "video_id": data.get("video_id"),
                "title": data.get("title"),
                "lang": data.get("lang"),
                "event_count": len(data.get("events", [])),
                "accepted_event_count": kept,
                "acceptance_ratio": round(kept / max(len(data.get("events", [])), 1), 3),
                "avg_quality_score": round(sum(scores) / max(len(scores), 1), 2),
                "source_url": data.get("source_url"),
            }
        )
    return {key: dedupe_keep_order(values) for key, values in buckets.items()}, source_rows, total_kept


def collect_from_messages():
    outgoing = []
    incoming = []
    for path in sorted(MESSAGES_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("type") != "text":
                    continue
                text = normalize(row.get("content", ""))
                if not is_romantic_runtime_text(text):
                    continue
                if row.get("direction") == "outgoing":
                    outgoing.append(text)
                elif row.get("direction") == "incoming":
                    incoming.append(text)
    return dedupe_keep_order(outgoing), dedupe_keep_order(incoming)


def collect_buckets_from_texts(texts: list) -> dict:
    buckets = {}
    for text in texts:
        for key in classify(text):
            buckets.setdefault(key, [])
            buckets[key].append(text)
    return {key: dedupe_keep_order(values) for key, values in buckets.items()}


def collect_from_approved_patterns():
    if not APPROVED_PATTERNS_PATH.exists():
        return {}
    data = json.loads(APPROVED_PATTERNS_PATH.read_text(encoding="utf-8"))
    buckets = {}
    for row in data.get("patterns", []):
        if not row.get("canonical_checks", {}).get("passed", True):
            continue
        text = normalize(row.get("text", ""))
        category = row.get("category")
        if not text or not category:
            continue
        buckets.setdefault(category, [])
        buckets[category].append(text)
    return {key: dedupe_keep_order(values) for key, values in buckets.items()}


def load_rejected_texts() -> set:
    if not REJECTED_PATTERNS_PATH.exists():
        return set()
    data = json.loads(REJECTED_PATTERNS_PATH.read_text(encoding="utf-8"))
    return {
        normalize(row.get("text", ""))
        for row in data.get("patterns", [])
        if normalize(row.get("text", ""))
    }


def filter_rejected_buckets(buckets: dict, rejected_texts: set) -> dict:
    if not rejected_texts:
        return buckets
    filtered = {}
    for key, values in buckets.items():
        kept = [value for value in values if normalize(value) not in rejected_texts]
        filtered[key] = dedupe_keep_order(kept)
    return filtered


def build_pattern_catalog(raw_buckets: dict, runtime_buckets: dict, user_buckets: dict, approved_buckets: dict) -> dict:
    catalog = {}
    for key in sorted(set(raw_buckets) | set(runtime_buckets) | set(user_buckets) | set(approved_buckets)):
        runtime_examples = runtime_buckets.get(key, [])[-8:]
        user_examples = user_buckets.get(key, [])[-8:]
        approved_examples = approved_buckets.get(key, [])[:8]
        corpus_examples = raw_buckets.get(key, [])[:12]
        merged = dedupe_keep_order(approved_examples + runtime_examples + user_examples + corpus_examples)
        catalog[key] = {
            "count": len(merged),
            "examples": merged[:12],
            "approved_examples": approved_examples,
            "runtime_examples": runtime_examples,
            "user_examples": user_examples,
            "corpus_examples": corpus_examples,
            "length_profile": text_length_profile(merged),
        }
    return catalog


def build_move_blueprints(pattern_catalog: dict) -> dict:
    def examples_for(*categories: str, allow_corpus: bool = True) -> list:
        preferred = []
        fallback = []
        for category in categories:
            payload = pattern_catalog.get(category) or {}
            preferred.extend(payload.get("runtime_examples", [])[:3])
            preferred.extend(payload.get("user_examples", [])[:2])
            if allow_corpus:
                fallback.extend(payload.get("corpus_examples", [])[:3])
        return dedupe_keep_order(preferred + fallback)[:6]

        return {
        "soft_observation": {
            "categories": ["scene_share", "emotion_check"],
            "examples": examples_for("scene_share", "emotion_check"),
        },
        "self_update": {
            "categories": ["self_update"],
            "examples": examples_for("self_update", allow_corpus=False),
        },
        "one_light_question": {
            "categories": ["current_state_check", "meal_routine"],
            "examples": examples_for("current_state_check", "meal_routine", allow_corpus=False),
        },
        "meal_or_energy_check": {
            "categories": ["meal_routine", "emotion_check"],
            "examples": examples_for("meal_routine", "emotion_check"),
        },
        "care_offer": {
            "categories": ["care_offer"],
            "examples": examples_for("care_offer"),
        },
        "soft_question_or_affection": {
            "categories": ["affection_imagination", "current_state_check"],
            "examples": examples_for("affection_imagination", "current_state_check"),
        },
        "thought_of_you": {
            "categories": ["thought_of_you"],
            "examples": examples_for("thought_of_you", allow_corpus=False),
        },
        "small_self_disclosure": {
            "categories": ["self_update", "scene_share"],
            "examples": examples_for("self_update", "scene_share"),
        },
        "shared_image": {
            "categories": ["photo_request", "scene_share"],
            "examples": examples_for("photo_request", "scene_share"),
        },
    }


def collect_texts_for_categories(pattern_catalog: dict, categories: list, prefer_runtime: bool = True) -> list:
    rows = []
    for category in categories:
        payload = pattern_catalog.get(category) or {}
        if prefer_runtime:
            rows.extend(payload.get("runtime_examples", []))
            rows.extend(payload.get("user_examples", []))
        rows.extend(payload.get("corpus_examples", []))
    return dedupe_keep_order(rows)


def build_recipe_length_profiles(pattern_catalog: dict, situation_recipes: dict) -> dict:
    move_to_categories = {
        "soft_observation": ["scene_share", "emotion_check"],
        "self_update": ["self_update"],
        "one_light_question": ["current_state_check", "meal_routine"],
        "meal_or_energy_check": ["meal_routine", "emotion_check"],
        "care_offer": ["care_offer"],
        "soft_question_or_affection": ["affection_imagination", "current_state_check"],
        "thought_of_you": ["thought_of_you"],
        "small_self_disclosure": ["self_update", "scene_share"],
        "shared_image": ["photo_request", "scene_share"],
    }
    profiles = {}
    for recipe_key, recipe in situation_recipes.items():
        texts = []
        for move in recipe.get("shape", []):
            texts.extend(collect_texts_for_categories(pattern_catalog, move_to_categories.get(move, [])))
        texts = dedupe_keep_order(texts)
        base = text_length_profile(texts)
        profiles[recipe_key] = {
            "sample_count": base["sample_count"],
            "recommended_char_range": [max(12, base["char_p50"] - 10), max(base["char_p50"], base["char_p75"] + 8)],
            "recommended_sentence_range": [1, max(1, min(3, base["sentence_p50"] + 1))],
            "question_ratio": base["question_ratio"],
            "question_density_hint": (
                "질문 1개 이하 유지" if base["question_ratio"] < 0.45 else "질문이 자연스럽지만 연속 2개는 피하기"
            ),
        }
    return profiles


def load_manifest_sources() -> list:
    if not MANIFEST_PATH.exists():
        return []
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def build_catalog():
    raw_buckets, source_rows, accepted_raw = collect_from_raw()
    outgoing, incoming = collect_from_messages()
    runtime_buckets = collect_buckets_from_texts(outgoing)
    user_buckets = collect_buckets_from_texts(incoming)
    approved_buckets = collect_from_approved_patterns()
    rejected_texts = load_rejected_texts()
    raw_buckets = filter_rejected_buckets(raw_buckets, rejected_texts)
    runtime_buckets = filter_rejected_buckets(runtime_buckets, rejected_texts)
    user_buckets = filter_rejected_buckets(user_buckets, rejected_texts)
    pattern_catalog = build_pattern_catalog(raw_buckets, runtime_buckets, user_buckets, approved_buckets)
    situation_recipes = {
        "morning_busy_checkin": {
            "when": "출근 전후, 바쁜 오전, 답장 길이는 짧게",
            "shape": ["soft_observation", "self_update", "one_light_question"],
            "avoid_if_blocked": ["current_state_check", "meal_routine"],
        },
        "midday_soft_ping": {
            "when": "점심 전후, 가볍게 연결 유지하고 싶을 때",
            "shape": ["thought_of_you", "self_update", "meal_or_energy_check"],
            "avoid_if_blocked": ["meal_routine"],
        },
        "after_work_comfort": {
            "when": "퇴근길, 피곤함이 느껴질 때",
            "shape": ["soft_observation", "care_offer", "self_update"],
            "avoid_if_blocked": ["emotion_check", "commute_arrival"],
        },
        "night_wind_down": {
            "when": "잘 준비 전, 분위기를 편하게 잇고 싶을 때",
            "shape": ["self_update", "shared_image", "soft_question_or_affection"],
            "avoid_if_blocked": ["appearance_imagination", "photo_request"],
        },
        "photo_affection_followup": {
            "when": "사진이나 모습 얘기가 방금 나왔을 때",
            "shape": ["soft_observation", "affection_imagination", "small_self_disclosure"],
            "avoid_if_blocked": ["photo_request", "appearance_imagination"],
        },
    }
    move_blueprints = build_move_blueprints(pattern_catalog)
    recipe_length_profiles = build_recipe_length_profiles(pattern_catalog, situation_recipes)

    manifest_rows = load_manifest_sources()
    quality_report = {
        "schema_version": 1,
        "managed_by": "build_conversation_pattern_catalog",
        "source_count": len(manifest_rows),
        "accepted_raw_event_count": accepted_raw,
        "sources": sorted(source_rows, key=lambda row: row["accepted_event_count"], reverse=True),
    }
    QUALITY_REPORT_PATH.write_text(json.dumps(quality_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "schema_version": 2,
        "managed_by": "build_conversation_pattern_catalog",
        "dataset_summary": {
            "source_count": len(manifest_rows),
            "accepted_raw_event_count": accepted_raw,
            "romantic_outgoing_count": len(outgoing),
            "romantic_incoming_count": len(incoming),
            "approved_pattern_count": sum(len(values) for values in approved_buckets.values()),
            "quality_report_path": str(QUALITY_REPORT_PATH),
        },
        "pattern_catalog": pattern_catalog,
        "move_blueprints": move_blueprints,
        "situation_recipes": situation_recipes,
        "recipe_length_profiles": recipe_length_profiles,
        "global_length_profile": {
            "woongbbi_outgoing": text_length_profile(outgoing),
            "user_incoming": text_length_profile(incoming),
        },
        "runtime_filter_notes": [
            "세팅, 파일, 프로세스, 이미지 생성 관련 문장은 연인 대화 패턴 학습에서 제외한다.",
            "자동 자막은 품질 점수 3점 이상만 카탈로그에 반영한다.",
            "실제 대화 로그는 웅삐다운 발화만 추려서 우선 반영한다.",
            "자동 승인형으로 통과한 패턴은 approved layer에서 우선 반영한다.",
        ],
        "notes": "공개 커플 코퍼스와 실제 웅삐 대화 로그를 섞되, 연인 대화다운 발화만 정제해 쓴 패턴 카탈로그",
    }


def write_profile(catalog: dict):
    summary = catalog.get("dataset_summary", {})
    lines = [
        "# Woongbbi Conversation Pattern Catalog",
        "",
        "## 목적",
        "",
        "- 실제 연인처럼 보이는 질문, 대답, 선톡 흐름을 카테고리별로 정리한다.",
        "- 자동 자막 코퍼스는 품질 점수를 거친 뒤 쓰고, 실제 웅삐 로그는 세팅 문장을 제외하고 반영한다.",
        "",
        "## 데이터 요약",
        "",
        f"- source_count: {summary.get('source_count', 0)}",
        f"- accepted_raw_event_count: {summary.get('accepted_raw_event_count', 0)}",
        f"- romantic_outgoing_count: {summary.get('romantic_outgoing_count', 0)}",
        f"- romantic_incoming_count: {summary.get('romantic_incoming_count', 0)}",
        f"- approved_pattern_count: {summary.get('approved_pattern_count', 0)}",
        "",
        "## 길이 가이드",
        "",
    ]
    for key, profile in sorted(catalog.get("recipe_length_profiles", {}).items()):
        lines.extend(
            [
                f"### {key}",
                f"- recommended_char_range: {profile.get('recommended_char_range')}",
                f"- recommended_sentence_range: {profile.get('recommended_sentence_range')}",
                f"- question_density_hint: {profile.get('question_density_hint')}",
                "",
            ]
        )
    lines.extend([
        "## 상황 레시피",
        "",
    ])
    for key, recipe in catalog["situation_recipes"].items():
        lines.extend(
            [
                f"### {key}",
                f"- when: {recipe['when']}",
                f"- shape: {', '.join(recipe['shape'])}",
                f"- avoid_if_blocked: {', '.join(recipe['avoid_if_blocked'])}",
                "",
            ]
        )
    lines.extend(["## 주요 패턴 예시", ""])
    for key, payload in sorted(catalog.get("pattern_catalog", {}).items()):
        examples = payload.get("examples", [])[:3]
        if not examples:
            continue
        lines.append(f"### {key}")
        for example in examples:
            lines.append(f"- {example}")
        lines.append("")
    lines.extend(
        [
            "## 메모",
            "",
            "- 질문을 반복하기보다 `관찰 -> 자기상황 -> 가벼운 질문` 흐름을 우선한다.",
            "- 사진 얘기가 최근 반복됐으면 다시 요구하지 말고, 방금 받은 감정이나 분위기를 짧게 묘사한다.",
            "- 선톡이 최근 `생각났어`류로 반복됐으면 현재 장면 공유형이나 자기상황 공유형으로 바꾼다.",
            "",
        ]
    )
    PROFILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    catalog = build_catalog()
    STATE_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_profile(catalog)
    print(str(STATE_PATH))
    print(str(PROFILE_PATH))
    print(str(QUALITY_REPORT_PATH))


if __name__ == "__main__":
    main()
