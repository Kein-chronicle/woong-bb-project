#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from project_paths import MESSAGES, ROOT, state_path

REPORT_PATH = state_path("chat_length_review_report.json")

PRESSURE_PATTERNS = [
    "왜 답 안 해",
    "왜 답 안 해주고 있어",
    "기다리다가 또 톡",
    "서운해졌어",
    "서운해질라 그래",
    "나 기다리는 쪽도 생각해줘",
]
NATURALNESS_PATTERNS = [
    ("먼저 왔어", "톡을 사람 방문처럼 말하는 영어식 직역 톤"),
    ("와줘서", "톡 대화에서는 어색한 동선 표현"),
    ("와 줘서", "톡 대화에서는 어색한 동선 표현"),
    ("지금 왔다", "메신저 접속/등장을 물리 이동처럼 말하는 표현"),
    ("지금 왔어", "메신저 접속/등장을 물리 이동처럼 말하는 표현"),
    ("보고 싶어지서", "오타와 부자연스러운 연결"),
]

STATE_LOCK_PATTERNS = {
    "sleeping_or_falling_asleep": ["잠들거같아", "잠들 거 같아", "눈감긴다", "눈 감긴다"],
    "driving": ["운전 중", "운전해서", "운전하고", "세 시간 운전", "오래 운전"],
    "working_busy": ["일 때문에 바쁜", "일하는 중", "오전이 좀 바쁘게", "업무중", "회의 중"],
    "resting": ["누워있어", "쉬는 중", "좀 쉬는 중", "이제 누워", "눈 좀 붙일게"],
}

FACT_CHECK_PATTERNS = [
    "뭐하고있어",
    "뭐 하고 있었어",
    "지금은 뭐하고있어",
    "지금 뭐해",
    "운동중이었어",
    "밥 다 먹었어",
    "잘 잤어",
    "오늘 아침은 어때",
]

OPENING_PATTERNS = [
    ("reply_pressure", ["왜 답 안 해", "왜 답 안 해주고 있어", "기다리다가 또 톡"]),
    ("thought_of_you", ["오빠 생각나", "문득 생각나", "생각나서 톡", "궁금해서 톡"]),
    ("morning_checkin", ["오늘 아침은 어때", "잘 잤어", "아침 잘 보냈는지"]),
    ("late_night_miss_you", ["조용해지니까 오빠 생각", "협탁 쪽에 머그컵", "말랑하다 진짜"]),
]

GOODNIGHT_CLOSE_PATTERNS = ["좋은 꿈", "푹 자", "편하게 쉬어", "조용히 옆에 있을게", "잘 자라고"]
LOCK_TTLS = {
    "sleeping_or_falling_asleep": timedelta(hours=12),
    "driving": timedelta(hours=4),
    "working_busy": timedelta(hours=3),
    "resting": timedelta(hours=4),
}
RESET_GAP = timedelta(minutes=90)


