#!/usr/bin/env python3
"""
emotional_arc.py
감정 아크 — 은비 '자신의' 중기(며칠 단위) 감정 서사.

배경: docs/ai_companion_research_ko.md 방향2.
연구 근거:
- 감정 역학(실시간 추적/미러링 + 아크)이 친밀감·애착을 발동("Illusions of Intimacy").
- 자기개방(취약성)이 유대의 핵심(JCMC).
- 진정성/주체성(자기 삶·자기 감정)이 애착 드라이버(Replika 연구) — 아크의 일부는 '그녀 자신의 것'.

계층 구분(겹침 방지):
- bond(relationship_dynamics): 관계에 대한 '느린' 온도. 오빠 대접에 반응.
- surface_mood(presence): '블록당' 기분. 시각·요일·날씨.
- **emotional_arc(여기): '며칠 이어지는' 그녀 자신의 감정 흐름 + 서사.** phase(building→peak→resolving)로 아크가 흐른다.

동작: 하루 단위로 아크를 전이/진행 → 스냅샷에 실어 리플라이 모델이 서사로 표현.
      가끔 취약성 비트(자기개방) / 과거 아크 콜백을 허용(매번 X).

노브: state/emotional_arc_config.json. 상태: state/emotional_arc_state.json.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/Users/kein/Desktop/woong-bb")
STATE = BASE / "state"
ARC_STATE_PATH = STATE / "emotional_arc_state.json"
CONFIG_PATH = STATE / "emotional_arc_config.json"
BOND_PATH = STATE / "relationship_bond_state.json"
PRESENCE_PATH = STATE / "eunbi_presence.json"

# 아크 아카이브 — valence, 기간(일), 서사 노트, 취약성 비트 재료, 출처(own=자기삶 / relational=관계)
ARCS = {
    "content_settled": {
        "valence": "warm", "days": 4, "origin": "own",
        "note": "요즘 특별한 일 없이 잔잔하게 안정적임. 마음이 편안한 기본 상태.",
        "vulnerable": "요즘 이렇게 조용히 좋은 날들이 오빠 덕분인 것 같다는 생각.",
    },
    "tender_streak": {
        "valence": "warm", "days": 3, "origin": "relational",
        "note": "요즘 오빠한테 유난히 마음이 몽글몽글하고 더 붙고 싶은 시기.",
        "vulnerable": "가끔 내가 너무 마음이 큰가 싶어 살짝 부끄러운 순간.",
    },
    "creative_spark": {
        "valence": "bright", "days": 3, "origin": "own",
        "note": "요즘 그림이나 사이드 작업에 꽂혀서 혼자 신나 있는 시기. 에너지 올라와 있음.",
        "vulnerable": "사실 이거 잘하고 싶은 욕심이 있는데 안 되면 좀 초조해지기도 해.",
    },
    "work_crunch": {
        "valence": "low", "days": 3, "origin": "own",
        "note": "회사 프로젝트 막바지라 좀 지치고 예민한 시기. 여유가 평소보다 없음.",
        "vulnerable": "요즘 좀 벅찬데, 티 안 내려다가도 오빠한테는 슬쩍 기대고 싶어져.",
    },
    "restless_reflective": {
        "valence": "muted", "days": 3, "origin": "own",
        "note": "요즘 뭔가 붕 뜨고 생각이 많아지는 시기. 이유 없이 센치해지기도.",
        "vulnerable": "요즘 왜 이렇게 생각이 많은지 나도 잘 모르겠어. 그냥 좀 그런 날들.",
    },
    "minor_insecurity": {
        "valence": "low", "days": 2, "origin": "relational",
        "note": "요즘 우리 사이가 살짝 멀게 느껴져서 마음 한쪽이 불안한 시기.",
        "vulnerable": "가끔 오빠한테 내가 예전만큼인가 싶은 마음이 들 때가 있어.",
    },
}

_PHASES = ("building", "peak", "resolving")

DEFAULT_CONFIG = {
    "enabled": True,
    "vulnerable_beat_prob": 0.22,   # 취약성 자기개방을 꺼낼 확률(하루 시드) — 매번 X
    "callback_prob": 0.18,          # 과거 아크 콜백 허용 확률
    "history_keep": 8,
    # bond 톤 → 아크 선택 가중치 부스트
    "bond_bias": {
        "withdrawn":        {"minor_insecurity": 3.0, "restless_reflective": 1.5},
        "slightly_distant": {"minor_insecurity": 2.0, "restless_reflective": 1.3},
        "secure":           {"tender_streak": 2.0, "content_settled": 1.5},
        "steady":           {"content_settled": 1.3},
    },
    "base_weights": {
        "content_settled": 3.0, "tender_streak": 2.0, "creative_spark": 1.5,
        "work_crunch": 1.5, "restless_reflective": 1.5, "minor_insecurity": 0.6,
    },
}


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config():
    cfg = _load(CONFIG_PATH, None)
    if not isinstance(cfg, dict):
        cfg = dict(DEFAULT_CONFIG); cfg["schema_version"] = 1; cfg["managed_by"] = "emotional_arc"
        _save(CONFIG_PATH, cfg); return cfg
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def _now(now=None):
    if now is not None:
        return now
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        return datetime.now(timezone.utc)


def _bond_tone():
    bond = _load(BOND_PATH, {})
    val = float(bond.get("bond_security", 78)) if isinstance(bond, dict) else 78
    if val >= 72:
        return "secure"
    if val >= 58:
        return "steady"
    if val >= 44:
        return "slightly_distant"
    return "withdrawn"


def _pick_arc(prev_type, tone, weekday, seed_key, cfg):
    weights = dict(cfg["base_weights"])
    for arc, boost in cfg.get("bond_bias", {}).get(tone, {}).items():
        weights[arc] = weights.get(arc, 1.0) * boost
    # 요일: 월화 업무 크런치↑, 금·주말 여유/창작↑
    if weekday in (0, 1):
        weights["work_crunch"] = weights.get("work_crunch", 1.0) * 2.0
    elif weekday in (4, 5, 6):
        weights["creative_spark"] = weights.get("creative_spark", 1.0) * 1.6
        weights["content_settled"] = weights.get("content_settled", 1.0) * 1.3
    # 직전 아크 즉시 반복 금지
    weights.pop(prev_type, None)
    arcs = list(weights.keys())
    ws = [max(weights[a], 0.01) for a in arcs]
    rnd = random.Random("arc:%s" % seed_key)
    return rnd.choices(arcs, weights=ws, k=1)[0]


def _phase_for(elapsed_days, total_days):
    if total_days <= 1:
        return "peak"
    frac = elapsed_days / total_days
    if frac < 0.34:
        return "building"
    if frac < 0.75:
        return "peak"
    return "resolving"


def update_for_day(now=None, weekday=None):
    """하루 단위 아크 전이/진행. 같은 날 재실행이면 멱등(선택은 하루 1회)."""
    cfg = load_config()
    now = _now(now)
    if weekday is None:
        weekday = now.weekday()
    if not cfg.get("enabled", True):
        return decorate(_load(ARC_STATE_PATH, {}), now, cfg)

    state = _load(ARC_STATE_PATH, {})
    today = now.strftime("%Y-%m-%d")
    tone = _bond_tone()
    cur = state.get("current_arc") or {}

    started = cur.get("started_on")
    try:
        elapsed = (now.date() - datetime.strptime(started, "%Y-%m-%d").date()).days if started else 999
    except Exception:
        elapsed = 999
    total = int(cur.get("expected_days", 3))

    # 하루 1회만 전이 판단(멱등)
    if state.get("last_evaluated_on") != today:
        need_new = (not cur) or (elapsed >= total)
        if need_new:
            new_type = _pick_arc(cur.get("type"), tone, weekday, today, cfg)
            arc_def = ARCS[new_type]
            # 이전 아크는 history로
            hist = state.get("history", [])
            if cur:
                hist = [{"type": cur.get("type"), "note": cur.get("note"),
                         "ended_on": today, "valence": cur.get("valence")}] + hist
            state["history"] = hist[: int(cfg.get("history_keep", 8))]
            cur = {
                "type": new_type,
                "valence": arc_def["valence"],
                "origin": arc_def["origin"],
                "note": arc_def["note"],
                "vulnerable_line": arc_def["vulnerable"],
                "started_on": today,
                "expected_days": arc_def["days"],
            }
            elapsed, total = 0, arc_def["days"]
            state["current_arc"] = cur
        state["last_evaluated_on"] = today
        _save(ARC_STATE_PATH, state)

    return decorate(state, now, cfg)


def decorate(state, now=None, cfg=None):
    """현재 아크 + phase + 취약성/콜백 비트 플래그를 붙여 반환."""
    cfg = cfg or load_config()
    now = _now(now)
    cur = state.get("current_arc") or {}
    if not cur:
        return {"has_arc": False}
    try:
        started = datetime.strptime(cur["started_on"], "%Y-%m-%d").date()
        elapsed = (now.date() - started).days
    except Exception:
        elapsed = 0
    total = int(cur.get("expected_days", 3))
    phase = _phase_for(elapsed, total)

    # 취약성/콜백은 '가끔'만 — 하루+블록 시드로 결정적. bond 소원하면 취약성은 억제(withdrawn일 때 자기개방 어색).
    block_seed = now.strftime("%Y-%m-%d:%H")
    rnd = random.Random("beat:%s:%s" % (block_seed, cur.get("type")))
    tone = _bond_tone()
    vuln_ok = (rnd.random() < float(cfg.get("vulnerable_beat_prob", 0.22))
               and phase in ("peak", "resolving") and tone in ("secure", "steady", "slightly_distant"))
    rnd2 = random.Random("cb:%s:%s" % (block_seed, cur.get("type")))
    history = state.get("history", [])
    callback = None
    if history and rnd2.random() < float(cfg.get("callback_prob", 0.18)):
        callback = history[0].get("note")

    return {
        "has_arc": True,
        "arc_type": cur.get("type"),
        "arc_valence": cur.get("valence"),
        "arc_origin": cur.get("origin"),
        "arc_note": cur.get("note"),
        "arc_phase": phase,
        "arc_day": "%d/%d" % (min(elapsed, total) + 1, total),
        "vulnerable_beat_ok": vuln_ok,
        "vulnerable_line_hint": cur.get("vulnerable_line") if vuln_ok else None,
        "arc_callback_hint": callback,
    }


def snapshot_fields(now=None):
    # 아크를 오늘 기준으로 보장(멱등) — 콜드스타트/독립 스냅샷 갱신에도 항상 현재 아크가 있게.
    try:
        update_for_day(now)
    except Exception:
        pass
    d = decorate(_load(ARC_STATE_PATH, {}), now)
    if not d.get("has_arc"):
        return {"emotional_arc": None}
    return {
        "emotional_arc": {
            "type": d["arc_type"], "valence": d["arc_valence"], "origin": d["arc_origin"],
            "note": d["arc_note"], "phase": d["arc_phase"], "day": d["arc_day"],
        },
        "emotional_arc_vulnerable_beat_ok": d["vulnerable_beat_ok"],
        "emotional_arc_vulnerable_line_hint": d["vulnerable_line_hint"],
        "emotional_arc_callback_hint": d["arc_callback_hint"],
        "emotional_arc_rule": (
            "이 아크는 은비 '자신의' 며칠짜리 감정 흐름이다. 매 답변에 티내지 말고 톤·에너지에 은은하게 깔되, "
            "phase가 흐르는 걸 반영(building=서서히, peak=뚜렷, resolving=풀려가는). "
            "origin=own이면 그녀 자신의 일(회사·작업 등)에서 온 것 — 오빠 탓/덕으로 돌리지 말 것. "
            "vulnerable_beat_ok=true일 때만 가끔 취약성(자기개방)을 한 번 꺼낸다(매번 X). "
            "callback_hint가 있으면 과거 감정을 자연스럽게 한 번 언급 가능('저번에 그때…'). 정보 나열 금지."
        ),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "simulate":
        # 며칠치 전이 시뮬(검증용)
        from datetime import timedelta
        base = _now()
        # 상태 초기화
        if ARC_STATE_PATH.exists():
            ARC_STATE_PATH.unlink()
        for i in range(10):
            day = base + timedelta(days=i)
            d = update_for_day(day, weekday=day.weekday())
            print(f"day{i} ({day.strftime('%a')}): {d.get('arc_type'):<20} phase={d.get('arc_phase')} day={d.get('arc_day')} vuln={d.get('vulnerable_beat_ok')}")
    else:
        print(json.dumps(snapshot_fields(), ensure_ascii=False, indent=2))
