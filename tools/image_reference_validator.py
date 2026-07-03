#!/usr/bin/env python3
"""
image_reference_validator.py
생성 직전 outfit/space reference와 현재 상태가 맞는지 검사하고
불일치 시 자동 교정.

Usage:
  python3 image_reference_validator.py  # 검사 + 교정 실행
  python3 image_reference_validator.py --check-only  # 검사만 (교정 없음)
"""
import argparse
import json
import os
from pathlib import Path

BASE = Path("/Users/kein/Desktop/woong-bb")
OUTFIT_REF_ROOT = Path("/Users/kein/Projects/woong-bb/working/eunbi/meta_references/generated/v2/outfits")
SPACE_REF_ROOT  = Path("/Users/kein/Projects/woong-bb/working/eunbi/meta_references/generated/v2/spaces")

APPEARANCE_PATH   = BASE / "state" / "eunbi_appearance_state.json"
PROMPT_PLAN_PATH  = BASE / "state" / "image_prompt_plan.json"
REF_MAP_PATH      = BASE / "state" / "outfit_reference_map.json"
CONTINUITY_PATH   = BASE / "state" / "image_continuity_state.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_allowed_outfit_families(outfit_context: str, ref_map: dict) -> list:
    """outfit_context에서 허용 OC 패밀리 목록 반환."""
    ctx_map = ref_map.get("outfit_context_map", {})
    # 직접 매핑
    if outfit_context in ctx_map:
        return ctx_map[outfit_context]
    # 부분 매칭 시도
    for key, families in ctx_map.items():
        if key in outfit_context or outfit_context in key:
            return families
    return ["OC-06", "OC-08"]  # 기본값: oversized_shirt, pajama_sleeveless


def get_allowed_space_refs(space_anchor: str, ref_map: dict) -> list:
    """space_anchor에서 허용 SP 파일 prefix 목록 반환."""
    anchor_map = ref_map.get("space_anchor_map", {})
    return anchor_map.get(space_anchor, ["SP-02", "SP-04"])


def outfit_ref_matches(ref_path: str, allowed_families: list) -> bool:
    """레퍼런스 경로가 허용 패밀리에 속하는지 확인."""
    fname = os.path.basename(ref_path)
    for family in allowed_families:
        if fname.startswith(family):
            return True
    return False


def space_ref_matches(ref_path: str, allowed_prefixes: list) -> bool:
    """레퍼런스 경로가 허용 SP prefix에 속하는지 확인."""
    fname = os.path.basename(ref_path)
    for prefix in allowed_prefixes:
        if fname.startswith(prefix):
            return True
    return False


def pick_outfit_refs(allowed_families: list, count: int = 2) -> list:
    """허용 패밀리에서 레퍼런스 파일 선택 (variant -02 우선)."""
    selected = []
    for family in allowed_families:
        candidates = sorted(OUTFIT_REF_ROOT.glob(f"{family}-*.png"))
        # variant 02 우선, 없으면 01
        priority = [f for f in candidates if "-02" in f.name]
        rest     = [f for f in candidates if f not in priority]
        for f in priority + rest:
            if len(selected) >= count:
                break
            if str(f) not in selected:
                selected.append(str(f))
        if len(selected) >= count:
            break
    return selected[:count]


def pick_space_refs(allowed_prefixes: list, count: int = 2) -> list:
    """허용 SP prefix에서 공간 레퍼런스 선택."""
    selected = []
    for prefix in allowed_prefixes:
        candidates = sorted(SPACE_REF_ROOT.glob(f"{prefix}*.png"))
        for f in candidates:
            if len(selected) >= count:
                break
            if str(f) not in selected:
                selected.append(str(f))
        if len(selected) >= count:
            break
    return selected[:count]


def validate_and_fix(check_only: bool = False) -> dict:
    appearance = load_json(APPEARANCE_PATH)
    plan       = load_json(PROMPT_PLAN_PATH)
    ref_map    = load_json(REF_MAP_PATH)
    continuity = load_json(CONTINUITY_PATH)

    outfit_context = plan.get("outfit_context") or appearance.get("outfit_context", "")
    space_anchor   = plan.get("space_anchor", "")

    ref_images = plan.get("reference_images", {})
    current_outfit_refs = ref_images.get("outfit", [])
    current_space_refs  = ref_images.get("space", [])

    issues = []
    fixes  = {}

    # ── Outfit 검사 ──────────────────────────────
    allowed_outfit = get_allowed_outfit_families(outfit_context, ref_map)
    bad_outfits = [r for r in current_outfit_refs if not outfit_ref_matches(r, allowed_outfit)]
    if bad_outfits:
        issues.append({
            "type": "outfit_mismatch",
            "context": outfit_context,
            "allowed": allowed_outfit,
            "bad_refs": bad_outfits,
        })
        if not check_only:
            new_outfit_refs = pick_outfit_refs(allowed_outfit, count=2)
            fixes["outfit"] = new_outfit_refs
            ref_images["outfit"] = new_outfit_refs

    # ── Space 검사 ──────────────────────────────
    # 레퍼런스 없는 anchor → downgrade
    downgrade = ref_map.get("space_anchor_downgrade", {})
    effective_anchor = downgrade.get(space_anchor, space_anchor)
    if effective_anchor != space_anchor:
        issues.append({
            "type": "space_anchor_downgrade",
            "original": space_anchor,
            "downgraded_to": effective_anchor,
        })
        if not check_only:
            plan["space_anchor"] = effective_anchor

    allowed_space = get_allowed_space_refs(effective_anchor, ref_map)
    bad_spaces = [r for r in current_space_refs if not space_ref_matches(r, allowed_space)]
    if bad_spaces:
        issues.append({
            "type": "space_mismatch",
            "anchor": effective_anchor,
            "allowed": allowed_space,
            "bad_refs": bad_spaces,
        })
        if not check_only:
            new_space_refs = pick_space_refs(allowed_space, count=1)
            fixes["space"] = new_space_refs
            ref_images["space"] = new_space_refs

    # ── Continuity: scene_change_allowed 보수화 ──
    appearance_branch = appearance.get("appearance_branch", "")
    time_block = plan.get("time_block", "")
    is_same_night = any(k in time_block for k in ["night", "sleep", "wind_down", "evening"])
    if is_same_night and continuity.get("scene_change_allowed", True):
        issues.append({
            "type": "continuity_scene_change_too_permissive",
            "note": "같은 밤 블록에서 scene_change_allowed=true → false로 조정",
        })
        if not check_only:
            continuity["scene_change_allowed"] = False
            continuity["continuity_reason"] = f"same_night_{appearance_branch}_scene_locked"
            save_json(CONTINUITY_PATH, continuity)

    # ── 교정 적용 ──────────────────────────────
    if fixes and not check_only:
        plan["reference_images"] = ref_images
        save_json(PROMPT_PLAN_PATH, plan)

    return {
        "outfit_context": outfit_context,
        "space_anchor": space_anchor,
        "effective_anchor": effective_anchor,
        "issues": issues,
        "fixes_applied": fixes if not check_only else {},
        "ok": len(issues) == 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    result = validate_and_fix(check_only=args.check_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["ok"]:
        print("✅ reference 검사 통과")
    else:
        action = "검사 완료 (교정 없음)" if args.check_only else "교정 완료"
        print(f"⚠️ {len(result['issues'])}건 이슈 발견 → {action}")
