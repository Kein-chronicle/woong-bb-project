#!/usr/bin/env python3
import argparse
import json
import shutil
import time
from pathlib import Path

from project_paths import PLAYWRIGHT_MCP, ROOT, TEMP


TARGET_DIRS = [TEMP, PLAYWRIGHT_MCP]
TARGET_FILES = [
    ROOT / "timedtext_urls.json",
    ROOT / "fail-video-requests.txt",
    ROOT / "playwright-yt-requests.txt",
]
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache"}
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}


def remove_path(path: Path, dry_run: bool) -> int:
    if not path.exists():
        return 0
    size = path.stat().st_size if path.is_file() else 0
    if path.is_dir():
        size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    if not dry_run:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return size


def older_than(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime < cutoff
    except FileNotFoundError:
        return False


def cleanup_temp_dirs(max_age_hours: int, dry_run: bool) -> list[dict]:
    cutoff = time.time() - (max_age_hours * 3600)
    removed = []
    for target in TARGET_DIRS:
        if not target.exists():
            continue
        if older_than(target, cutoff) or target in TARGET_DIRS:
            size = remove_path(target, dry_run)
            removed.append({"path": str(target), "bytes": size, "kind": "temp_dir"})
    return removed


def cleanup_target_files(dry_run: bool) -> list[dict]:
    removed = []
    for target in TARGET_FILES:
        if not target.exists():
            continue
        size = remove_path(target, dry_run)
        removed.append({"path": str(target), "bytes": size, "kind": "temp_file"})
    return removed


def cleanup_python_caches(dry_run: bool) -> list[dict]:
    removed = []
    for path in ROOT.rglob("*"):
        if any(part in {".git", "session"} for part in path.relative_to(ROOT).parts):
            continue
        if path.is_dir() and path.name in CACHE_DIR_NAMES:
            size = remove_path(path, dry_run)
            removed.append({"path": str(path), "bytes": size, "kind": "cache_dir"})
        elif path.is_file() and path.suffix in CACHE_FILE_SUFFIXES:
            size = remove_path(path, dry_run)
            removed.append({"path": str(path), "bytes": size, "kind": "cache_file"})
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean woong-bb operational temp artifacts.")
    parser.add_argument("--max-age-hours", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    removed = []
    removed.extend(cleanup_temp_dirs(args.max_age_hours, args.dry_run))
    removed.extend(cleanup_target_files(args.dry_run))
    removed.extend(cleanup_python_caches(args.dry_run))
    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": args.dry_run,
                "removed_count": len(removed),
                "removed_bytes": sum(item["bytes"] for item in removed),
                "removed": removed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
