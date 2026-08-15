#!/usr/bin/env python3
"""
user_persona_tracker.py
오빠(사용자) 페르소나 장기 기억 — "consequential fact store".

배경: docs/ai_companion_research_ko.md 방향1(기억 심화).
연구 근거: 누적 기억이 관계 깊이의 엔진이고(유저는 데이터유출보다 'AI가 날 잊는 것'을 더 무서워함),
          모델은 실제로 장기 사실을 44.4%밖에 기억 못 함. → 대화창 밖 durable store가 현실감 최대 ROI.

기존 문제: state/user_persona_facts.json은 잘 설계됐으나 **아무도 안 읽고 안 씀(dead infra)**.
          한 달 stale. 이 모듈이 (1) recall을 스냅샷에 실어 리플라이 모델이 쓰게 하고,
          (2) upsert API로 capture를 붙일 수 있게 한다.

핵심 설계 (advisor 반영)
- **타입/만료:** 시간에 묶인 사실(stated_plans: "7/7 외근")은 지나면 회수 금지 — 그건 기억이 아니라 44.4% 망각 실패.
  카테고리 기반 기본 타입 + 항목별 expires_at/event_date 오버라이드. recall은 만료된 건 제외.
- **확신도 등급:** high는 단정("오빠 그거 좋아하잖아"), low는 조심스럽게("오빠 수영 다니지 않았어?").
  확신 있게 틀리는 게 잊는 것보다 현실감을 더 깬다.
- **모순=supersede:** 같은 슬롯에 상충 정보 오면 옛것을 stale 처리, append 금지.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/Users/kein/Desktop/woong-bb")
STATE = BASE / "state"
FACTS_PATH = STATE / "user_persona_facts.json"

# 카테고리 → 기본 타입. 시간에 묶인 카테고리는 만료 체크 대상.
TIME_BOUND_CATEGORIES = {"stated_plans"}
# recall 대상(durable) 카테고리와 그 표면 라벨
DURABLE_SOURCES = [
    ("preferences", "취향"),
    ("current_concerns_or_goals", "요즘 관심/고민"),
    ("past_shared_memories_with_woongbbi", "둘의 추억"),
    ("verbal_quirks_user_uses", "말버릇"),
    ("people_around_user", "주변 사람"),
    ("stated_plans", "예정/계획"),  # 미래 계획은 회수, 지난 계획은 expiry로 자동 제외
]
_CONF_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_DATE_RE = re.compile(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})")


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(p: Path, d) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_facts() -> dict:
    return _load(FACTS_PATH, {})


def _now(now=None) -> datetime:
    if now is not None:
        return now
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        return datetime.now(timezone.utc)


def _parse_date(s):
    if not s or not isinstance(s, str):
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


def _item_expired(item: dict, category: str, now: datetime) -> bool:
    """시간에 묶인 사실이 지났는지. stated_plans 등은 value/expires_at의 날짜로 판단."""
    # 명시 오버라이드 우선
    exp = item.get("expires_at") or item.get("event_date")
    d = _parse_date(exp) if exp else None
    if d is None and (item.get("type") == "time_bound_event" or category in TIME_BOUND_CATEGORIES):
        # value 앞부분의 날짜(예: "2026-07-07 오전 11시…")를 이벤트 날짜로 봄
        d = _parse_date(item.get("value", ""))
    if d is None:
        return False
    # 이벤트 날짜의 '다음 날'부터 만료(당일까지는 유효)
    return d.date() < now.replace(tzinfo=None).date()


def _iter_pref_items(prefs: dict):
    """preferences는 {food:[...], hobbies:[...]} 중첩 구조. (subkey, item) 평탄화."""
    for sub, items in (prefs or {}).items():
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("value"):
                    yield sub, it


def _assertiveness(conf: str) -> str:
    return "assertive" if conf == "high" else ("tentative" if conf == "low" else "soft")


def build_recall(now=None, max_items: int = 4) -> list:
    """durable 사실을 회수 후보로. 만료된 시간묶임 사실은 제외. 확신도·최근성·미사용 우선 랭킹."""
    now = _now(now)
    facts = load_facts()
    items = facts.get("items", {})
    pool = []

    for cat, label in DURABLE_SOURCES:
        node = items.get(cat)
        if cat == "preferences" and isinstance(node, dict):
            for sub, it in _iter_pref_items(node):
                if it.get("stale") or _item_expired(it, cat, now):
                    continue
                pool.append((f"{label}:{sub}", it))
        elif isinstance(node, list):
            for it in node:
                if (isinstance(it, dict) and it.get("value") and not it.get("stale")
                        and not _item_expired(it, cat, now)):
                    pool.append((label, it))

    def rank(entry):
        _, it = entry
        conf = _CONF_WEIGHT.get(str(it.get("confidence", "medium")), 2)
        used = int(it.get("use_count", 0) or 0)
        captured = _parse_date(it.get("captured_at", "")) or datetime(2000, 1, 1)
        # 확신도 높고, 덜 회수됐고, 최근에 알게 된 것 우선
        return (-conf, used, -(captured.timestamp()))

    pool.sort(key=rank)
    out = []
    for label, it in pool[:max_items]:
        conf = str(it.get("confidence", "medium"))
        out.append({
            "value": it.get("value"),
            "category": label,
            "confidence": conf,
            "assertiveness": _assertiveness(conf),
            "use_count": int(it.get("use_count", 0) or 0),
        })
    return out


def build_curiosity(max_items: int = 3) -> list:
    """아직 모르는 것 / 파생 궁금증에서 '가끔 물어볼' 후보. 캐던스(빈도)는 리플라이 모델이 조절."""
    facts = load_facts()
    out = []
    checklist = facts.get("curiosity_checklist", {})
    for key, node in checklist.items():
        if key.startswith("_"):
            continue
        if isinstance(node, dict) and node.get("known") is False:
            hint = node.get("question_hint")
            if hint:
                out.append({"category": key, "ask_hint": hint})
    # 파생 궁금증(아직 안 물어본 것)
    for it in (facts.get("derived_curiosity", {}).get("items", []) or []):
        if isinstance(it, dict) and not it.get("asked") and it.get("question"):
            out.append({"category": it.get("from_category"), "ask_hint": it.get("question")})
    return out[:max_items]


def snapshot_fields(now=None) -> dict:
    """chat_runtime_snapshot에 병합. 리플라이 모델이 durable 기억을 회수/궁금해하게 하는 재료."""
    return {
        "user_persona_recall": build_recall(now),
        "user_persona_curiosity": build_curiosity(),
        "user_persona_recall_rule": (
            "durable 사실은 한 답변에 0~1개만, 장면 흐름에 녹여 자연스럽게 회수(정보 나열 금지). "
            "confidence=high는 단정('오빠 그거 좋아하잖아'), low는 조심스럽게('오빠 그거 하지 않았어?'). "
            "만료·지난 계획은 회수 금지."
        ),
        "user_persona_curiosity_rule": (
            "모르는 건 매 답변이 아니라 4~5번에 한 번, 맥락 자연스러울 때 하나씩. 오빠가 힘들거나 바쁘면 캐묻지 말 것."
        ),
    }


# ---- capture API (증분2에서 워커가 호출) ----

def _ensure_list(items: dict, category: str) -> list:
    node = items.setdefault(category, [])
    if not isinstance(node, list):
        node = items[category] = []
    return node


def upsert(category: str, value: str, source_excerpt: str = "", confidence: str = "medium",
           subkey: str = None, fact_type: str = None, expires_at: str = None,
           supersede_contains: str = None, now=None) -> dict:
    """durable 사실 추가/갱신. 모순되면 옛것 supersede(stale 처리) 후 새로 기록.
    preferences처럼 중첩이면 subkey 지정(food/hobbies/...)."""
    now = _now(now)
    facts = load_facts()
    items = facts.setdefault("items", {})

    # 대상 리스트 선택
    if category == "preferences":
        prefs = items.setdefault("preferences", {})
        if not isinstance(prefs, dict):
            prefs = items["preferences"] = {}
        target = prefs.setdefault(subkey or "misc", [])
        if not isinstance(target, list):
            target = prefs[subkey or "misc"] = []
    else:
        target = _ensure_list(items, category)

    # supersede: 같은 슬롯의 상충 항목을 stale 처리
    if supersede_contains:
        for it in target:
            if isinstance(it, dict) and supersede_contains in str(it.get("value", "")):
                it["stale"] = True
                it["superseded_at"] = now.isoformat(timespec="seconds")

    new_item = {
        "value": value,
        "source_excerpt": source_excerpt,
        "captured_at": now.isoformat(timespec="seconds"),
        "confidence": confidence,
        "use_count": 0,
    }
    if fact_type:
        new_item["type"] = fact_type
    if expires_at:
        new_item["expires_at"] = expires_at
    # 활성 항목만 남기고(중복 value 제거) append
    target[:] = [it for it in target if not (isinstance(it, dict) and it.get("value") == value)]
    target.append(new_item)
    facts["last_updated_at"] = now.isoformat(timespec="seconds")
    _save(FACTS_PATH, facts)
    return new_item


def main():
    ap = argparse.ArgumentParser(description="오빠 페르소나 장기 기억 트래커")
    sub = ap.add_subparsers(dest="cmd")

    ap_recall = sub.add_parser("recall", help="회수 후보 출력")
    ap_recall.add_argument("--max", type=int, default=4)

    sub.add_parser("snapshot", help="스냅샷 병합 필드 출력")

    ap_up = sub.add_parser("upsert", help="durable 사실 추가/갱신")
    ap_up.add_argument("--category", required=True, help="preferences|current_concerns_or_goals|past_shared_memories_with_woongbbi|verbal_quirks_user_uses|people_around_user|sensitive_topics_to_avoid|stated_plans")
    ap_up.add_argument("--value", required=True)
    ap_up.add_argument("--source", default="")
    ap_up.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    ap_up.add_argument("--subkey", default=None, help="preferences일 때 food/drink/hobbies/...")
    ap_up.add_argument("--type", dest="fact_type", default=None, choices=["stable_preference", "time_bound_event", "commitment", "relational"])
    ap_up.add_argument("--expires-at", dest="expires_at", default=None, help="YYYY-MM-DD (time_bound면 권장)")
    ap_up.add_argument("--supersede-contains", dest="supersede_contains", default=None)

    args = ap.parse_args()
    if args.cmd == "recall":
        print(json.dumps(build_recall(max_items=args.max), ensure_ascii=False, indent=2))
    elif args.cmd == "snapshot":
        print(json.dumps(snapshot_fields(), ensure_ascii=False, indent=2))
    elif args.cmd == "upsert":
        item = upsert(args.category, args.value, args.source, args.confidence,
                      subkey=args.subkey, fact_type=args.fact_type,
                      expires_at=args.expires_at, supersede_contains=args.supersede_contains)
        print(json.dumps({"upserted": item}, ensure_ascii=False, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
