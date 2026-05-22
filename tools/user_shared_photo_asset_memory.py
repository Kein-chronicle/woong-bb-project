#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from project_paths import ROOT

REGISTRY_PATH = ROOT / "state" / "user_shared_photo_asset_registry.json"
ASSET_ROOT = ROOT / "images" / "user_shared_assets"


DEFAULT_REGISTRY = {
    "schema_version": 1,
    "managed_by": "user_shared_photo_asset_memory",
    "asset_root": str(ASSET_ROOT),
    "last_updated_at": None,
    "assets": [],
    "notes": "User-shared Telegram photos promoted into reusable image-generation references.",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(value: str, fallback: str = "asset") -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return (normalized or fallback)[:60]


def normalize_tag(value: str) -> str:
    normalized = re.sub(r"\s+", "_", value.strip().lower())
    normalized = re.sub(r"[^\w가-힣_-]+", "", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:80]


def ensure_registry() -> dict:
    registry = load_json(REGISTRY_PATH, DEFAULT_REGISTRY.copy())
    registry.setdefault("schema_version", 1)
    registry.setdefault("managed_by", "user_shared_photo_asset_memory")
    registry.setdefault("asset_root", str(ASSET_ROOT))
    registry.setdefault("assets", [])
    return registry


def read_analysis(path_value: Optional[str]) -> dict:
    if not path_value:
        return {}
    if path_value == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path_value).read_text(encoding="utf-8")
    return json.loads(raw or "{}")


def flat_tags(analysis: dict) -> list[str]:
    tags: list[str] = []
    for key in ["scene_tags", "object_tags", "relationship_tags", "reuse_triggers", "generation_use_cases"]:
        value = analysis.get(key, [])
        if isinstance(value, list):
            tags.extend(str(item) for item in value if str(item).strip())
    for subject in analysis.get("reusable_subjects", []) if isinstance(analysis.get("reusable_subjects"), list) else []:
        if isinstance(subject, dict):
            tags.extend(str(item) for item in subject.get("visual_tags", []) if str(item).strip())
            tags.extend(str(item) for item in subject.get("reuse_when", []) if str(item).strip())
            if subject.get("kind"):
                tags.append(str(subject["kind"]))
    return sorted({normalized for tag in tags if (normalized := normalize_tag(tag))})


def asset_kind(analysis: dict) -> str:
    raw = str(analysis.get("asset_kind") or "user_shared_photo").strip()
    allowed = {
        "person_context",
        "shared_object",
        "wearable",
        "accessory",
        "cup_or_tableware",
        "food_drink",
        "place_scene",
        "couple_item",
        "reference_bundle",
        "user_shared_photo",
    }
    return raw if raw in allowed else "user_shared_photo"


def build_asset_id(image: Path, analysis: dict, digest: str) -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    title = str(analysis.get("title") or analysis.get("short_label") or image.stem)
    return f"{stamp}_{asset_kind(analysis)}_{slug(title)}_{digest[:10]}"


def find_existing_by_hash(registry: dict, digest: str) -> Optional[dict]:
    for asset in registry.get("assets", []):
        if asset.get("source_sha256") == digest:
            return asset
    return None


def add_asset(args: argparse.Namespace) -> dict:
    image = Path(args.image).expanduser().resolve()
    if not image.exists():
        raise FileNotFoundError(str(image))

    analysis = read_analysis(args.analysis_json)
    digest = file_sha256(image)
    registry = ensure_registry()
    existing = find_existing_by_hash(registry, digest)

    timestamp = now_iso()
    if existing:
        existing.setdefault("source_paths", [])
        if str(image) not in existing["source_paths"]:
            existing["source_paths"].append(str(image))
        existing["last_seen_at"] = timestamp
        if args.caption:
            existing.setdefault("captions", [])
            if args.caption not in existing["captions"]:
                existing["captions"].append(args.caption)
        if analysis:
            existing["analysis"] = merge_analysis(existing.get("analysis", {}), analysis)
            existing["tags"] = sorted(set(existing.get("tags", [])) | set(flat_tags(existing["analysis"])))
        registry["last_updated_at"] = timestamp
        save_json(REGISTRY_PATH, registry)
        return {"ok": True, "action": "updated_existing", "asset_id": existing["asset_id"], "asset": existing}

    asset_id = build_asset_id(image, analysis, digest)
    asset_dir = ASSET_ROOT / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    target = asset_dir / f"source{image.suffix.lower() or '.jpg'}"
    shutil.copy2(image, target)

    asset = {
        "asset_id": asset_id,
        "created_at": timestamp,
        "last_seen_at": timestamp,
        "source": args.source,
        "telegram_user": args.telegram_user,
        "kind": asset_kind(analysis),
        "title": analysis.get("title") or analysis.get("short_label") or image.stem,
        "canonical_path": str(target),
        "asset_dir": str(asset_dir),
        "source_paths": [str(image)],
        "source_sha256": digest,
        "captions": [args.caption] if args.caption else [],
        "tags": flat_tags(analysis),
        "analysis": analysis,
        "generation_reuse": analysis.get(
            "generation_reuse",
            {
                "allowed": bool(analysis),
                "default_strength": "supporting_reference",
                "requires_user_intent": True,
            },
        ),
    }
    save_json(asset_dir / "metadata.json", asset)
    registry["assets"].append(asset)
    registry["last_updated_at"] = timestamp
    save_json(REGISTRY_PATH, registry)
    return {"ok": True, "action": "created", "asset_id": asset_id, "asset": asset}


