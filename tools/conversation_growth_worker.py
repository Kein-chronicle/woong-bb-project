#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from project_paths import ROOT, log_path
STATE = ROOT / "state"
REGISTRY_PATH = STATE / "conversation_source_registry.json"
WORKER_STATE_PATH = STATE / "conversation_growth_worker_state.json"
LEARNING_STATE_PATH = STATE / "conversation_learning_state.json"
APPROVED_PATH = STATE / "approved_conversation_patterns.json"
REJECTED_PATH = STATE / "rejected_conversation_patterns.json"
CATALOG_PATH = STATE / "conversation_pattern_catalog.json"
COUPLE_SAMPLE_DIR = ROOT / "couple_script_sample"
MANIFEST_PATH = COUPLE_SAMPLE_DIR / "manifest.json"
BUILD_COUPLE_SCRIPT = ROOT / "scripts" / "build_couple_script_sample.mjs"
BUILD_CATALOG_SCRIPT = ROOT / "scripts" / "build_conversation_pattern_catalog.py"
LEARNING_LOOP_SCRIPT = ROOT / "tools" / "conversation_learning_loop.py"
DECISION_LOG_PATH = log_path("response_decision_log.jsonl")

DISCOVERY_QUERIES = [
    "커플 브이로그 대화",
    "신혼부부 Q&A 유튜브",
    "장기연애 커플 토크",
    "couple q&a relationship youtube",
    "real couple conversation vlog",
    "relationship advice forum",
]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
}


def now_local() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def parse_iso(text: str):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def ensure_state_files() -> None:
    load_json(REGISTRY_PATH, {})
    load_json(LEARNING_STATE_PATH, {})
    load_json(APPROVED_PATH, {})
    load_json(REJECTED_PATH, {})
    load_json(CATALOG_PATH, {})


def should_run(last_at: str, interval_hours: int) -> bool:
    parsed = parse_iso(last_at)
    if not parsed:
        return True
    return now_local() - parsed >= timedelta(hours=interval_hours)


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        return url
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def score_candidate(url: str) -> float:
    lowered = url.lower()
    score = 0.2
    if "youtube.com" in lowered:
        score += 0.45
    if "reddit.com" in lowered:
        score += 0.35
    if "archiveofourown.org" in lowered:
        score += 0.2
    if "pann.nate.com" in lowered:
        score += 0.25
    if "relationship" in lowered or "couple" in lowered or "romance" in lowered:
        score += 0.15
    return round(min(score, 0.99), 2)


def classify_source(url: str) -> tuple:
    lowered = url.lower()
    if "youtube.com" in lowered:
        return ("youtube_search_candidate", "couple_dialogue_video", "multi")
    if "reddit.com" in lowered:
        return ("reddit_candidate", "relationship_advice", "en")
    if "archiveofourown.org" in lowered:
        return ("ao3_candidate", "fiction_dialogue", "en")
    if "pann.nate.com" in lowered:
        return ("pann_candidate", "community_relationship", "ko")
    return ("web_candidate", "unknown", "unknown")


def discover_registry_candidates(registry: dict) -> dict:
    existing = {row.get("base_url"): row for row in registry.get("sources", [])}
    discovered = []
    for query in DISCOVERY_QUERIES:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        try:
            html = fetch_text(url)
        except Exception:
            continue
        raw_urls = re.findall(r'nofollow" class="[^"]*" href="([^"]+)"', html)
        for raw in raw_urls:
            if "uddg=" in raw:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("uddg", [])
                candidate_url = parsed[0] if parsed else raw
            else:
                candidate_url = raw
            candidate_url = urllib.parse.unquote(candidate_url)
            candidate_url = normalize_url(candidate_url)
            if not candidate_url.startswith("http"):
                continue
            if candidate_url in existing:
                continue
            source_id, content_type, language = classify_source(candidate_url)
            row = {
                "source_id": f"{source_id}_{abs(hash(candidate_url)) % 10_000_000}",
                "site_name": candidate_url.split("/")[2],
                "base_url": candidate_url,
                "content_type": content_type,
                "language": language,
                "status": "watch",
                "collection_interval_minutes": 720,
                "priority_score": score_candidate(candidate_url),
                "notes": f"discovered_by_query:{query}",
            }
            existing[candidate_url] = row
            discovered.append(row)

    sources = sorted(existing.values(), key=lambda row: (row.get("status") != "active", -float(row.get("priority_score", 0))), reverse=False)
    sources = sorted(sources, key=lambda row: (0 if row.get("status") == "active" else 1, -float(row.get("priority_score", 0))))
    registry["sources"] = sources[:20]
    registry["updated_at"] = now_iso()
    return {"registry": registry, "discovered": discovered[:20]}


