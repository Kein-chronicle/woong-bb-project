#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from project_paths import ROOT, log_path
STATE = ROOT / "state"
CATALOG_PATH = STATE / "conversation_pattern_catalog.json"
APPROVED_PATH = STATE / "approved_conversation_patterns.json"
REJECTED_PATH = STATE / "rejected_conversation_patterns.json"
LEARNING_STATE_PATH = STATE / "conversation_learning_state.json"
SOURCE_REGISTRY_PATH = STATE / "conversation_source_registry.json"
DECISION_LOG_PATH = log_path("response_decision_log.jsonl")
BUILD_SCRIPT_PATH = ROOT / "scripts" / "build_conversation_pattern_catalog.py"

PATTERN_RULES = [
    ("current_state_check", ["지금 뭐", "뭐하고", "뭐 해", "어디쯤", "어디야", "가는 중", "도착했", "뭐 하고 있어"]),
    ("meal_routine", ["밥", "점심", "저녁", "먹었어", "먹을거야", "커피", "챙겨 먹"]),
    ("emotion_check", ["힘들", "지쳤", "피곤", "괜찮아", "기분 어때", "오늘 어땠"]),
    ("photo_request", ["사진", "보여주", "찍어줘", "지금 모습"]),
    ("affection_imagination", ["같이", "옆에", "안고", "안기", "보고 싶", "보고싶", "같이 있었으면"]),
    ("self_update", ["나 지금", "방금", "나는 지금", "나 이제", "지금은 나는", "씻고", "누워있", "퇴근길", "집 와서"]),
    ("thought_of_you", ["오빠 생각", "문득", "갑자기", "궁금해서 먼저", "생각하고 있었어"]),
    ("care_offer", ["물 마셔", "천천히", "쉬어", "무리하지", "챙겨", "조심히 가"]),
    ("playful_tease", ["모야", "ㅋㅋ", "반칙", "왜케", "헤헤", "ㅎㅎ", "또 왔어"]),
    ("scene_share", ["조용", "공기", "날씨", "바람", "협탁", "머그컵", "밤", "퇴근길", "창밖"]),
]

EXPLICIT_PATTERNS = [
    r"섹스", r"성관계", r"자위", r"오르가즘", r"삽입", r"사정", r"애무",
    r"성기", r"음부", r"보지", r"자지", r"고추", r"펠라", r"벗겨", r"야하게",
]

IDENTITY_CONFLICT_PATTERNS = [
    r"\b(자기야|여보|남편|신랑)\b",
    r"\b(baby|darling|honey)\b",
]

JOB_CONFLICT_PATTERNS = [
    r"회의", r"팀장", r"사무실", r"출근카드", r"교수님", r"수업", r"강의실",
]

ALLOWED_JOB_CONTEXT_PATTERNS = [
    r"병원", r"병동", r"인수인계", r"차팅", r"환자", r"퇴근", r"출근길",
]

TONE_CONFLICT_PATTERNS = [
    r"bro", r"야 너", r"ㅋㅋㅋㅋㅋㅋㅋㅋ", r"씨발", r"ㅗ",
]

FRAGMENT_ENDING_PATTERNS = [
    r"그나마$",
    r"시간을$",
    r"길인데$",
    r"그리고$",
    r"정도$",
    r"같이$",
    r"때문에$",
]

