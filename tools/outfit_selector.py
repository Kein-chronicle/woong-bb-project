#!/usr/bin/env python3
"""
outfit_selector.py
의상 하이브리드 선택기 — 갈아입는 순간(outfit_context 전환)에 1회 호출.

방식(③ 하이브리드):
- silhouette: 카테고리 풀에서 anti-repeat 로테이션(최근 사용 제외)으로 통제.
- 색/디테일: color_pool/detail_pool에서 랜덤 레이어 → 같은 실루엣도 매번 다르게.
- 노출: activity(상황)별 exposure cap으로 게이팅 — 통근/회사=커버·moderate, 집/저녁/잠/샤워후=high.
- 선택 결과는 다음 갈아입기 전까지 유지(재선택은 전환 때만; apply_time_block이 제어).

데이터: state/outfit_wardrobe.json  |  로테이션 상태: state/outfit_rotation_state.json
"""
from __future__ import annotations

import json
import random
from pathlib import Path

BASE = Path("/Users/kein/Desktop/woong-bb")
STATE = BASE / "state"
WARDROBE_PATH = STATE / "outfit_wardrobe.json"
ROTATION_PATH = STATE / "outfit_rotation_state.json"

# 상황(activity)별 노출 상한. 낮/회사도 완전 커버가 아니라 노출 있게(사용자 요청) → high 허용,
# 실제 렌더 수위는 워커 content_level(통근=2 / 낮·회사=2.5 / 사적=3)이 정밀 게이팅.
# 통근(대중교통 공개)만 moderate로 조금 눌러둠.
_COVERED_ACTIVITIES: set = set()
_MODERATE_ACTIVITIES = {"morning_commute", "evening_commute"}


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_category(outfit_context: str, wardrobe: dict) -> str | None:
    for cat, spec in wardrobe.get("categories", {}).items():
        if outfit_context in spec.get("maps_from", []):
            return cat
    return None


def resolve_exposure_cap(activity: str) -> str:
    if activity in _COVERED_ACTIVITIES:
        return "covered"
    if activity in _MODERATE_ACTIVITIES:
        return "moderate"
    return "high"


def _rank(tier: str, wardrobe: dict) -> int:
    return wardrobe.get("exposure_tier_rank", {}).get(tier, 0)


def pick_variation(category: str, exposure_cap: str, seed_key: str, wardrobe: dict, rotation: dict) -> dict | None:
    spec = wardrobe.get("categories", {}).get(category)
    if not spec:
        return None
    cap_rank = _rank(exposure_cap, wardrobe)
    variations = spec.get("variations", [])
    if not variations:
        return None
    # 노출 상한 통과 variation만
    eligible = [v for v in variations if _rank(v.get("tier", "covered"), wardrobe) <= cap_rank]
    if not eligible:
        # 상한 이하가 하나도 없으면(예: 통근=covered인데 전부 high) 전체로 풀지 말고
        # 가장 덜 노출된 tier만 선택 — 공개 상황에서 과노출 방지.
        min_rank = min(_rank(v.get("tier", "covered"), wardrobe) for v in variations)
        eligible = [v for v in variations if _rank(v.get("tier", "covered"), wardrobe) == min_rank]
    # anti-repeat: 최근 사용 id 제외
    recent = rotation.get(category, [])
    fresh = [v for v in eligible if v["id"] not in recent[-3:]]
    pool = fresh if fresh else eligible
    rnd = random.Random("outfit:%s:%s" % (category, seed_key))
    return rnd.choice(pool)


def compose_outfit(activity: str, outfit_context: str, seed_key: str) -> dict | None:
    """갈아입는 순간 호출. 실루엣 픽 + 색/디테일 랜덤 레이어 → top/bottom 문자열 구성.
    반환: {top, bottom, outfit_id, category, tier, exposes, summary} 또는 None."""
    wardrobe = _load(WARDROBE_PATH, {})
    if not wardrobe:
        return None
    category = resolve_category(outfit_context, wardrobe)
    if not category:
        return None
    exposure_cap = resolve_exposure_cap(activity)
    rotation = _load(ROTATION_PATH, {})
    var = pick_variation(category, exposure_cap, seed_key, wardrobe, rotation)
    if not var:
        return None

    rnd = random.Random("outfitdetail:%s:%s" % (category, seed_key))
    color = rnd.choice(wardrobe.get("color_pool", ["아이보리"]))
    details = wardrobe.get("detail_pool", [])
    detail = rnd.choice(details) if details and rnd.random() < 0.6 else None

    # 색은 상의에 1회, 디테일은 상의에만(하의에 네크라인 등 붙는 어색함 방지). 하의는 색만 코디.
    base_top = var.get("top", "")
    base_bottom = var.get("bottom", "")
    top = ("%s %s (%s)" % (color, base_top, detail)) if (base_top and detail) else (("%s %s" % (color, base_top)).strip())
    bottom = base_bottom.strip()
    summary = top if not bottom else "%s + %s" % (top, bottom)

    # 로테이션 상태 갱신(최근 사용 id 누적, 카테고리별 최근 6개 유지)
    recent = rotation.get(category, [])
    recent = (recent + [var["id"]])[-6:]
    rotation[category] = recent
    rotation["_updated_at"] = seed_key
    _save(ROTATION_PATH, rotation)

    return {
        "top": top,
        "bottom": bottom,
        "outfit_id": var["id"],
        "category": category,
        "tier": var.get("tier"),
        "exposes": var.get("exposes", []),
        "innerwear": var.get("innerwear", "none"),
        "exposure_cap": exposure_cap,
        "summary": summary,
    }


if __name__ == "__main__":
    import sys
    # 데모: 각 카테고리 대표 상황으로 3회씩 뽑아 다양성 확인
    demos = [("evening_free", "home_casual"), ("clean_after_shower", "clean_after_shower"),
             ("night_wind_down", "summer_sleepwear"), ("morning_work", "home_casual_work")]
    for act, ctx in demos:
        print("== activity=%s outfit_context=%s (cap=%s) ==" % (act, ctx, resolve_exposure_cap(act)))
        for i in range(3):
            o = compose_outfit(act, ctx, "demo-%s-%d" % (act, i))
            if o:
                print("  [%s|%s] %s  exposes=%s" % (o["outfit_id"], o["tier"], o["summary"], o["exposes"]))