def run_command(args: list, timeout: int = None) -> dict:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def extract_json_block(text: str) -> dict:
    body = (text or "").strip()
    if not body:
        return {}
    for idx, char in enumerate(body):
        if char != "{":
            continue
        candidate = body[idx:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def refresh_youtube_corpus() -> dict:
    if not BUILD_COUPLE_SCRIPT.exists():
        return {"ok": False, "reason": "missing_build_couple_script"}
    result = run_command(["node", str(BUILD_COUPLE_SCRIPT)], timeout=1800)
    result["manifest_count"] = len(load_json(MANIFEST_PATH, []))
    return result


def refresh_catalog_and_review(limit_per_category: int) -> dict:
    build_result = run_command(["python3", str(BUILD_CATALOG_SCRIPT)], timeout=600)
    review_result = run_command(
        [
            "python3",
            str(LEARNING_LOOP_SCRIPT),
            "review-candidates",
            "--limit-per-category",
            str(limit_per_category),
            "--rebuild-catalog",
        ],
        timeout=900,
    )
    parsed_review = {}
    if review_result["stdout"]:
        parsed_review = extract_json_block(review_result["stdout"])
    return {
        "build_result": build_result,
        "review_result": review_result,
        "parsed_review": parsed_review,
    }


def perform_tick(run_registry_refresh: bool, run_youtube_refresh: bool, limit_per_category: int) -> dict:
    ensure_state_files()
    worker_state = load_json(WORKER_STATE_PATH, {
        "schema_version": 1,
        "managed_by": "conversation_growth_worker",
        "updated_at": None,
        "last_tick_at": None,
        "last_registry_refresh_at": None,
        "last_youtube_refresh_at": None,
        "last_catalog_review_at": None,
        "last_status": "idle",
        "last_result": {},
        "errors": [],
        "notes": "인터넷 기반 대화 학습 성장 워커 실행 상태",
    })
    registry = load_json(REGISTRY_PATH, {"schema_version": 1, "managed_by": "conversation_learning_loop", "updated_at": None, "sources": []})
    summary = {
        "tick_at": now_iso(),
        "registry_refreshed": False,
        "youtube_refreshed": False,
        "catalog_reviewed": False,
        "discovered_source_count": 0,
        "approved_pattern_count": 0,
        "rejected_pattern_count": 0,
    }

    if run_registry_refresh:
        discovered = discover_registry_candidates(registry)
        registry = discovered["registry"]
        save_json(REGISTRY_PATH, registry)
        worker_state["last_registry_refresh_at"] = now_iso()
        summary["registry_refreshed"] = True
        summary["discovered_source_count"] = len(discovered["discovered"])

    if run_youtube_refresh:
        youtube_result = refresh_youtube_corpus()
        summary["youtube_refresh_result"] = youtube_result
        summary["youtube_refreshed"] = youtube_result.get("ok", False)
        worker_state["last_youtube_refresh_at"] = now_iso()

    review_summary = refresh_catalog_and_review(limit_per_category=limit_per_category)
    summary["catalog_reviewed"] = True
    summary["catalog_review_result"] = review_summary
    parsed_review = review_summary.get("parsed_review") or {}
    summary["approved_pattern_count"] = parsed_review.get("approved_count", 0)
    summary["rejected_pattern_count"] = parsed_review.get("rejected_count", 0)
    worker_state["last_catalog_review_at"] = now_iso()

    approved = load_json(APPROVED_PATH, {"patterns": []})
    rejected = load_json(REJECTED_PATH, {"patterns": []})
    catalog = load_json(CATALOG_PATH, {"dataset_summary": {}})
    summary["approved_pattern_total"] = len(approved.get("patterns", []))
    summary["rejected_pattern_total"] = len(rejected.get("patterns", []))
    summary["catalog_dataset_summary"] = catalog.get("dataset_summary", {})

    worker_state["updated_at"] = now_iso()
    worker_state["last_tick_at"] = now_iso()
    worker_state["last_status"] = "ok"
    worker_state["last_result"] = summary
    save_json(WORKER_STATE_PATH, worker_state)
    append_jsonl(
        DECISION_LOG_PATH,
        {
            "timestamp": now_iso(),
            "decision_type": "conversation_growth_tick",
            **summary,
        },
    )
    return summary


def cmd_tick(args) -> int:
    summary = perform_tick(
        run_registry_refresh=args.with_registry_refresh,
        run_youtube_refresh=args.with_youtube_refresh,
        limit_per_category=args.limit_per_category,
    )
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False, indent=2))
    return 0


def cmd_status(_args) -> int:
    state = load_json(WORKER_STATE_PATH, {})
    print(json.dumps({"ok": True, "state": state}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="conversation growth worker")
    sub = parser.add_subparsers(dest="command", required=True)
    tick = sub.add_parser("tick")
    tick.add_argument("--with-registry-refresh", action="store_true", default=False)
    tick.add_argument("--with-youtube-refresh", action="store_true", default=False)
    tick.add_argument("--limit-per-category", type=int, default=4)
    sub.add_parser("status")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "tick":
        return cmd_tick(args)
    if args.command == "status":
        return cmd_status(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
