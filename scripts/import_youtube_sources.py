#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from project_paths import ROOT

RAW_DIR = ROOT / "couple_script_sample" / "raw"
MANIFEST_PATH = ROOT / "couple_script_sample" / "manifest.json"


def decode_text(text: str) -> str:
    return (
        (text or "")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def normalize_caption_events(transcript_json: dict) -> list:
    events = []
    for event in transcript_json.get("events", []):
        segs = event.get("segs") or []
        text = decode_text("".join((seg.get("utf8") or "") for seg in segs))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if re.fullmatch(r"\[[^\]]+\]", text):
            continue
        if text.startswith(("♪", "♬")):
            continue
        events.append(
            {
                "start_ms": event.get("tStartMs") or 0,
                "duration_ms": event.get("dDurationMs") or 0,
                "text": text,
            }
        )
    return events


def infer_lang(timedtext_url: str) -> str:
    query = parse_qs(urlparse(timedtext_url).query)
    return (query.get("lang") or ["unknown"])[0]


def load_manifest() -> list:
    if not MANIFEST_PATH.exists():
        return []
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save_manifest(rows: list) -> None:
    MANIFEST_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def import_video(video_id: str) -> dict:
    proc = subprocess.run(
        ["node", "scripts/get_youtube_timedtext_url.mjs", video_id],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout.strip())
    timedtext_url = payload.get("timedtextUrl") or ""
    transcript = payload.get("transcript")
    if not timedtext_url or not transcript:
        raise RuntimeError(f"missing transcript for {video_id}")

    transcript_json = json.loads(transcript)
    events = normalize_caption_events(transcript_json)
    if not events:
        raise RuntimeError(f"no usable caption events for {video_id}")

    lang = infer_lang(timedtext_url)
    raw_doc = {
        "video_id": video_id,
        "title": payload.get("title"),
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "lang": lang,
        "event_count": len(events),
        "events": events,
    }
    raw_path = RAW_DIR / f"{video_id}.json"
    raw_path.write_text(json.dumps(raw_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = [row for row in load_manifest() if row.get("video_id") != video_id]
    manifest.append(
        {
            "video_id": video_id,
            "title": payload.get("title"),
            "source_url": f"https://www.youtube.com/watch?v={video_id}",
            "lang": lang,
            "raw_file": f"raw/{video_id}.json",
            "event_count": len(events),
        }
    )
    manifest.sort(key=lambda row: row.get("video_id", ""))
    save_manifest(manifest)
    return {"video_id": video_id, "lang": lang, "event_count": len(events), "title": payload.get("title")}


def main() -> None:
    video_ids = sys.argv[1:]
    if not video_ids:
        raise SystemExit("usage: python3 scripts/import_youtube_sources.py <videoId> [<videoId> ...]")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    imported = []
    failed = []
    for video_id in video_ids:
        try:
            imported.append(import_video(video_id))
        except Exception as exc:
            failed.append({"video_id": video_id, "error": str(exc)})
    print(json.dumps({"imported": imported, "failed": failed}, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
