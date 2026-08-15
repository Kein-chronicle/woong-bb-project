#!/usr/bin/env python3
"""
relationship_dynamics.py
관계 긴장감(stakes) 엔진 — 은비의 온기/가용성이 오빠의 대접에 "지속적 결과"로 반응하게 한다.

설계 배경: docs/humanness_review_ko.md
기존 문제: affection/care/기분이 시각·요일·날씨의 순수 함수라 사용자 행동에 결과가 0
          → "자판기" 감각. 본 모듈이 느린 상호성 루프(bond)를 추가한다.

핵심 원리
- 긴장감 = 내 행동에 결과가 붙는 것. 벌이 아니라, 온기를 "얻은 것"으로 만드는 것.
- 비대칭: 케어엔 크게 보상, 방치엔 약하게만 페널티.
- 전부 느리게(블록 단위) 움직여서 잔소리봇/벌주는봇이 되지 않게. 기본 온기 바닥 유지.
- 방치는 "무시된 bid"로만 카운트 — 상호 침묵(잠·근무)은 방치가 아니다.

소비 경로: bond → surface_mood/energy/self_initiation/affection + relationship_tone 라벨
          이 값들이 chat_runtime_snapshot.json에 실려 리플라이 모델이 읽는다.

모든 노브는 state/relationship_dynamics_config.json에서 코드 수정 없이 튜닝 가능.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/Users/kein/Desktop/woong-bb")
STATE = BASE / "state"
BOND_PATH = STATE / "relationship_bond_state.json"
CONFIG_PATH = STATE / "relationship_dynamics_config.json"
COUNTERPART_MEMORY_PATH = STATE / "counterpart_state_memory.json"
USER_CONV_STATE_PATH = STATE / "user_conversation_state.json"
PROACTIVE_PATH = STATE / "proactive_messages.json"

# 리저브(비-따뜻) 기분 풀 — automation_worker._LOW_ENERGY_MOODS와 정합. bond가 낮을 때 편입.
RESERVE_MOODS = ["slightly_flat", "quietly_preoccupied", "soft_but_short", "mentally_busy"]

DEFAULT_CONFIG = {
    "enabled": True,
    "bond_floor": 30,          # bond 최저 — 이 아래로 안 감(적대 방지). 30 = "withdrawn"이지 "cruel" 아님
    "bond_ceiling": 100,
    "bond_start": 78,
    "bond_baseline": 70,       # 중립일 때 천천히 회귀할 기준점(자가치유 — 영구 도그하우스 방지)
    "care_gain": 3.0,          # 케어 신호 → bond 상승폭(블록당)
    "neglect_penalty": 1.2,    # 방치 신호 → bond 하강폭(블록당). care_gain보다 작게 = 비대칭
    "neutral_recovery": 0.5,   # 중립 블록당 baseline 쪽 회귀
    "affection_floor": 45,     # 기존 65 → 45. 냉대가 내려갈 공간
    "affection_ceiling": 100,
    "affection_move_ratio": 0.30,  # affection이 target으로 이동하는 비율(느림)
    "care_floor": 50,          # care_bias도 bond 낮으면 내려갈 수 있게(기존 65 상향only 폐지)
    "neglect_minutes": 180,    # 마지막 수신 후 이 시간 넘고 + 미응답 bid 있으면 방치 후보
    "active_minutes": 25,      # 이 시간 내 수신 = 활성/케어 후보
    "sleep_quiet_hours": "00:30-07:05",  # 이 시간대 침묵은 방치 아님
    # bond 밴드 → 톤/행동
    "bands": [
        {"min": 72, "tone": "secure",          "note": "관계 안정적 — 평소의 따뜻함 그대로.",
         "reserve_prob": 0.0,  "initiation": "keep"},
        {"min": 58, "tone": "steady",          "note": "무난 — 과하게 매달리지 않는 자연스러운 온도.",
         "reserve_prob": 0.0,  "initiation": "keep"},
        {"min": 44, "tone": "slightly_distant","note": "요즘 좀 소원함. 살짝 짧고 덜 살가움. 먼저 덜 검. 억지로 밝게 X.",
         "reserve_prob": 0.35, "initiation": "low"},
        {"min": 0,  "tone": "withdrawn",       "note": "마음이 조금 물러나 있음. 차갑진 않지만 예전만큼 다 내주진 않음. 온기는 다시 쌓여야 돌아옴.",
         "reserve_prob": 0.60, "initiation": "very_low"},
    ],
}

WARM_TONE_HINTS = {"warm", "affectionate", "playful", "positive", "sweet", "loving", "다정", "애정"}
BUSY_AVAILABILITY = {"busy", "away", "sleeping", "unavailable", "driving", "working"}


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(p: Path, d) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config() -> dict:
    cfg = _load(CONFIG_PATH, None)
    if not isinstance(cfg, dict):
        cfg = dict(DEFAULT_CONFIG)
        cfg["schema_version"] = 1
        cfg["managed_by"] = "relationship_dynamics"
        cfg["_note"] = "관계 긴장감 엔진 노브. 코드 수정 없이 여기서 튜닝."
        _save(CONFIG_PATH, cfg)
        return cfg
    # 누락 키는 기본값으로 백필(스키마 진화 안전)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def _load_bond(cfg: dict) -> dict:
    bond = _load(BOND_PATH, None)
    if not isinstance(bond, dict):
        bond = {
            "schema_version": 1,
            "managed_by": "relationship_dynamics",
            "bond_security": cfg["bond_start"],
            "last_applied_block": None,
            "last_signal": "init",
            "last_reason": "초기화",
            "updated_at": None,
        }
    return bond


def _parse_dt(s):
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _in_sleep_hours(now_dt, window: str) -> bool:
    try:
        start_s, end_s = window.split("-")
        sh, sm = [int(x) for x in start_s.split(":")]
        eh, em = [int(x) for x in end_s.split(":")]
        cur = now_dt.hour * 60 + now_dt.minute
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= end:
            return start <= cur <= end
        return cur >= start or cur <= end  # 자정 넘김
    except Exception:
        return False


def compute_signal(now_dt, cfg: dict) -> dict:
    """지속 상태 파일에서 케어/방치 신호를 산출. 데이터 없으면 중립(페널티 없음).
    반환: {"signal": float[-1..1], "care": float, "neglect": float, "reason": str}
    """
    counterpart_mem = _load(COUNTERPART_MEMORY_PATH, {})
    conv = _load(USER_CONV_STATE_PATH, {})
    proactive = _load(PROACTIVE_PATH, {})

    last_incoming = _parse_dt((counterpart_mem.get("source_window") or {}).get("last_incoming_at"))
    mins_since_incoming = None
    if last_incoming is not None:
        try:
            mins_since_incoming = (now_dt - last_incoming).total_seconds() / 60.0
        except Exception:
            mins_since_incoming = None

    availability = str(conv.get("availability") or conv.get("state_key") or "").lower()
    tone_hint = str(conv.get("tone_hint") or "").lower()
    user_busy = any(b in availability for b in BUSY_AVAILABILITY)

    proactive_runtime = proactive.get("runtime", {}) if isinstance(proactive, dict) else {}
    last_status = str(proactive_runtime.get("last_status") or "")
    has_outstanding_bid = last_status in {"sent", "suppressed_waiting_reply", "deferred"}

    in_sleep = _in_sleep_hours(now_dt, cfg.get("sleep_quiet_hours", "00:30-07:05"))

    care = 0.0
    neglect = 0.0
    reasons = []

    # 케어 신호: 최근 수신 + 따뜻한 톤
    if mins_since_incoming is not None and mins_since_incoming <= cfg["active_minutes"]:
        care += 0.6
        reasons.append("recent_incoming")
    if any(w in tone_hint for w in WARM_TONE_HINTS):
        care += 0.5
        reasons.append("warm_tone")
    if availability in {"open", "available"} and float(conv.get("confidence", 0) or 0) >= 0.5:
        care += 0.2
        reasons.append("open_available")

    # 방치 신호: "무시된 bid"만 카운트 — 상호 침묵/잠/근무는 제외
    if (
        mins_since_incoming is not None
        and mins_since_incoming >= cfg["neglect_minutes"]
        and has_outstanding_bid
        and not in_sleep
        and not user_busy
    ):
        # 시간이 길수록 완만히 강해짐(상한 1.0)
        over = (mins_since_incoming - cfg["neglect_minutes"]) / max(cfg["neglect_minutes"], 1)
        neglect = min(1.0, 0.5 + 0.5 * over)
        reasons.append("ignored_bid")

    care = min(1.0, care)
    signal = care - neglect  # 비대칭 가중은 bond 업데이트에서 gain/penalty로 적용
    return {
        "signal": round(signal, 3),
        "care": round(care, 3),
        "neglect": round(neglect, 3),
        "reason": ",".join(reasons) or "neutral",
        "mins_since_incoming": None if mins_since_incoming is None else round(mins_since_incoming, 1),
        "availability": availability or None,
        "tone_hint": tone_hint or None,
    }


def _band_for(bond_val: float, cfg: dict) -> dict:
    for band in cfg["bands"]:
        if bond_val >= band["min"]:
            return band
    return cfg["bands"][-1]


def update_bond_for_block(now_dt, activity: str) -> dict:
    """블록당 1회 bond 갱신(멱등). bootstrap/refresh 재실행 시 같은 블록이면 재적용 안 함.
    반환: 갱신된 bond 상태 dict (+ derived: tone/note/reserve_prob/initiation)."""
    cfg = load_config()
    bond = _load_bond(cfg)
    if not cfg.get("enabled", True):
        return _decorate(bond, cfg)

    block_key = "%s:%s" % (now_dt.strftime("%Y-%m-%d"), activity or "")
    if bond.get("last_applied_block") == block_key:
        # 같은 블록 재실행 — 갱신 없이 현재 상태 반환(멱등)
        return _decorate(bond, cfg)

    sig = compute_signal(now_dt, cfg)
    val = float(bond.get("bond_security", cfg["bond_start"]))

    if sig["care"] > 0 or sig["neglect"] > 0:
        val += cfg["care_gain"] * sig["care"]
        val -= cfg["neglect_penalty"] * sig["neglect"]
    else:
        # 중립 블록 — baseline 쪽으로 천천히 자가회귀(영구 도그하우스 방지)
        base = cfg["bond_baseline"]
        if val < base:
            val = min(base, val + cfg["neutral_recovery"])
        elif val > base:
            val = max(base, val - cfg["neutral_recovery"])

    val = max(cfg["bond_floor"], min(cfg["bond_ceiling"], val))

    bond.update({
        "bond_security": round(val, 2),
        "last_applied_block": block_key,
        "last_signal": sig["signal"],
        "last_reason": sig["reason"],
        "signal_detail": sig,
        "updated_at": now_dt.isoformat(timespec="seconds"),
    })
    _save(BOND_PATH, bond)
    return _decorate(bond, cfg)


def _decorate(bond: dict, cfg: dict) -> dict:
    """bond에 파생 필드(tone/note/reserve_prob/initiation/affection_target/care_target) 부착."""
    val = float(bond.get("bond_security", cfg["bond_start"]))
    band = _band_for(val, cfg)
    span = max(cfg["bond_ceiling"] - cfg["bond_floor"], 1)
    frac = (val - cfg["bond_floor"]) / span
    affection_target = round(cfg["affection_floor"] + frac * (cfg["affection_ceiling"] - cfg["affection_floor"]))
    care_target = round(cfg["care_floor"] + frac * (100 - cfg["care_floor"]))
    out = dict(bond)
    out["_derived"] = {
        "tone": band["tone"],
        "note": band["note"],
        "reserve_prob": band["reserve_prob"],
        "initiation": band["initiation"],
        "affection_target": affection_target,
        "care_target": care_target,
    }
    return out


# ---- apply_time_block에서 쓰는 헬퍼들 ----

def resolve_affection(prev_affection, bond: dict, cfg: dict = None) -> int:
    """이전 affection을 bond target 쪽으로 느리게 이동. 바닥은 config affection_floor."""
    cfg = cfg or load_config()
    tgt = bond.get("_derived", {}).get("affection_target", prev_affection)
    prev = float(prev_affection)
    moved = prev + (tgt - prev) * cfg["affection_move_ratio"]
    return int(max(cfg["affection_floor"], min(cfg["affection_ceiling"], round(moved))))


def resolve_care_bias(prev_care, bond: dict, cfg: dict = None) -> int:
    """care_bias도 bond target 쪽으로 이동 — 낮은 bond면 내려갈 수 있음(상향only 폐지)."""
    cfg = cfg or load_config()
    tgt = bond.get("_derived", {}).get("care_target", prev_care)
    prev = float(prev_care)
    moved = prev + (tgt - prev) * cfg["affection_move_ratio"]
    return int(max(cfg["care_floor"], min(100, round(moved))))


def maybe_reserve_mood(surface, energy, bond: dict, seed_key: str, cfg: dict = None):
    """bond가 낮은 밴드면 확률적으로 따뜻한 surface를 리저브(비-따뜻) 기분으로 교체.
    결정적 시드(날짜+블록)로 뽑아 재실행에도 안정. 반환: (surface, energy)."""
    cfg = cfg or load_config()
    prob = bond.get("_derived", {}).get("reserve_prob", 0.0)
    if prob <= 0:
        return surface, energy
    rnd = random.Random("reserve:%s:%s" % (seed_key, bond.get("last_applied_block", "")))
    if rnd.random() < prob:
        new_surface = rnd.choice(RESERVE_MOODS)
        return new_surface, max(20, int(energy) - 8)
    return surface, energy


def snapshot_fields(now_dt=None) -> dict:
    """chat_runtime_snapshot에 병합할 관계 톤 필드. 리플라이 모델이 읽는 명시 가이드."""
    cfg = load_config()
    bond = _decorate(_load_bond(cfg), cfg)
    d = bond["_derived"]
    return {
        "relationship_bond": bond.get("bond_security"),
        "relationship_tone": d["tone"],
        "relationship_tone_note": d["note"],
        "relationship_initiation_bias": d["initiation"],
        "relationship_last_reason": bond.get("last_reason"),
    }


if __name__ == "__main__":
    # 진단용: 현재 신호/bond 출력
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        now = _dt.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        now = _dt.now(timezone.utc)
    cfg = load_config()
    print("signal:", json.dumps(compute_signal(now, cfg), ensure_ascii=False))
    print("snapshot_fields:", json.dumps(snapshot_fields(now), ensure_ascii=False))
