#!/usr/bin/env python3
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from project_paths import ROOT
SESSION_ENV = ROOT / "session" / "elevenlabs.env"
ROOT_ENV = ROOT / "elevenlabs.env"
VOICE_ROOT = ROOT / "voice-message"


def load_env_file() -> dict:
    path = SESSION_ENV if SESSION_ENV.exists() else ROOT_ENV
    if not path.exists():
        raise RuntimeError("elevenlabs env file not found")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def slugify(text: str) -> str:
    text = re.sub(r"[^0-9A-Za-z가-힣]+", "_", text.strip())
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:36] or "voice"


def speaking_text(text: str) -> str:
    normalized = text.strip()
    normalized = normalized.replace("ㅋㅋ", "").replace("ㅎㅎ", "")
    normalized = normalized.replace("..", ".")
    normalized = normalized.replace("~", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def synthesize(text: str, output_path: Path, env: dict) -> None:
    api_key = env.get("ELEVENLABS_API_KEY")
    voice_id = env.get("ELEVENLABS_VOICE_ID")
    model_id = env.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    output_format = env.get("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    if not api_key or not voice_id:
        raise RuntimeError("missing required elevenlabs settings")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={urllib.parse.quote(output_format)}"
    payload = {
        "text": speaking_text(text),
        "model_id": model_id,
        "language_code": "ko",
        "voice_settings": {
            "stability": float(env.get("ELEVENLABS_STABILITY", "0.42")),
            "similarity_boost": float(env.get("ELEVENLABS_SIMILARITY_BOOST", "0.82")),
            "style": float(env.get("ELEVENLABS_STYLE", "0.18")),
            "use_speaker_boost": env.get("ELEVENLABS_USE_SPEAKER_BOOST", "true").lower() == "true",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"elevenlabs_tts_http_{exc.code}: {body[:400]}") from exc
    output_path.write_bytes(audio)


def update_manifest(date_dir: Path, filename: str, text: str, env: dict) -> None:
    manifest_path = date_dir / "INDEX.md"
    lines = [
        f"# {date_dir.name} Voice Messages",
        "",
        "## Files",
        "",
    ]
    entries = []
    if manifest_path.exists():
        existing = manifest_path.read_text(encoding="utf-8").splitlines()
        marker = "## Files"
        if marker in existing:
            idx = existing.index(marker)
            entries = existing[idx + 2 :]
    timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
    entries.append(f"- `{filename}`")
    entries.append(f"  - created_at: `{timestamp}`")
    entries.append(f"  - engine: `elevenlabs`")
    entries.append(f"  - model: `{env.get('ELEVENLABS_MODEL_ID', 'eleven_multilingual_v2')}`")
    entries.append(
        "  - settings: "
        f"`stability={env.get('ELEVENLABS_STABILITY', '0.42')}` / "
        f"`similarity={env.get('ELEVENLABS_SIMILARITY_BOOST', '0.82')}` / "
        f"`style={env.get('ELEVENLABS_STYLE', '0.18')}` / "
        f"`speaker_boost={env.get('ELEVENLABS_USE_SPEAKER_BOOST', 'true')}`"
    )
    entries.append(f"  - text: {text}")
    entries.append("")
    manifest_path.write_text("\n".join(lines + entries).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--label", default="sample")
    args = parser.parse_args()

    env = load_env_file()
    now = datetime.now().astimezone()
    date_dir = VOICE_ROOT / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%H%M%S')}_{slugify(args.label)}.mp3"
    output_path = date_dir / filename

    synthesize(args.text, output_path, env)
    update_manifest(date_dir, filename, args.text, env)

    print(
        json.dumps(
            {
                "ok": True,
                "path": str(output_path),
                "size_bytes": output_path.stat().st_size,
                "manifest": str(date_dir / "INDEX.md"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
