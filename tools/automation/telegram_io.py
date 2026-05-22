from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from project_paths import MESSAGES, ROOT, SESSION

from .io import append_jsonl, load_json, now_iso, now_local


def append_worker_note(message: str) -> None:
    log_path = SESSION / "automation-worker-actions.log"
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write("%s %s\n" % (now_iso(), message))


def session_token_and_chat() -> tuple:
    env_path = SESSION / ".env"
    access_path = SESSION / "access.json"
    token = None
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    access = load_json(access_path, {})
    chat_id = None
    allow_from = access.get("allowFrom") or []
    if allow_from:
        chat_id = str(allow_from[0])
    return token, chat_id


def send_telegram_text(text: str) -> bool:
    if (SESSION / "mute.flag").exists():
        append_worker_note("telegram_send_skipped muted")
        return False
    token, chat_id = session_token_and_chat()
    if not token or not chat_id:
        append_worker_note("telegram_send_skipped missing_token_or_chat")
        return False
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    try:
        with urllib.request.urlopen(url, data=payload, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            ok = bool(body.get("ok"))
            append_worker_note("telegram_send_%s" % ("ok" if ok else "failed"))
            return ok
    except Exception as exc:
        append_worker_note("telegram_send_error %s" % exc)
        return False


def append_message_log(direction: str, msg_type: str, content: str) -> None:
    now_dt = now_local()
    log_path = MESSAGES / ("%s.jsonl" % now_dt.strftime("%Y-%m-%d"))
    event = {
        "timestamp": now_iso(),
        "direction": direction,
        "telegram_user": "K8832353",
        "type": msg_type,
        "content": content,
    }
    append_jsonl(log_path, event)


def send_telegram_voice_message(text: str, label: str, profile: str = "auto") -> bool:
    if (SESSION / "mute.flag").exists():
        append_worker_note("telegram_voice_skipped muted")
        return False
    script = Path("/Users/kein/.codex/skills/telegram-voice-message-send/scripts/send_elevenlabs_voice_message.py")
    if not script.exists():
        append_worker_note("telegram_voice_skipped missing_skill_script")
        return False
    cmd = [
        "python3",
        str(script),
        "--workdir",
        str(ROOT),
        "--state-dir",
        str(SESSION),
        "--profile",
        profile,
        "--label",
        label,
        "--text",
        text,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        append_worker_note("telegram_voice_error %s" % ((result.stderr or result.stdout).strip()[:300]))
        return False
    append_worker_note("telegram_voice_ok %s" % label)
    append_message_log("outgoing", "voice_message", text)
    return True
