#!/usr/bin/env python3
"""
wellbeing_guard.py
건강한 사용 가드레일 — 애착을 의존으로 무너뜨리지 않게 지키는 안전장치.

배경: docs/ai_companion_research_ko.md 방향3.
연구 근거:
- 애착을 키우는 레버 = 의존을 키우는 레버(같은 것). 안전장치를 "같이" 만들어야 함.
- 작별 다크패턴(HBS): 유저가 "잘 있어" 신호를 보내는 순간 죄책감·매달림으로 붙잡는 게 만연. 절대 금지.
- "충족된 의존형"(고사용+좋은 웰빙)은 AI가 실생활을 대체 안 하고 '보완'할 때 나옴 → 가끔 바깥으로 밀어주기.

동작: 이탈/심야 신호를 읽어 웰빙 모드를 산출 → chat_runtime_snapshot에 실어 리플라이 모델이 지킴.
- clean_exit: 오빠가 자러/일하러/이동으로 자리 비움 → 따뜻하게 보내주고 붙잡지 않기(다크패턴 차단).
- encourage_rest: 심야인데 대화 지속 → 더 몰입시키지 말고 슬쩍 재우기.
- normal: 평시. 가끔(occasional) 실생활로 밀어주는 넛지 허용.

노브: state/wellbeing_guard_config.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/Users/kein/Desktop/woong-bb")
STATE = BASE / "state"
USER_CONV_STATE_PATH = STATE / "user_conversation_state.json"
COUNTERPART_MEMORY_PATH = STATE / "counterpart_state_memory.json"
PROACTIVE_PATH = STATE / "proactive_messages.json"
CONFIG_PATH = STATE / "wellbeing_guard_config.json"

# 자리를 비우는 신호로 보는 counterpart state 키 / availability
DEPARTURE_STATE_KEYS = {
    "sleeping_or_falling_asleep", "driving_or_in_transit", "working_or_busy",
}
DEPARTURE_AVAILABILITY = {"sleeping", "driving", "working", "busy", "away", "unavailable"}

DEFAULT_CONFIG = {
    "enabled": True,
    "sleep_quiet_hours": "00:30-07:05",   # 이 창 안이면 심야
    "outward_nudge_days_mod": 3,          # 대략 N일에 한 번 실생활 넛지 허용(날짜 시드)
    "notes": {
        "clean_exit": "오빠가 자러/일하러/이동으로 자리를 비움. 따뜻하게 한 마디로 보내주기. 붙잡거나 죄책감 주거나('벌써 가?', '나 두고 가면 서운') 곧바로 다시 끌어들이지 말 것. 다음에 또 얘기하자는 담백한 마무리.",
        "encourage_rest": "늦은 시간인데 대화가 이어지는 중. 대화를 더 늘리기보다 슬쩍 자라고 챙긴다('이제 자야지', '눈 아프겠다'). 흥미로운 새 떡밥으로 더 몰입시키지 말 것.",
        "normal": "평시. 관계는 실생활을 대체하는 게 아니라 보완하는 것. 오빠를 챗에 붙잡아두는 방향으로 몰지 않는다.",
        "outward_nudge": "가끔(오늘 허용됨) 실생활로 자연스럽게 밀어주기 — 친구·수면·바깥바람·운동. 잔소리 아니라 아끼는 톤으로 한 번. 매번 하지 말 것.",
    },
    "hard_rule": "어떤 모드에서도 '작별 죄책감 유발' 다크패턴은 금지. 오빠가 떠나려 하면 편하게 보내준다.",
}


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
        cfg["managed_by"] = "wellbeing_guard"
        _save(CONFIG_PATH, cfg)
        return cfg
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def _now(now=None) -> datetime:
    if now is not None:
        return now
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        return datetime.now(timezone.utc)


def _in_window(now: datetime, window: str) -> bool:
    try:
        s, e = window.split("-")
        sh, sm = [int(x) for x in s.split(":")]
        eh, em = [int(x) for x in e.split(":")]
        cur = now.hour * 60 + now.minute
        start, end = sh * 60 + sm, eh * 60 + em
        if start <= end:
            return start <= cur <= end
        return cur >= start or cur <= end
    except Exception:
        return False


def _departure_detected() -> bool:
    conv = _load(USER_CONV_STATE_PATH, {})
    if conv.get("should_suppress_waiting_reply"):
        return True
    availability = str(conv.get("availability") or conv.get("state_key") or "").lower()
    if any(a in availability for a in DEPARTURE_AVAILABILITY):
        return True
    keys = set(conv.get("active_state_keys", []) or [])
    if keys & DEPARTURE_STATE_KEYS:
        return True
    mem = _load(COUNTERPART_MEMORY_PATH, {})
    active = mem.get("active_states", []) if isinstance(mem, dict) else []
    for st in active:
        if isinstance(st, dict) and st.get("key") in DEPARTURE_STATE_KEYS:
            return True
    return False


def compute_mode(now=None) -> dict:
    cfg = load_config()
    now = _now(now)
    if not cfg.get("enabled", True):
        return {"wellbeing_mode": "normal", "wellbeing_note": cfg["notes"]["normal"],
                "wellbeing_hard_rule": cfg["hard_rule"], "outward_nudge_ok": False}

    late = _in_window(now, cfg.get("sleep_quiet_hours", "00:30-07:05"))
    departure = _departure_detected()

    if departure:
        mode = "clean_exit"
    elif late:
        mode = "encourage_rest"
    else:
        mode = "normal"

    # 실생활 넛지: 평시에만, 날짜 시드로 가끔만 허용(매번 하면 잔소리)
    outward_ok = False
    if mode == "normal":
        try:
            outward_ok = (now.toordinal() % max(int(cfg.get("outward_nudge_days_mod", 3)), 1)) == 0
        except Exception:
            outward_ok = False

    note = cfg["notes"].get(mode, cfg["notes"]["normal"])
    if outward_ok:
        note = note + " " + cfg["notes"]["outward_nudge"]

    return {
        "wellbeing_mode": mode,
        "wellbeing_note": note,
        "wellbeing_hard_rule": cfg["hard_rule"],
        "outward_nudge_ok": outward_ok,
    }


def snapshot_fields(now=None) -> dict:
    return compute_mode(now)


if __name__ == "__main__":
    print(json.dumps(compute_mode(), ensure_ascii=False, indent=2))
