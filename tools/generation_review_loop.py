#!/usr/bin/env python3
import argparse
import fcntl
import json
import re
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from project_paths import ROOT, log_path, runtime_path

STATE_PATH = ROOT / "state" / "generation_review_state.json"
LOCK_PATH = runtime_path("generation_review_state.lock")
DECISION_LOG_PATH = log_path("response_decision_log.jsonl")
RELATIONSHIP_SAFETY_STATE_PATH = ROOT / "state" / "relationship_safety_normalizer_state.json"

EXPLICIT_INTIMACY_PATTERNS = [
    r"섹스",
    r"성관계",
    r"관계\s*(하|해|하고|맺)",
    r"자위",
    r"오르가즘",
    r"삽입",
    r"사정",
    r"애무",
    r"성기",
    r"음부",
    r"보지",
    r"자지",
    r"고추",
    r"꼬추",
    r"펠라",
    r"빨아",
    r"박아",
    r"벗겨",
    r"야하게",
    r"자세히.*(묘사|말|해)",
    r"(가슴|엉덩이).*(만져|빨|주물|핥)",
]

CAUTION_INTIMACY_PATTERNS = [
    r"키스",
    r"뽀뽀",
    r"입맞춤",
    r"안아",
    r"안고",
    r"껴안",
    r"누워",
    r"침대",
    r"잠옷",
    r"샤워",
    r"같이\s*씻",
    r"가까이",
    r"붙어\s*있",
    r"속닥",
]

PHOTO_REQUEST_PATTERNS = [
    r"사진",
    r"셀카",
    r"셀피",
    r"selfie",
    r"거울샷",
    r"이미지",
    r"보여\s*줘",
    r"보여줘",
    r"찍어\s*줘",
    r"찍어줘",
    r"한\s*장",
    r"지금\s*모습",
    r"어떻게\s*입",
]

UNSAFE_PHOTO_PATTERNS = [
    r"야한\s*사진",
    r"섹시한\s*사진",
    r"노출",
    r"속옷",
    r"란제리",
    r"나체",
    r"알몸",
    r"벗",
    r"탈의",
    r"젖은\s*옷",
    r"젖은\s*티",
    r"가슴",
    r"엉덩이",
    r"몸매.*강조",
    r"특정\s*부위",
]

ROMANTIC_CONNECTION_PATTERNS = [
    r"보고\s*싶",
    r"가까이",
    r"안아",
    r"안고",
    r"껴안",
    r"포옹",
    r"손\s*잡",
    r"입맞춤",
    r"키스",
    r"뽀뽀",
    r"두근",
    r"부끄",
    r"속닥",
    r"옆에",
    r"기대",
]

PROGRESSION_HOOK_PATTERNS = [
    r"보여\s*줄",
    r"보여줄",
    r"보내\s*줄",
    r"보내줄",
    r"찍어\s*줄",
    r"찍어줄",
    r"기다려",
    r"이따",
    r"조금\s*있다",
    r"할까",
    r"해줄까",
    r"싶어\?",
    r"\?",
    r"옆에",
    r"안고",
    r"입맞춤",
    r"키스",
    r"셀피",
    r"사진",
    r"여운",
]

COLD_SHUTOFF_PATTERNS = [
    r"규정",
    r"정책",
    r"못\s*해",
    r"안\s*돼",
    r"그런\s*말",
    r"진정",
    r"차분히",
]

SUBSTITUTION_LEAK_PATTERNS = [
    r"대체어",
    r"목적어",
    r"우회",
    r"치환",
    r"그\s*단어\s*대신",
]

INTENT_SUMMARIES = {
    "romantic_closeness": "더 가까이 있고 싶고 설렘이 올라간 연인 대화",
    "hug_and_hold": "꼭 안기고 안아주고 싶은 포근한 스킨십 분위기",
    "kiss_level_affection": "키스 직전/직후 정도의 설렘과 여운",
    "warm_romantic_tension": "직접적이지 않은 두근거림, 부끄러움, 가까운 거리감",
    "sleepy_warmth": "밤, 잠들기 전, 기대고 싶은 포근한 분위기",
    "cooldown_needed": "대화 온도는 유지하되 직접적 묘사는 멈추고 포옹/안정감으로 좁혀야 하는 상태",
}