def merge_analysis(old: dict, new: dict) -> dict:
    merged = dict(old or {})
    for key, value in new.items():
        if isinstance(value, list) and isinstance(merged.get(key), list):
            seen = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in merged[key]}
            for item in value:
                marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
                if marker not in seen:
                    merged[key].append(item)
                    seen.add(marker)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_analysis(merged[key], value)
        elif value not in (None, "", []):
            merged[key] = value
    return merged


def searchable_text(asset: dict) -> str:
    parts: list[str] = [
        str(asset.get("asset_id", "")),
        str(asset.get("kind", "")),
        str(asset.get("title", "")),
        " ".join(str(item) for item in asset.get("tags", [])),
        " ".join(str(item) for item in asset.get("captions", [])),
    ]
    analysis = asset.get("analysis", {})
    for key in ["description_ko", "visible_summary_ko", "prompt_hints_ko"]:
        value = analysis.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    for subject in analysis.get("reusable_subjects", []) if isinstance(analysis.get("reusable_subjects"), list) else []:
        if isinstance(subject, dict):
            parts.extend(str(subject.get(key, "")) for key in ["label_ko", "kind", "description_ko"])
            parts.extend(str(item) for item in subject.get("visual_tags", []))
            parts.extend(str(item) for item in subject.get("reuse_when", []))
    return " ".join(parts).lower()


def search_assets(args: argparse.Namespace) -> dict:
    registry = ensure_registry()
    query_terms = [term for term in re.split(r"\s+", args.query.lower().strip()) if term]
    results = []
    for asset in registry.get("assets", []):
        if args.kind and not asset_matches_kind(asset, args.kind):
            continue
        haystack = searchable_text(asset)
        score = sum(3 if term in " ".join(asset.get("tags", [])).lower() else 1 for term in query_terms if term in haystack)
        if not query_terms or score > 0:
            results.append(
                {
                    "asset_id": asset.get("asset_id"),
                    "kind": asset.get("kind"),
                    "title": asset.get("title"),
                    "canonical_path": asset.get("canonical_path"),
                    "tags": asset.get("tags", []),
                    "score": score,
                    "analysis": asset.get("analysis", {}),
                }
            )
    results.sort(key=lambda item: (item["score"], item["asset_id"] or ""), reverse=True)
    return {"ok": True, "query": args.query, "count": len(results[: args.limit]), "results": results[: args.limit]}


def asset_matches_kind(asset: dict, kind: str) -> bool:
    if asset.get("kind") == kind:
        return True
    analysis = asset.get("analysis", {})
    subjects = analysis.get("reusable_subjects", [])
    if not isinstance(subjects, list):
        return False
    return any(isinstance(subject, dict) and subject.get("kind") == kind for subject in subjects)


def init_registry(_args: argparse.Namespace) -> dict:
    registry = ensure_registry()
    registry["last_updated_at"] = registry.get("last_updated_at") or now_iso()
    save_json(REGISTRY_PATH, registry)
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "registry_path": str(REGISTRY_PATH), "asset_root": str(ASSET_ROOT)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage reusable user-shared photo assets.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    add = sub.add_parser("add")
    add.add_argument("--image", required=True)
    add.add_argument("--analysis-json", default=None, help="Path to analysis JSON, or '-' for stdin.")
    add.add_argument("--caption", default="")
    add.add_argument("--telegram-user", default="")
    add.add_argument("--source", default="telegram_incoming")

    search = sub.add_parser("search")
    search.add_argument("--query", default="")
    search.add_argument("--kind", default="")
    search.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()
    if args.command == "init":
        result = init_registry(args)
    elif args.command == "add":
        result = add_asset(args)
    elif args.command == "search":
        result = search_assets(args)
    else:
        raise RuntimeError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