FIXED_REJECTION_NEEDLES = [
    "/Users/", ".json", ".jsonl", ".md", "세팅모드", "설정파일", "폴더", "파일",
    "프로세스", "타이머", "스킬", "루트", "캘린더", "이미지 생성",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def dedupe_keep_order(values: list) -> list:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def classify_categories(text: str) -> list:
    matched = []
    for key, needles in PATTERN_RULES:
        if any(needle in text for needle in needles):
            matched.append(key)
    return matched


def hangul_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(re.findall(r"[가-힣]", text)) / max(len(text), 1)


def detect_change_type(text: str, category: str) -> str:
    if category in {"playful_tease", "care_offer", "affection_imagination", "thought_of_you"}:
        return "tone_adjustment"
    if len(text) <= 18 or len(text) >= 80:
        return "length_adjustment"
    return "pattern_change"


def determine_scope(category: str) -> str:
    hybrid_categories = {
        "current_state_check",
        "meal_routine",
        "emotion_check",
        "photo_request",
        "affection_imagination",
        "self_update",
        "thought_of_you",
        "care_offer",
        "playful_tease",
        "scene_share",
    }
    if category in hybrid_categories:
        return "hybrid"
    return "review"


def build_routing(category: str, scope: str) -> dict:
    generation_targets = ["conversation_pattern_catalog", "approved_conversation_patterns"]
    review_targets = ["rejected_conversation_patterns", "generation_review_state"]
    if category in {"current_state_check", "photo_request", "playful_tease", "thought_of_you"}:
        generation_targets.append("conversation_pattern_state")
    if scope == "generation":
        review_targets = []
    if scope == "review":
        generation_targets = ["approved_conversation_patterns"]
    return {
        "generation_targets": dedupe_keep_order(generation_targets),
        "review_targets": dedupe_keep_order(review_targets),
    }


def canonical_checks(text: str, category: str) -> dict:
    body = normalize(text)
    identity_conflict = bool(re.search("|".join(IDENTITY_CONFLICT_PATTERNS), body, re.IGNORECASE))
    explicit_conflict = any(re.search(pattern, body, re.IGNORECASE) for pattern in EXPLICIT_PATTERNS)
    tone_conflict = any(re.search(pattern, body, re.IGNORECASE) for pattern in TONE_CONFLICT_PATTERNS)
    fixed_noise = any(needle in body for needle in FIXED_REJECTION_NEEDLES)
    non_korean = hangul_ratio(body) < 0.3
    fragment_conflict = any(re.search(pattern, body) for pattern in FRAGMENT_ENDING_PATTERNS)
    job_conflict = False
    if category == "self_update":
        job_conflict = any(re.search(pattern, body, re.IGNORECASE) for pattern in JOB_CONFLICT_PATTERNS)
        if any(re.search(pattern, body, re.IGNORECASE) for pattern in ALLOWED_JOB_CONTEXT_PATTERNS):
            job_conflict = False
    relationship_conflict = bool(re.search(r"\b(남편|신랑|아내|와이프)\b", body))
    if category in {"current_state_check", "meal_routine", "care_offer"} and len(body) < 18 and "오빠" not in body:
        fragment_conflict = True
    if "대부도" in body or "지역 어디야" in body:
        fragment_conflict = True
    passed = not any([identity_conflict, explicit_conflict, tone_conflict, fixed_noise, non_korean, fragment_conflict, job_conflict, relationship_conflict])
    reasons = []
    if identity_conflict:
        reasons.append("identity_conflict")
    if explicit_conflict:
        reasons.append("intimacy_conflict")
    if tone_conflict:
        reasons.append("tone_conflict")
    if fixed_noise:
        reasons.append("non_dialogue_noise")
    if non_korean:
        reasons.append("language_conflict")
    if fragment_conflict:
        reasons.append("naturalness_conflict")
    if job_conflict:
        reasons.append("job_conflict")
    if relationship_conflict:
        reasons.append("relationship_conflict")
    return {
        "passed": passed,
        "reasons": reasons,
        "identity_safe": not identity_conflict,
        "job_safe": not job_conflict,
        "relationship_safe": not relationship_conflict,
        "intimacy_safe": not explicit_conflict,
        "tone_safe": not tone_conflict,
        "language_safe": not non_korean,
        "naturalness_safe": not fragment_conflict,
    }


def mine_candidates(limit_per_category: int = 4) -> list:
    catalog = load_json(CATALOG_PATH, {})
    pattern_catalog = catalog.get("pattern_catalog") or {}
    candidates = []
    for category, payload in sorted(pattern_catalog.items()):
        examples = []
        examples.extend(payload.get("runtime_examples", [])[:limit_per_category])
        examples.extend(payload.get("user_examples", [])[:limit_per_category])
        examples.extend(payload.get("examples", [])[:limit_per_category])
        for text in dedupe_keep_order(examples)[:limit_per_category]:
            body = normalize(text)
            if len(body) < 8 or len(body) > 140:
                continue
            candidates.append(
                {
                    "text": body,
                    "category": category,
                    "source_type": "catalog_seed",
                    "source_ref": str(CATALOG_PATH),
                    "change_type": detect_change_type(body, category),
                    "application_scope": determine_scope(category),
                    "asset_type": "text",
                }
            )
    return candidates


def build_pattern_id(category: str, text: str) -> str:
    compact = re.sub(r"[^a-z0-9가-힣]+", "-", text.lower()).strip("-")
    compact = compact[:36] or "pattern"
    return f"{category}__{compact}"


def review_candidates(candidates: list) -> dict:
    approved_state = load_json(APPROVED_PATH, {"schema_version": 1, "managed_by": "conversation_learning_loop", "updated_at": None, "patterns": []})
    rejected_state = load_json(REJECTED_PATH, {"schema_version": 1, "managed_by": "conversation_learning_loop", "updated_at": None, "patterns": []})
    approved_existing = {row.get("id"): row for row in approved_state.get("patterns", [])}
    rejected_existing = {row.get("id"): row for row in rejected_state.get("patterns", [])}

    approved_new = []
    rejected_new = []

    for row in candidates:
        text = normalize(row.get("text", ""))
        category = row.get("category") or (classify_categories(text) or [None])[0]
        if not category:
            continue
        pattern_id = row.get("id") or build_pattern_id(category, text)
        checks = canonical_checks(text, category)
        payload = {
            "id": pattern_id,
            "text": text,
            "category": category,
            "change_type": row.get("change_type") or detect_change_type(text, category),
            "application_scope": row.get("application_scope") or determine_scope(category),
            "asset_type": row.get("asset_type") or "text",
            "source_type": row.get("source_type") or "external_candidate",
            "source_ref": row.get("source_ref"),
            "canonical_checks": checks,
            "routing": build_routing(category, row.get("application_scope") or determine_scope(category)),
            "updated_at": now_iso(),
        }
        if checks["passed"]:
            payload["approved_at"] = now_iso()
            approved_existing[pattern_id] = payload
            rejected_existing.pop(pattern_id, None)
            approved_new.append(payload)
        else:
            payload["rejected_at"] = now_iso()
            approved_existing.pop(pattern_id, None)
            rejected_existing[pattern_id] = payload
            rejected_new.append(payload)

    approved_state["patterns"] = sorted(approved_existing.values(), key=lambda row: (row.get("category", ""), row.get("id", "")))
    approved_state["updated_at"] = now_iso()
    rejected_state["patterns"] = sorted(rejected_existing.values(), key=lambda row: (row.get("category", ""), row.get("id", "")))
    rejected_state["updated_at"] = now_iso()
    save_json(APPROVED_PATH, approved_state)
    save_json(REJECTED_PATH, rejected_state)

    learning_state = load_json(LEARNING_STATE_PATH, {
        "schema_version": 1,
        "managed_by": "conversation_learning_loop",
        "updated_at": None,
        "last_bootstrapped_at": None,
        "last_reviewed_at": None,
        "last_applied_at": None,
        "last_candidate_count": 0,
        "last_approved_count": 0,
        "last_rejected_count": 0,
        "last_rebuild_triggered": False,
        "notes": "대화 학습 루프 실행 메타데이터",
    })
    learning_state["updated_at"] = now_iso()
    learning_state["last_reviewed_at"] = now_iso()
    learning_state["last_candidate_count"] = len(candidates)
    learning_state["last_approved_count"] = len(approved_new)
    learning_state["last_rejected_count"] = len(rejected_new)
    save_json(LEARNING_STATE_PATH, learning_state)
    append_jsonl(
        DECISION_LOG_PATH,
        {
            "timestamp": now_iso(),
            "decision_type": "conversation_learning_review",
            "candidate_count": len(candidates),
            "approved_count": len(approved_new),
            "rejected_count": len(rejected_new),
        },
    )
    return {
        "candidate_count": len(candidates),
        "approved_count": len(approved_new),
        "rejected_count": len(rejected_new),
        "approved_patterns": approved_new,
        "rejected_patterns": rejected_new,
    }


def rebuild_catalog() -> None:
    subprocess.run(["python3", str(BUILD_SCRIPT_PATH)], check=True, cwd=str(ROOT))
    learning_state = load_json(LEARNING_STATE_PATH, {})
    learning_state["updated_at"] = now_iso()
    learning_state["last_applied_at"] = now_iso()
    learning_state["last_rebuild_triggered"] = True
    save_json(LEARNING_STATE_PATH, learning_state)
    append_jsonl(
        DECISION_LOG_PATH,
        {
            "timestamp": now_iso(),
            "decision_type": "conversation_learning_catalog_rebuilt",
            "catalog_path": str(CATALOG_PATH),
        },
    )


def cmd_bootstrap(_args) -> int:
    load_json(SOURCE_REGISTRY_PATH, {})
    load_json(LEARNING_STATE_PATH, {})
    load_json(APPROVED_PATH, {})
    load_json(REJECTED_PATH, {})
    state = load_json(LEARNING_STATE_PATH, {})
    state["updated_at"] = now_iso()
    state["last_bootstrapped_at"] = now_iso()
    save_json(LEARNING_STATE_PATH, state)
    print(json.dumps({"ok": True, "bootstrapped_at": state["last_bootstrapped_at"]}, ensure_ascii=False, indent=2))
    return 0


def cmd_seed_registry(_args) -> int:
    registry = load_json(SOURCE_REGISTRY_PATH, {})
    registry["updated_at"] = now_iso()
    save_json(SOURCE_REGISTRY_PATH, registry)
    print(json.dumps({"ok": True, "source_count": len(registry.get("sources", []))}, ensure_ascii=False, indent=2))
    return 0


def cmd_mine_candidates(args) -> int:
    candidates = mine_candidates(limit_per_category=args.limit_per_category)
    print(json.dumps({"ok": True, "candidate_count": len(candidates), "candidates": candidates}, ensure_ascii=False, indent=2))
    return 0


def cmd_review_candidates(args) -> int:
    if args.json_file:
        candidates = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    else:
        candidates = mine_candidates(limit_per_category=args.limit_per_category)
    result = review_candidates(candidates)
    if args.rebuild_catalog:
        rebuild_catalog()
        result["catalog_rebuilt"] = True
    else:
        result["catalog_rebuilt"] = False
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="approved conversation pattern learning loop")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap")
    sub.add_parser("seed-registry")
    mine = sub.add_parser("mine-candidates")
    mine.add_argument("--limit-per-category", type=int, default=4)
    review = sub.add_parser("review-candidates")
    review.add_argument("--json-file", default=None)
    review.add_argument("--limit-per-category", type=int, default=4)
    review.add_argument("--rebuild-catalog", action="store_true", default=False)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "bootstrap":
        return cmd_bootstrap(args)
    if args.command == "seed-registry":
        return cmd_seed_registry(args)
    if args.command == "mine-candidates":
        return cmd_mine_candidates(args)
    if args.command == "review-candidates":
        return cmd_review_candidates(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