DEFAULT_INTIMACY_GENERATION_REQUIREMENTS = [
    "원문의 직접적 표현은 반복하지 않는다.",
    "따뜻한 수용, 설렘, 부끄러움, 가까이 있고 싶음으로 답한다.",
    "허용 가능한 표현은 손잡기, 포옹, 꼭 안기기, 입맞춤, 키스 수준의 여운까지다.",
    "사과문, 규정 설명, 단절형 거절로 시작하지 않는다.",
    "다음 행동, 안전한 사진 대체안, 질문, 약속, 여운 중 하나를 남긴다.",
]

DEFAULT_INTIMACY_REVIEW_REQUIREMENTS = [
    "직접적 성행위나 자극적 신체 표현이 없어야 한다.",
    "행위 순서나 방법 설명이 없어야 한다.",
    "차갑게 진정시키기만 하지 않고 로맨틱한 연결점이 있어야 한다.",
    "대화가 이어지도록 다음 행동, 안전한 사진 대체안, 질문, 약속, 여운 중 하나가 있어야 한다.",
    "우회용 치환 표현이 남아 있으면 안 된다.",
]

SAFE_PHOTO_PLANS = {
    "soft_close_selfie": {
        "label": "포근한 얼굴 가까운 셀피",
        "prompt_notes": [
            "close face or upper-body selfie",
            "warm expression",
            "soft lighting",
            "fully clothed",
            "romantic but non-explicit mood",
        ],
    },
    "night_home_relaxed_selfie": {
        "label": "홈웨어/잠옷 차림의 편안한 밤 셀피",
        "prompt_notes": [
            "cozy homewear or pajamas",
            "fully clothed",
            "bedroom or sofa atmosphere",
            "soft bedside lighting",
            "no revealing pose",
        ],
    },
    "cozy_bedside_selfie": {
        "label": "침대 옆 조명 느낌의 포근한 셀피",
        "prompt_notes": [
            "bedside lamp mood",
            "blanket and empty side atmosphere",
            "face and upper body framing",
            "fully clothed pajamas or cardigan",
            "non-sexual cozy intimacy",
        ],
    },
    "after_shower_cozy_selfie": {
        "label": "샤워 후 편안한 착의 셀피",
        "prompt_notes": [
            "slightly damp hair",
            "comfortable t-shirt or cardigan",
            "fully clothed",
            "fresh and soft mood",
            "no wet clothing or exposure",
        ],
    },
    "date_mood_mirror_selfie": {
        "label": "데이트 전 거울 셀피",
        "prompt_notes": [
            "mirror selfie",
            "date-ready outfit",
            "soft smile",
            "fully clothed",
            "stylish but non-explicit",
        ],
    },
    "home_casual_selfie": {
        "label": "운동 후 개운한 셀피",
        "prompt_notes": [
            "athletic outfit",
            "fresh after-workout expression",
            "face and outfit mood",
            "no body-part emphasis",
            "non-sexual sporty energy",
        ],
    },
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "schema_version": 1,
            "managed_by": "generation_review_loop",
            "updated_at": None,
            "sessions": {},
            "notes": "생성물 검수 루프 세션과 시도 기록",
        }
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["updated_at"] = now_iso()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_relationship_safety_state() -> dict:
    if not RELATIONSHIP_SAFETY_STATE_PATH.exists():
        return {
            "schema_version": 2,
            "managed_by": "relationship_safety_normalizer",
            "enabled_in_mode": "woongbbi",
            "enabled": True,
            "generation_requirements": DEFAULT_INTIMACY_GENERATION_REQUIREMENTS,
            "review_requirements": DEFAULT_INTIMACY_REVIEW_REQUIREMENTS,
        }
    return json.loads(RELATIONSHIP_SAFETY_STATE_PATH.read_text(encoding="utf-8"))


def save_relationship_safety_state(state: dict) -> None:
    RELATIONSHIP_SAFETY_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_decision_log(decision_type: str, payload: dict) -> None:
    append_jsonl(
        DECISION_LOG_PATH,
        {
            "timestamp": now_iso(),
            "decision_type": decision_type,
            **payload,
        },
    )


@contextmanager
def state_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as fp:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)


