#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
INBOX_PATH = STATE / "lab_idea_inbox.json"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_inbox() -> dict:
    if not INBOX_PATH.exists():
        return {
            "schema_version": 1,
            "managed_by": "lab_idea_inbox",
            "items": [],
        }
    try:
        return json.loads(INBOX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": 1,
            "managed_by": "lab_idea_inbox",
            "items": [],
        }


def save_inbox(data: dict) -> None:
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INBOX_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="웅삐랩 아이디어 인박스에 항목 추가")
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--detail", default="")
    parser.add_argument("--project", default="whale-survivors")
    parser.add_argument("--source", default="telegram_chat")
    parser.add_argument("--tags", default="")
    args = parser.parse_args()

    data = load_inbox()
    items = data.setdefault("items", [])
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    item_id = f"idea_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    items.append(
        {
            "id": item_id,
            "created_at": now_iso(),
            "project": args.project,
            "source": args.source,
            "title": args.title.strip(),
            "summary": args.summary.strip(),
            "detail": args.detail.strip(),
            "tags": tags,
            "status": "inbox",
        }
    )
    data["last_updated_at"] = now_iso()
    save_inbox(data)
    print(item_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
