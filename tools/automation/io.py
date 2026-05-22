from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def now_local() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def load_json(path: Path, default: Optional[dict] = None) -> dict:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text())


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp_path, path)


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        fp.flush()
        os.fsync(fp.fileno())
        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