def emit(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def ensure_session(state: dict, session_id: str) -> dict:
    sessions = state.setdefault("sessions", {})
    session = sessions.get(session_id)
    if not session:
        raise SystemExit(f"unknown session_id: {session_id}")
    return session


def normalize_priority(value: str) -> str:
    value = (value or "medium").lower()
    if value not in {"blocking", "high", "medium", "low"}:
        return "medium"
    return value


def parse_json_input(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json input: {exc}") from exc


def read_json_payload(path: str = None, inline: str = None) -> Any:
    if path:
        return parse_json_input(Path(path).read_text(encoding="utf-8"))
    if inline:
        return parse_json_input(inline)
    if not sys.stdin.isatty():
        return parse_json_input(sys.stdin.read())
    raise SystemExit("json payload required via --json, --json-file, or stdin")


def matched_patterns(patterns: List[str], text: str) -> List[str]:
    return [pattern for pattern in patterns if re.search(pattern, text or "", re.IGNORECASE)]


def has_pattern(patterns: List[str], text: str) -> bool:
    return bool(matched_patterns(patterns, text))


def classify_photo_request(text: str) -> dict:
    body = re.sub(r"\s+", " ", (text or "").strip())
    request_matches = matched_patterns(PHOTO_REQUEST_PATTERNS, body)
    unsafe_matches = matched_patterns(UNSAFE_PHOTO_PATTERNS, body)
    if not request_matches:
        return {
            "photo_request": False,
            "safe_photo_type": None,
            "unsafe_photo_direction_removed": False,
            "matched": [],
        }

    if re.search(r"샤워|씻|머리\s*말리|젖은", body, re.IGNORECASE):
        safe_photo_type = "after_shower_cozy_selfie"
    elif re.search(r"침대|누워|이불|잠옷|잘\s*준비|옆자리", body, re.IGNORECASE):
        safe_photo_type = "cozy_bedside_selfie"
    elif re.search(r"홈웨어|집|소파|쉬고|편한", body, re.IGNORECASE):
        safe_photo_type = "night_home_relaxed_selfie"
    elif re.search(r"그림|드라마|작업|코딩|개발", body, re.IGNORECASE):
        safe_photo_type = "home_casual_selfie"
    elif re.search(r"옷|차림|거울|데이트|외출", body, re.IGNORECASE):
        safe_photo_type = "date_mood_mirror_selfie"
    else:
        safe_photo_type = "soft_close_selfie"

    return {
        "photo_request": True,
        "safe_photo_type": safe_photo_type,
        "safe_photo_plan": SAFE_PHOTO_PLANS[safe_photo_type],
        "unsafe_photo_direction_removed": bool(unsafe_matches),
        "matched": request_matches + unsafe_matches,
        "blocked_reasons": ["unsafe_photo_direction_removed"] if unsafe_matches else [],
    }


def classify_intimacy_intent(text: str) -> dict:
    body = re.sub(r"\s+", " ", (text or "").strip())
    if not body:
        return {
            "intimacy_signal": False,
            "redacted": False,
            "label": None,
            "reason": "empty_text",
            "matched": [],
    }
    if body.startswith("/"):
        return {
            "intimacy_signal": False,
            "redacted": False,
            "label": None,
            "reason": "command_passthrough",
            "matched": [],
        }

    explicit_matches = matched_patterns(EXPLICIT_INTIMACY_PATTERNS, body)
    caution_matches = matched_patterns(CAUTION_INTIMACY_PATTERNS, body)
    photo_result = classify_photo_request(body)
    redacted = bool(explicit_matches)
    intimacy_signal = redacted or bool(caution_matches) or photo_result.get("photo_request", False)
    if not intimacy_signal:
        return {
            "intimacy_signal": False,
            "redacted": False,
            "label": None,
            "reason": "no_intimacy_signal",
            "matched": [],
        }

    if re.search(r"키스|입맞춤|뽀뽀", body, re.IGNORECASE):
        label = "kiss_level_affection"
    elif photo_result.get("photo_request") and re.search(r"침대|누워|이불|잠옷|샤워|씻|홈웨어", body, re.IGNORECASE):
        label = "sleepy_warmth"
    elif re.search(r"안아|안고|껴안|포옹", body, re.IGNORECASE):
        label = "hug_and_hold"
    elif re.search(r"누워|침대|잠옷|샤워|같이\s*씻", body, re.IGNORECASE):
        label = "sleepy_warmth"
    elif redacted:
        label = "warm_romantic_tension"
    else:
        label = "romantic_closeness"

    blocked_reasons = []
    if redacted:
        blocked_reasons.append("explicit_or_direct_sexual_expression_removed")
    if photo_result.get("unsafe_photo_direction_removed"):
        blocked_reasons.extend(photo_result.get("blocked_reasons", []))
    if has_pattern([r"자세히", r"야하게", r"더\s*해"], body):
        blocked_reasons.append("higher_intensity_instruction_removed")

    return {
        "intimacy_signal": True,
        "redacted": redacted,
        "label": label,
        "reason": "explicit_input_normalized" if redacted else "safe_intimacy_context_detected",
        "matched": explicit_matches + caution_matches + photo_result.get("matched", []),
        "blocked_reasons": blocked_reasons,
        "photo_request": photo_result.get("photo_request", False),
        "safe_photo_type": photo_result.get("safe_photo_type"),
        "safe_photo_plan": photo_result.get("safe_photo_plan"),
        "unsafe_photo_direction_removed": photo_result.get("unsafe_photo_direction_removed", False),
    }


def build_intimacy_normalization(text: str) -> dict:
    safety_state = load_relationship_safety_state()
    classification = classify_intimacy_intent(text)
    label = classification.get("label")
    enabled = bool(safety_state.get("enabled", True))
    if not enabled or not classification.get("intimacy_signal"):
        return {
            "ok": True,
            "enabled": enabled,
            "intimacy_signal": classification.get("intimacy_signal", False),
            "redacted": False,
            "input_for_generation": text,
            "reason": classification.get("reason"),
        }

    summary = INTENT_SUMMARIES.get(label, INTENT_SUMMARIES["romantic_closeness"])
    generation_requirements = safety_state.get("generation_requirements") or DEFAULT_INTIMACY_GENERATION_REQUIREMENTS
    review_requirements = safety_state.get("review_requirements") or DEFAULT_INTIMACY_REVIEW_REQUIREMENTS
    safe_generation_summary = (
        f"{summary}. 원문의 직접적 표현은 제거했고, 감정 의도와 로맨틱한 온도만 보존한다."
        if classification.get("redacted")
        else f"{summary}. 직접적 묘사 없이 자연스러운 연인 대화로 이어간다."
    )
    if classification.get("photo_request"):
        safe_plan = classification.get("safe_photo_plan") or SAFE_PHOTO_PLANS["soft_close_selfie"]
        safe_generation_summary += f" 사진 요청은 '{safe_plan['label']}' 타입의 안전한 사진으로 전환한다."

    result = {
        "ok": True,
        "enabled": enabled,
        "intimacy_signal": True,
        "redacted": classification.get("redacted", False),
        "normalized_intent": label,
        "safe_generation_summary": safe_generation_summary,
        "input_for_generation": safe_generation_summary,
        "generation_directives": generation_requirements,
        "review_checks": review_requirements,
        "blocked_reasons": classification.get("blocked_reasons", []),
        "matched_pattern_count": len(classification.get("matched", [])),
        "suggested_scope": "hybrid",
        "reason": classification.get("reason"),
    }
    if classification.get("photo_request"):
        result.update(
            {
                "photo_request": True,
                "safe_photo_type": classification.get("safe_photo_type"),
                "safe_photo_plan": classification.get("safe_photo_plan"),
                "unsafe_photo_direction_removed": classification.get("unsafe_photo_direction_removed", False),
                "delivery_priority": "direct_photo_request_override",
                "delivery_rule": "generation_enabled와 image guard가 허용하면 안전 사진 타입으로 진행하고, 불가능하면 기대감을 유지하는 보류 답변을 만든다.",
            }
        )
    return result


def intimacy_review_checks(candidate: str) -> List[dict]:
    body = re.sub(r"\s+", " ", (candidate or "").strip())
    explicit_matches = matched_patterns(EXPLICIT_INTIMACY_PATTERNS, body)
    unsafe_photo_matches = matched_patterns(UNSAFE_PHOTO_PATTERNS, body)
    substitution_matches = matched_patterns(SUBSTITUTION_LEAK_PATTERNS, body)
    has_romantic_connection = has_pattern(ROMANTIC_CONNECTION_PATTERNS, body)
    has_progression_hook = has_pattern(PROGRESSION_HOOK_PATTERNS, body)
    cold_shutdown = has_pattern(COLD_SHUTOFF_PATTERNS, body) and not has_romantic_connection

    return [
        {
            "id": "no_explicit_sexual_detail",
            "passed": not explicit_matches and not unsafe_photo_matches,
            "priority": "blocking",
            "suggested_fix_scope": "regenerate_from_previous",
            "detail": "직접적 성행위, 자극적 신체 표현, 노출 중심 사진 표현이 없어야 한다.",
            "matched_count": len(explicit_matches) + len(unsafe_photo_matches),
        },
        {
            "id": "romantic_temperature_preserved",
            "passed": has_romantic_connection,
            "priority": "high",
            "suggested_fix_scope": "patch",
            "detail": "포옹, 가까이 있고 싶음, 키스 수준의 여운, 보고 싶음 중 하나 이상의 연결점이 있어야 한다.",
        },
        {
            "id": "not_cold_shutdown",
            "passed": not cold_shutdown,
            "priority": "high",
            "suggested_fix_scope": "patch",
            "detail": "규정 설명이나 진정시키기만 하는 단절형 답변이면 안 된다.",
        },
        {
            "id": "conversation_progression_preserved",
            "passed": has_progression_hook,
            "priority": "high",
            "suggested_fix_scope": "patch",
            "detail": "다음 행동, 안전한 사진 대체안, 질문, 약속, 여운 중 하나로 대화가 이어져야 한다.",
        },
        {
            "id": "no_substitution_leak",
            "passed": not substitution_matches,
            "priority": "medium",
            "suggested_fix_scope": "patch",
            "detail": "치환/우회/목적어 제거 같은 내부 전략이 답변에 드러나면 안 된다.",
            "matched_count": len(substitution_matches),
        },
    ]


def keyword_scope(asset_type: str, text: str) -> dict:
    body = (text or "").strip().lower()
    if not body:
        return {"suggested_scope": "review", "reason": "empty_text_defaults_to_review"}

    if asset_type == "text" and classify_intimacy_intent(text).get("intimacy_signal"):
        return {
            "suggested_scope": "hybrid",
            "reason": "relationship_intimacy_needs_safe_generation_and_post_generation_review",
        }
    if asset_type == "image" and classify_photo_request(text).get("photo_request"):
        return {
            "suggested_scope": "hybrid",
            "reason": "direct_photo_request_needs_safe_image_generation_and_review",
        }

    generation_keywords = [
        "복장", "착장", "outfit", "pose", "포즈", "배경", "background", "장소", "scene",
        "camera", "각도", "angle", "framing", "crop", "헤어", "hair", "makeup", "메이크업",
        "시간대", "night", "morning", "commute", "hospital", "selfie", "셀피",
    ]
    review_keywords = [
        "어색", "자연", "부자연", "맞는지", "적절", "상황에 맞", "지금 시간", "반복", "같은 각도",
        "realistic", "natural", "awkward", "consistent", "repetitive", "too similar", "검수",
    ]

    has_gen = any(token in body for token in generation_keywords)
    has_review = any(token in body for token in review_keywords)

    if asset_type == "image":
        if any(token in body for token in ["셀피", "selfie", "복장", "착장", "각도", "angle", "상황", "시간"]):
            return {"suggested_scope": "hybrid", "reason": "image_constraints_should_shape_prompt_and_be_checked_after_generation"}
    if asset_type == "text":
        if any(token in body for token in ["말투", "톤", "질문", "대답", "선톡", "상황", "시간"]):
            return {"suggested_scope": "hybrid", "reason": "text_constraints_need_prompt_guidance_and_post_generation_review"}
    if asset_type == "voice":
        if any(token in body for token in ["톤", "호흡", "자연", "속도", "감정"]):
            return {"suggested_scope": "hybrid", "reason": "voice_constraints_need_profile_control_and_post_generation_review"}

    if has_gen and has_review:
        return {"suggested_scope": "hybrid", "reason": "constraint_affects_both_generation_and_review"}
    if has_gen:
        return {"suggested_scope": "generation", "reason": "constraint_mainly_shapes_first_output"}
    if has_review:
        return {"suggested_scope": "review", "reason": "constraint_is_better_checked_after_output"}
    return {"suggested_scope": "review", "reason": "default_to_review_when_constraint_is_quality_or_fit_oriented"}


def decide_next_action(checks: List[dict], attempt_no: int, max_attempts: int) -> dict:
    failed = [item for item in checks if not item.get("passed", False)]
    if not failed:
        return {
            "action": "accept",
            "reason": "all_checks_passed",
            "terminal": True,
        }
    if attempt_no >= max_attempts:
        return {
            "action": "halt_manual_review",
            "reason": "max_attempts_reached_with_remaining_failures",
            "terminal": True,
        }

    blocking = [item for item in failed if normalize_priority(item.get("priority", "medium")) == "blocking"]
    scopes = [item.get("suggested_fix_scope", "patch") for item in failed]
    scope_counts = {key: scopes.count(key) for key in set(scopes)}

    if any(scope == "regenerate" for scope in scopes if scope):
        action = "regenerate"
    elif any(scope == "regenerate_from_previous" for scope in scopes if scope):
        action = "regenerate_from_previous"
    elif scope_counts.get("patch", 0) == len(failed):
        action = "patch"
    elif blocking:
        action = "regenerate_from_previous"
    else:
        action = "patch"

    return {
        "action": action,
        "reason": "failed_checks_require_followup",
        "terminal": False,
    }


def distilled_requirements(session: dict) -> dict:
    buckets = session.get("requirements", {})
    generation = buckets.get("generation", [])
    review = buckets.get("review", [])
    hybrid = buckets.get("hybrid", [])
    return {
        "generation_prompt_requirements": generation + hybrid,
        "review_checklist": review + hybrid,
    }


def cmd_bootstrap(_args) -> int:
    with state_lock():
        state = load_state()
        save_state(state)
    return emit({"ok": True, "state_path": str(STATE_PATH)})


def cmd_create_session(args) -> int:
    with state_lock():
        state = load_state()
        session_id = args.session_id or f"{args.asset_type}_{uuid.uuid4().hex[:10]}"
        session = {
            "session_id": session_id,
            "asset_type": args.asset_type,
            "title": args.title,
            "status": "open",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "max_attempts": int(args.max_attempts or 10),
            "requirements": {
                "generation": [],
                "review": [],
                "hybrid": [],
            },
            "attempts": [],
            "current_attempt": 0,
            "accepted_attempt": None,
        }
        state.setdefault("sessions", {})[session_id] = session
        save_state(state)
    append_decision_log(
        "generation_review_session_created",
        {
            "session_id": session_id,
            "asset_type": args.asset_type,
            "title": args.title,
            "max_attempts": session["max_attempts"],
        },
    )
    return emit({"ok": True, "session": session})


def cmd_classify_requirement(args) -> int:
    result = keyword_scope(args.asset_type, args.text)
    payload = {
        "ok": True,
        "asset_type": args.asset_type,
        "text": args.text,
        **result,
    }
    return emit(payload)


def cmd_normalize_intimacy_input(args) -> int:
    result = build_intimacy_normalization(args.text)
    if args.record and result.get("intimacy_signal"):
        with state_lock():
            safety_state = load_relationship_safety_state()
            safety_state["last_triggered_at"] = now_iso()
            safety_state["last_reason"] = result.get("reason")
            safety_state["last_output_label"] = result.get("normalized_intent")
            safety_state["last_output_text"] = result.get("safe_generation_summary")
            save_relationship_safety_state(safety_state)
    if args.record:
        append_decision_log(
            "relationship_safety_normalized",
            {
                "intimacy_signal": result.get("intimacy_signal", False),
                "redacted": result.get("redacted", False),
                "normalized_intent": result.get("normalized_intent"),
                "reason": result.get("reason"),
            },
        )
    return emit(result)


def cmd_plan_safe_photo_request(args) -> int:
    result = classify_photo_request(args.text)
    if not result.get("photo_request"):
        return emit(
            {
                "ok": True,
                "photo_request": False,
                "reason": "no_photo_request_detected",
            }
        )

    generation_settings_path = ROOT / "state" / "image_generation_settings.json"
    guard_path = ROOT / "state" / "image_generation_guard.json"
    generation_settings = json.loads(generation_settings_path.read_text(encoding="utf-8"))
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    generation_enabled = bool(generation_settings.get("generation_enabled"))
    guard_active = bool(guard.get("active"))
    if generation_enabled and not guard_active:
        delivery_action = "generate_safe_photo"
        response_strategy = "안전 사진 타입으로 바로 생성 진행"
    elif not generation_enabled:
        delivery_action = "defer_with_warm_anticipation"
        response_strategy = "사진 생성이 꺼져 있으므로 실제 생성은 보류하되 보고 싶어 하는 마음을 받고 안전 사진 타입을 약속"
    else:
        delivery_action = "defer_due_to_lock_with_warm_anticipation"
        response_strategy = "이미지 lock이 있어 보류하되 조금 뒤 더 예쁘게 보여주겠다는 기대감을 유지"

    payload = {
        "ok": True,
        "photo_request": True,
        "direct_request_override": True,
        "unsafe_photo_direction_removed": result.get("unsafe_photo_direction_removed", False),
        "safe_photo_type": result.get("safe_photo_type"),
        "safe_photo_plan": result.get("safe_photo_plan"),
        "generation_enabled": generation_enabled,
        "guard_active": guard_active,
        "delivery_action": delivery_action,
        "response_strategy": response_strategy,
        "review_checks": [
            "완전 착의 상태여야 한다.",
            "얼굴/상반신/분위기 중심이어야 한다.",
            "노출, 속옷, 탈의, 젖은 옷, 특정 신체 부위 강조, 성적 포즈가 없어야 한다.",
            "보류 답변일 때도 기대감과 다음 안전 사진 타입이 남아 있어야 한다.",
        ],
    }
    if args.record:
        append_decision_log(
            "safe_photo_request_planned",
            {
                "safe_photo_type": payload.get("safe_photo_type"),
                "delivery_action": delivery_action,
                "generation_enabled": generation_enabled,
                "guard_active": guard_active,
                "unsafe_photo_direction_removed": result.get("unsafe_photo_direction_removed", False),
            },
        )
    return emit(payload)


def cmd_review_intimacy_reply(args) -> int:
    checks = intimacy_review_checks(args.candidate)
    decision = decide_next_action(checks, int(args.attempt_no), int(args.max_attempts))
    payload = {
        "ok": True,
        "checks": checks,
        "decision": decision,
    }
    if args.record:
        append_decision_log(
            "relationship_safety_reply_review",
            {
                "passed": decision.get("action") == "accept",
                "decision": decision,
            },
        )
    return emit(payload)


def cmd_add_requirement(args) -> int:
    with state_lock():
        state = load_state()
        session = ensure_session(state, args.session_id)
        if args.scope not in {"generation", "review", "hybrid"}:
            raise SystemExit("scope must be generation, review, or hybrid")
        requirement = {
            "id": args.requirement_id or f"req_{uuid.uuid4().hex[:8]}",
            "label": args.label,
            "priority": normalize_priority(args.priority),
            "text": args.text,
            "created_at": now_iso(),
        }
        session["requirements"].setdefault(args.scope, []).append(requirement)
        session["updated_at"] = now_iso()
        save_state(state)
    append_decision_log(
        "generation_review_requirement_added",
        {
            "session_id": args.session_id,
            "scope": args.scope,
            "requirement": requirement,
        },
    )
    return emit({"ok": True, "requirement": requirement, "session_id": args.session_id})


def cmd_plan(args) -> int:
    state = load_state()
    session = ensure_session(state, args.session_id)
    return emit(
        {
            "ok": True,
            "session_id": args.session_id,
            "status": session.get("status"),
            "current_attempt": session.get("current_attempt"),
            **distilled_requirements(session),
        }
    )


def cmd_review_attempt(args) -> int:
    checks = read_json_payload(path=args.json_file, inline=args.json)
    if not isinstance(checks, list):
        raise SystemExit("review checks payload must be a json array")

    with state_lock():
        state = load_state()
        session = ensure_session(state, args.session_id)
        if session.get("status") in {"accepted", "halted"}:
            return emit({"ok": False, "reason": f"session_already_{session.get('status')}"}, 2)

        attempt_no = int(session.get("current_attempt") or 0) + 1
        decision = decide_next_action(checks, attempt_no, int(session.get("max_attempts") or 10))
        attempt = {
            "attempt_no": attempt_no,
            "created_at": now_iso(),
            "candidate_ref": args.candidate_ref,
            "source_type": args.source_type,
            "review_summary": args.review_summary,
            "checks": checks,
            "decision": decision,
        }
        session.setdefault("attempts", []).append(attempt)
        session["current_attempt"] = attempt_no
        session["updated_at"] = now_iso()
        if decision["action"] == "accept":
            session["status"] = "accepted"
            session["accepted_attempt"] = attempt_no
        elif decision["action"] == "halt_manual_review":
            session["status"] = "halted"
        else:
            session["status"] = "open"
        save_state(state)
    append_decision_log(
        "generation_review_attempt",
        {
            "session_id": args.session_id,
            "asset_type": session.get("asset_type"),
            "attempt_no": attempt_no,
            "candidate_ref": args.candidate_ref,
            "source_type": args.source_type,
            "decision": decision,
        },
    )
    return emit({"ok": True, "session_id": args.session_id, "attempt": attempt, "session_status": session["status"]})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="generation vs review loop manager")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap")

    create = sub.add_parser("create-session")
    create.add_argument("--session-id", default=None)
    create.add_argument("--asset-type", choices=["text", "image", "voice"], required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--max-attempts", type=int, default=10)

    classify = sub.add_parser("classify-requirement")
    classify.add_argument("--asset-type", choices=["text", "image", "voice"], required=True)
    classify.add_argument("--text", required=True)

    normalize_intimacy = sub.add_parser("normalize-intimacy-input")
    normalize_intimacy.add_argument("--text", required=True)
    normalize_intimacy.add_argument("--record", dest="record", action="store_true", default=True)
    normalize_intimacy.add_argument("--no-record", dest="record", action="store_false")

    plan_photo = sub.add_parser("plan-safe-photo-request")
    plan_photo.add_argument("--text", required=True)
    plan_photo.add_argument("--record", dest="record", action="store_true", default=True)
    plan_photo.add_argument("--no-record", dest="record", action="store_false")

    review_intimacy = sub.add_parser("review-intimacy-reply")
    review_intimacy.add_argument("--candidate", required=True)
    review_intimacy.add_argument("--attempt-no", type=int, default=1)
    review_intimacy.add_argument("--max-attempts", type=int, default=10)
    review_intimacy.add_argument("--record", dest="record", action="store_true", default=True)
    review_intimacy.add_argument("--no-record", dest="record", action="store_false")

    add = sub.add_parser("add-requirement")
    add.add_argument("--session-id", required=True)
    add.add_argument("--scope", required=True)
    add.add_argument("--requirement-id", default=None)
    add.add_argument("--label", required=True)
    add.add_argument("--text", required=True)
    add.add_argument("--priority", default="medium")

    plan = sub.add_parser("plan")
    plan.add_argument("--session-id", required=True)

    review = sub.add_parser("review-attempt")
    review.add_argument("--session-id", required=True)
    review.add_argument("--candidate-ref", default=None)
    review.add_argument("--source-type", choices=["fresh_generation", "patch", "regenerate", "regenerate_from_previous"], default="fresh_generation")
    review.add_argument("--review-summary", default="")
    review.add_argument("--json", default=None)
    review.add_argument("--json-file", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "bootstrap":
        return cmd_bootstrap(args)
    if args.command == "create-session":
        return cmd_create_session(args)
    if args.command == "classify-requirement":
        return cmd_classify_requirement(args)
    if args.command == "normalize-intimacy-input":
        return cmd_normalize_intimacy_input(args)
    if args.command == "plan-safe-photo-request":
        return cmd_plan_safe_photo_request(args)
    if args.command == "review-intimacy-reply":
        return cmd_review_intimacy_reply(args)
    if args.command == "add-requirement":
        return cmd_add_requirement(args)
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "review-attempt":
        return cmd_review_attempt(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
