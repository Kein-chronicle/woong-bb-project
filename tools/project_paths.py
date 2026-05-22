from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(os.environ.get("WOONG_BB_ROOT", Path(__file__).resolve().parents[1])).resolve()
STATE = ROOT / "state"
STATE_RUNTIME = STATE / "runtime"
STATE_LOGS = STATE / "logs"
SESSION = ROOT / "session"
MESSAGES = ROOT / "messages"
DIARY = ROOT / "diary"
PROFILE = ROOT / "profile"
TOOLS = ROOT / "tools"
SCRIPTS = ROOT / "scripts"
IMAGES = ROOT / "images"
TEMP = ROOT / ".tmp"
PLAYWRIGHT_MCP = ROOT / ".playwright-mcp"


def state_path(name: str) -> Path:
    return STATE / name


def runtime_path(name: str) -> Path:
    return STATE_RUNTIME / name


def log_path(name: str) -> Path:
    return STATE_LOGS / name


def ensure_operational_dirs() -> None:
    for path in (STATE_RUNTIME, STATE_LOGS, SESSION, MESSAGES, DIARY):
        path.mkdir(parents=True, exist_ok=True)
