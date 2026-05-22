from __future__ import annotations

import glob
import json
from datetime import datetime
from typing import Optional

from project_paths import MESSAGES, STATE

from .io import load_json, now_local


PROACTIVE_PATH = STATE / "proactive_messages.json"


def load_message_events(limit_files: int = 2) -> list:
    files = sorted(glob.glob(str(MESSAGES / "*.jsonl")))
    selected = files[-limit_files:]
    events = []
    for path in selected:
        with open(path, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    def event_sort_key(event: dict) -> tuple:
        timestamp = event.get("timestamp", "")
        dt = parse_event_timestamp(timestamp)
        if not dt:
            return (float("-inf"), timestamp)
        return (dt.timestamp(), timestamp)

    events.sort(key=event_sort_key)
    return events


def parse_event_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return None


def compute_conversation_guard() -> dict:
    proactive = load_json(PROACTIVE_PATH, {})
    guards = proactive.get("guards", {})
    events = load_message_events()
    last_incoming = None
    last_outgoing = None
    recent_pairs = []
    for event in events:
        if event.get("direction") == "incoming":
            last_incoming = event
        elif event.get("direction") == "outgoing" and event.get("type") in {"text", "voice_message", "voice"}:
            last_outgoing = event
        if event.get("direction") in {"incoming", "outgoing"}:
            recent_pairs.append(event)
    now_dt = now_local()
    window_minutes = int(guards.get("conversation_active_window_minutes", 20))
    cooldown_minutes = int(guards.get("outgoing_cooldown_minutes", 10))
    late_probe_minutes = int(guards.get("late_reply_probe_minutes", 60))
    conversation_active = False
    last_incoming_dt = parse_event_timestamp(last_incoming.get("timestamp")) if last_incoming else None
    last_outgoing_dt = parse_event_timestamp(last_outgoing.get("timestamp")) if last_outgoing else None
    if last_incoming_dt and last_outgoing_dt:
        conversation_active = (
            (now_dt - last_incoming_dt).total_seconds() <= window_minutes * 60
            and (now_dt - last_outgoing_dt).total_seconds() <= window_minutes * 60
            and abs((last_outgoing_dt - last_incoming_dt).total_seconds()) <= window_minutes * 60
        )
    waiting_reply = False
    if last_outgoing_dt and (not last_incoming_dt or last_outgoing_dt > last_incoming_dt):
        waiting_reply = True
    outgoing_cooldown = False
    if last_outgoing_dt:
        outgoing_cooldown = (now_dt - last_outgoing_dt).total_seconds() <= cooldown_minutes * 60
    late_reply_ok = False
    if last_incoming_dt:
        late_reply_ok = (now_dt - last_incoming_dt).total_seconds() >= late_probe_minutes * 60
    unanswered_outgoing_count = 0
    if waiting_reply:
        last_incoming_dt = parse_event_timestamp(last_incoming.get("timestamp")) if last_incoming else None
        for event in events:
            if event.get("direction") != "outgoing" or event.get("type") not in {"text", "voice_message", "voice"}:
                continue
            event_dt = parse_event_timestamp(event.get("timestamp"))
            if not event_dt:
                continue
            if not last_incoming_dt or event_dt > last_incoming_dt:
                unanswered_outgoing_count += 1
    minutes_since_last_outgoing = None
    if last_outgoing_dt:
        minutes_since_last_outgoing = (now_dt - last_outgoing_dt).total_seconds() / 60.0
    return {
        "conversation_active": conversation_active,
        "waiting_reply": waiting_reply,
        "outgoing_cooldown": outgoing_cooldown,
        "late_reply_ok": late_reply_ok,
        "last_incoming": last_incoming,
        "last_outgoing": last_outgoing,
        "unanswered_outgoing_count": unanswered_outgoing_count,
        "minutes_since_last_outgoing": minutes_since_last_outgoing,
    }
