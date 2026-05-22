#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from xml.sax.saxutils import escape

from project_paths import ROOT

SESSION_ENV = ROOT / "session" / "azure-speech.env"
ROOT_ENV = ROOT / "azure-speech.env"
VOICE_ROOT = ROOT / "voice-message"


def load_env_file() -> dict:
    path = SESSION_ENV if SESSION_ENV.exists() else ROOT_ENV
    if not path.exists():
        raise RuntimeError("azure speech env file not found")
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


def build_ssml(text: str, env: dict) -> str:
    locale = env.get("AZURE_SPEECH_LOCALE", "ko-KR")
    voice = env.get("AZURE_SPEECH_VOICE", "ko-KR-SunHiNeural")
    rate = env.get("AZURE_SPEECH_RATE", "-3%")
    pitch = env.get("AZURE_SPEECH_PITCH", "0%")
    volume = env.get("AZURE_SPEECH_VOLUME", "medium")
    spoken = speaking_text(text)
    spoken = spoken.replace(". ", '. <break time="360ms"/> ')
    spoken = spoken.replace("? ", '? <break time="280ms"/> ')
    spoken = spoken.replace("! ", '! <break time="260ms"/> ')
    safe_text = escape(spoken).replace('&lt;break time="360ms"/&gt;', '<break time="360ms"/>') \
                              .replace('&lt;break time="280ms"/&gt;', '<break time="280ms"/>') \
                              .replace('&lt;break time="260ms"/&gt;', '<break time="260ms"/>')
    return (
        f'<speak version="1.0" xml:lang="{locale}">'
        f'<voice name="{voice}">'
        f'<prosody rate="{rate}" pitch="{pitch}" volume="{volume}">{safe_text}</prosody>'
        f"</voice>"
        f"</speak>"
    )


def synthesize(text: str, output_path: Path, env: dict) -> None:
    key = env.get("AZURE_SPEECH_KEY")
    region = env.get("AZURE_SPEECH_REGION")
    fmt = env.get("AZURE_SPEECH_OUTPUT_FORMAT", "audio-24khz-48kbitrate-mono-mp3")
    if not key or not region:
        raise RuntimeError("missing required azure speech settings")
    raw_endpoint = env.get("AZURE_SPEECH_ENDPOINT", "").strip()
    if raw_endpoint and "tts.speech.microsoft.com" in raw_endpoint:
        endpoint = raw_endpoint.rstrip("/")
        if not endpoint.endswith("/cognitiveservices/v1"):
            endpoint = endpoint + "/cognitiveservices/v1"
    else:
        endpoint = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    data = build_ssml(text, env).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, method="POST")
    req.add_header("Ocp-Apim-Subscription-Key", key)
    req.add_header("Content-Type", "application/ssml+xml")
    req.add_header("X-Microsoft-OutputFormat", fmt)
    req.add_header("User-Agent", "woong-bb-azure-tts")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"azure_tts_http_{exc.code}: {body[:300]}") from exc
    output_path.write_bytes(audio)


def update_manifest(date_dir: Path, filename: str, text: str, env: dict) -> None:
    manifest_path = date_dir / "INDEX.md"
    lines = [
        f"# {date_dir.name} Voice Messages",
        "",
        f"- voice: `{env.get('AZURE_SPEECH_VOICE', 'ko-KR-SunHiNeural')}`",
        f"- locale: `{env.get('AZURE_SPEECH_LOCALE', 'ko-KR')}`",
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
    entries.append(f"  - voice: `{env.get('AZURE_SPEECH_VOICE', 'ko-KR-SunHiNeural')}`")
    entries.append(f"  - rate/pitch/volume: `{env.get('AZURE_SPEECH_RATE', '-3%')}` / `{env.get('AZURE_SPEECH_PITCH', '0%')}` / `{env.get('AZURE_SPEECH_VOLUME', 'medium')}`")
    entries.append(f"  - text: {text}")
    entries.append("")
    manifest_path.write_text("\n".join(lines + entries).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--label", default="sample")
    parser.add_argument("--voice")
    parser.add_argument("--rate")
    parser.add_argument("--pitch")
    parser.add_argument("--volume")
    args = parser.parse_args()

    env = load_env_file()
    if args.voice:
        env["AZURE_SPEECH_VOICE"] = args.voice
    if args.rate:
        env["AZURE_SPEECH_RATE"] = args.rate
    if args.pitch:
        env["AZURE_SPEECH_PITCH"] = args.pitch
    if args.volume:
        env["AZURE_SPEECH_VOLUME"] = args.volume
    now = datetime.now().astimezone()
    date_dir = VOICE_ROOT / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%H%M%S')}_{slugify(args.label)}.mp3"
    output_path = date_dir / filename

    synthesize(args.text, output_path, env)
    update_manifest(date_dir, filename, args.text, env)

    result = {
        "ok": True,
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "manifest": str(date_dir / "INDEX.md"),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