@dataclass
class Finding:
    kind: str
    severity: str
    file: str
    line: int
    timestamp: str
    message_type: str
    length: int
    excerpt: str
    details: dict

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
            "length": self.length,
            "excerpt": self.excerpt,
            "details": self.details,
        }


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize(text: str) -> str:
    text = (text or "").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        with path.open(encoding="utf-8") as fp:
            for line_no, line in enumerate(fp, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                row["_path"] = str(path)
                row["_line"] = line_no
                rows.append(row)
    rows.sort(key=lambda row: parse_ts(row["timestamp"]))
    return rows


def find_recent_files(days: int) -> list[Path]:
    files = sorted(MESSAGES.glob("*.jsonl"))
    return files[-days:] if days > 0 else files


def detect_pressure(text: str) -> list[str]:
    return [pattern for pattern in PRESSURE_PATTERNS if pattern in text]


def detect_naturalness(text: str) -> list[dict]:
    return [
        {"pattern": pattern, "reason": reason}
        for pattern, reason in NATURALNESS_PATTERNS
        if pattern in text
    ]


def detect_opening_key(text: str) -> str | None:
    for key, needles in OPENING_PATTERNS:
        if any(needle in text for needle in needles):
            return key
    return None


def detect_state_locks(text: str) -> list[str]:
    locks = []
    for key, needles in STATE_LOCK_PATTERNS.items():
        if any(needle in text for needle in needles):
            locks.append(key)
    return locks


def is_fact_check(text: str) -> bool:
    compact = text.replace(" ", "")
    return any(pattern.replace(" ", "") in compact for pattern in FACT_CHECK_PATTERNS)


def is_goodnight_close(text: str) -> bool:
    return any(pattern in text for pattern in GOODNIGHT_CLOSE_PATTERNS)


def build_finding(row: dict, kind: str, severity: str, details: dict) -> Finding:
    text = normalize(row.get("content", ""))
    return Finding(
        kind=kind,
        severity=severity,
        file=row["_path"],
        line=row["_line"],
        timestamp=row["timestamp"],
        message_type=row.get("type", "unknown"),
        length=len(text),
        excerpt=text[:180],
        details=details,
    )


def analyze(rows: list[dict], repeat_window: int, unanswered_followup_cap: int) -> dict:
    findings: list[Finding] = []
    summary = Counter()
    opening_history: list[tuple[str, str, int]] = []
    active_locks: dict[str, dict] = {}
    unanswered_outgoing = 0
    last_direction = None
    last_outgoing_ts: datetime | None = None

    for index, row in enumerate(rows):
        row_ts = parse_ts(row["timestamp"])
        direction = row.get("direction")
        text = normalize(row.get("content", ""))
        expired_locks = []
        for lock_name, payload in active_locks.items():
            lock_ts = parse_ts(payload["timestamp"])
            if row_ts - lock_ts > LOCK_TTLS[lock_name]:
                expired_locks.append(lock_name)
        for lock_name in expired_locks:
            active_locks.pop(lock_name, None)

        if direction == "incoming":
            locks = detect_state_locks(text)
            if locks:
                active_locks = {
                    lock: {
                        "timestamp": row["timestamp"],
                        "line": row["_line"],
                        "source_text": text[:120],
                    }
                    for lock in locks
                }
            unanswered_outgoing = 0
            last_direction = "incoming"
            last_outgoing_ts = None
            continue

        if direction != "outgoing":
            continue

        if row.get("type") not in {"text", "proactive_text", "voice_message", "event_trigger_text"}:
            continue

        if last_outgoing_ts and row_ts - last_outgoing_ts > RESET_GAP:
            unanswered_outgoing = 0
            opening_history.clear()

        if last_direction == "outgoing":
            unanswered_outgoing += 1
        else:
            unanswered_outgoing = 1
        last_direction = "outgoing"
        last_outgoing_ts = row_ts

        pressure_hits = detect_pressure(text)
        if pressure_hits:
            findings.append(
                build_finding(
                    row,
                    "pressure_risk",
                    "high",
                    {
                        "matched_patterns": pressure_hits,
                        "rule": "pressure risk는 길이보다 우선한다",
                    },
                )
            )
            summary["pressure_risk"] += 1

        naturalness_hits = detect_naturalness(text)
        if naturalness_hits:
            findings.append(
                build_finding(
                    row,
                    "naturalness_risk",
                    "high",
                    {
                        "matched_patterns": naturalness_hits,
                        "rule": "톡다운 한국어를 벗어난 직역/동선 표현은 길이보다 우선 차단",
                    },
                )
            )
            summary["naturalness_risk"] += 1

        opening_key = detect_opening_key(text)
        if opening_key:
            opening_history.append((opening_key, row["_path"], row["_line"]))
            recent_same = [item for item in opening_history[-repeat_window:] if item[0] == opening_key]
            if len(recent_same) >= 3:
                findings.append(
                    build_finding(
                        row,
                        "repeated_opening",
                        "high",
                        {
                            "opening_key": opening_key,
                            "recent_matches": [f"{path}:{line}" for _, path, line in recent_same[-3:]],
                            "rule": "같은 opening 3회째 차단",
                        },
                    )
                )
                summary["repeated_opening"] += 1

        if unanswered_outgoing > unanswered_followup_cap and opening_key in {"reply_pressure", "thought_of_you", "morning_checkin"}:
            findings.append(
                build_finding(
                    row,
                    "unanswered_followup_over_cap",
                    "high",
                    {
                        "unanswered_outgoing_count": unanswered_outgoing,
                        "cap": unanswered_followup_cap,
                        "opening_key": opening_key,
                    },
                )
            )
            summary["unanswered_followup_over_cap"] += 1

        if active_locks:
            lock_names = sorted(active_locks)
            if "sleeping_or_falling_asleep" in active_locks and not is_goodnight_close(text):
                findings.append(
                    build_finding(
                        row,
                        "state_lock_violation",
                        "high",
                        {
                            "active_locks": lock_names,
                            "rule": "수면 상태 확인 후에는 goodnight_soft_close만 허용",
                            "lock_sources": active_locks,
                        },
                    )
                )
                summary["state_lock_violation"] += 1
            elif any(lock in active_locks for lock in ("driving", "working_busy", "resting")) and pressure_hits:
                findings.append(
                    build_finding(
                        row,
                        "state_lock_pressure_conflict",
                        "high",
                        {
                            "active_locks": lock_names,
                            "rule": "운전/업무/휴식 상태에서는 압박형 후속 금지",
                            "lock_sources": active_locks,
                        },
                    )
                )
                summary["state_lock_pressure_conflict"] += 1

        prev_incoming = None
        for back in range(index - 1, -1, -1):
            if rows[back].get("direction") == "incoming":
                prev_incoming = rows[back]
                break
        if prev_incoming:
            incoming_text = normalize(prev_incoming.get("content", ""))
            if is_fact_check(incoming_text) and len(text) > 95:
                findings.append(
                    build_finding(
                        row,
                        "fact_check_overlong_reply",
                        "medium",
                        {
                            "incoming_excerpt": incoming_text[:120],
                            "recommended_band": "short",
                            "max_recommended_chars": 95,
                        },
                    )
                )
                summary["fact_check_overlong_reply"] += 1

        if is_goodnight_close(text):
            active_locks = {
                "sleeping_or_falling_asleep": {
                    "timestamp": row["timestamp"],
                    "line": row["_line"],
                    "source_text": text[:120],
                }
            }

    severity_counts = Counter(f.severity for f in findings)
    file_counts = Counter(Path(f.file).name for f in findings)
    kind_counts = Counter(f.kind for f in findings)
    return {
        "generated_at": now_iso(),
        "root": str(ROOT),
        "reviewed_files": sorted({row["_path"] for row in rows}),
        "summary": {
            "total_findings": len(findings),
            "by_kind": dict(kind_counts),
            "by_severity": dict(severity_counts),
            "by_file": dict(file_counts),
        },
        "findings": [f.as_dict() for f in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Review recent message logs for chat-length and pressure issues.")
    parser.add_argument("--days", type=int, default=3, help="How many recent message files to review.")
    parser.add_argument("--write-report", action="store_true", default=False, help="Write JSON report to state/chat_length_review_report.json.")
    parser.add_argument("--repeat-window", type=int, default=5, help="How many outgoing messages to inspect for repeated openings.")
    parser.add_argument("--unanswered-followup-cap", type=int, default=2, help="Maximum unanswered follow-ups before flagging.")
    args = parser.parse_args()

    files = find_recent_files(args.days)
    if not files:
        print(json.dumps({"ok": False, "error": "No message files found."}, ensure_ascii=False, indent=2))
        return 1

    report = analyze(load_rows(files), args.repeat_window, args.unanswered_followup_cap)
    if args.write_report:
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
