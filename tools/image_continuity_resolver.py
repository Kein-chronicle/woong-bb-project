#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from project_paths import MESSAGES, state_path

APPEARANCE_PATH = state_path("eunbi_appearance_state.json")
STATE_PATH = state_path("image_continuity_state.json")


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_local() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def find_last_outgoing_image() -> Optional[dict]:
    files = sorted(MESSAGES.glob("*.jsonl"))
    for file_path in reversed(files):
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for raw in reversed(lines):
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if row.get("direction") == "outgoing" and row.get("type") == "image" and row.get("path"):
                return row
    return None


def family_from_appearance(appearance: dict) -> str:
    block = appearance.get("current_time_block", "")
    branch = appearance.get("appearance_branch", "")
    outfit = appearance.get("outfit_context", "")
    joined = " ".join([block, branch, outfit])
    if any(key in joined for key in ["hospital", "commute", "shift", "work"]):
        return "hospital_workday"
    if any(key in joined for key in ["exercise", "running", "swimming", "gym", "cycling"]):
        return "exercise_block"
    if any(key in joined for key in ["cafe", "outing", "park", "walk"]):
        return "cafe_outing"
    if any(key in joined for key in ["home", "night", "sleep", "dinner", "wind_down", "relaxed"]):
        return "home_relaxed"
    return "unknown"


def snapshot_from_appearance(appearance: dict) -> dict:
    return {
        "appearance_branch": appearance.get("appearance_branch"),
        "outfit_context": appearance.get("outfit_context"),
        "top": appearance.get("top"),
        "bottom": appearance.get("bottom"),
        "outerwear": appearance.get("outerwear"),
        "hair_state": appearance.get("hair_state"),
        "makeup_state": appearance.get("makeup_state"),
        "face_state": appearance.get("face_state"),
        "freshness_state": appearance.get("freshness_state"),
        "accessory_profile": appearance.get("accessory_profile"),
    }


def resolve() -> None:
    state = load_json(
        STATE_PATH,
        {
            "schema_version": 1,
            "managed_by": "image_continuity_resolver",
            "continuity_windows": {
                "immediate_repeat_minutes": 20,
                "same_outfit_family_hours": 12,
            },
        },
    )
    appearance = load_json(APPEARANCE_PATH, {})
    last_image = find_last_outgoing_image()

    state["last_resolved_at"] = now_iso()

    if not last_image:
        state["resolver_status"] = "no_previous_image"
        state["continuity_band"] = "none"
        state["preserve_scope"] = "no_direct_image_reference"
        state["direct_reference_path"] = None
        state["reference_strength"] = 0
        state["elapsed_minutes_since_last_image"] = None
        state["current_family"] = family_from_appearance(appearance)
        state["last_image_family"] = None
        state["preserve_targets"] = []
        state["scene_change_allowed"] = True
        state["appearance_change_allowed"] = True
        state["continuity_reason"] = "previous_outgoing_image_missing"
        save_json(STATE_PATH, state)
        return

    last_ts = parse_ts(last_image["timestamp"])
    elapsed_minutes = max(0, int((now_local() - last_ts).total_seconds() // 60))
    current_family = family_from_appearance(appearance)

    last_snapshot = state.get("last_sent_snapshot") or {}
    last_family = state.get("last_image_family") or last_snapshot.get("outfit_context") or current_family
    if last_family not in {"hospital_workday", "exercise_block", "cafe_outing", "home_relaxed"}:
        inferred_outfit = (last_snapshot.get("outfit_context") or "").lower()
        if "hospital" in inferred_outfit or "commute" in inferred_outfit:
            last_family = "hospital_workday"
        elif "exercise" in inferred_outfit or "swim" in inferred_outfit or "running" in inferred_outfit:
            last_family = "exercise_block"
        elif "cafe" in inferred_outfit or "outing" in inferred_outfit:
            last_family = "cafe_outing"
        elif "home" in inferred_outfit or "night" in inferred_outfit:
            last_family = "home_relaxed"
        else:
            last_family = current_family

    immediate_minutes = int(state.get("continuity_windows", {}).get("immediate_repeat_minutes", 20))
    same_family_hours = int(state.get("continuity_windows", {}).get("same_outfit_family_hours", 12))
    same_day = last_ts.date().isoformat() == appearance.get("current_date")
    same_family = current_family == last_family

    continuity_band = "expired"
    preserve_scope = "no_direct_image_reference"
    preserve_targets = []
    scene_change_allowed = True
    appearance_change_allowed = True
    reference_strength = 0
    continuity_reason = "appearance_reset_or_family_changed"

    if elapsed_minutes <= immediate_minutes and same_day:
        continuity_band = "immediate_repeat"
        preserve_scope = "full_scene_reference"
        preserve_targets = ["space", "lighting", "outfit", "hair", "makeup", "face_state", "mood"]
        scene_change_allowed = False
        appearance_change_allowed = False
        reference_strength = 100
        continuity_reason = "recent_image_and_no_meaningful_time_gap"
    elif same_day and same_family and elapsed_minutes <= same_family_hours * 60:
        continuity_band = "same_outfit_window"
        preserve_scope = "outfit_face_reference"
        preserve_targets = ["outfit", "hair", "makeup", "face_state", "accessory_profile"]
        scene_change_allowed = True
        appearance_change_allowed = False
        reference_strength = 72
        continuity_reason = "same_day_same_outfit_family_keep_appearance_only"

    state["resolver_status"] = "resolved"
    state["continuity_band"] = continuity_band
    state["preserve_scope"] = preserve_scope
    state["direct_reference_path"] = last_image.get("path") if preserve_scope != "no_direct_image_reference" else None
    state["reference_strength"] = reference_strength
    state["elapsed_minutes_since_last_image"] = elapsed_minutes
    state["current_family"] = current_family
    state["last_image_family"] = last_family
    state["preserve_targets"] = preserve_targets
    state["scene_change_allowed"] = scene_change_allowed
    state["appearance_change_allowed"] = appearance_change_allowed
    state["continuity_reason"] = continuity_reason
    state["last_sent_image"] = {
        "timestamp": last_image.get("timestamp"),
        "path": last_image.get("path"),
        "caption": last_image.get("caption", ""),
        "message_date": last_ts.date().isoformat(),
        "scene_tag": continuity_band if continuity_band != "expired" else None,
        "share_type": "outgoing_image_log",
    }

    # 기존 snapshot이 비어 있으면 현재 state 기준으로 bootstrap한다.
    if not any((state.get("last_sent_snapshot") or {}).values()):
        state["last_sent_snapshot"] = snapshot_from_appearance(appearance)

    save_json(STATE_PATH, state)
    print(
        json.dumps(
            {
                "ok": True,
                "continuity_band": continuity_band,
                "preserve_scope": preserve_scope,
                "direct_reference_path": state["direct_reference_path"],
                "elapsed_minutes_since_last_image": elapsed_minutes,
                "continuity_reason": continuity_reason,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    resolve()
