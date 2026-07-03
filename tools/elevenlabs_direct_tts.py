#!/usr/bin/env python3
"""TTS 생성 전용 — 파일 저장만 하고 Telegram 전송 없음. 영상용 오디오 생성에 사용."""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env(state_dir: Path) -> dict:
    env = {}
    for path in [state_dir / "elevenlabs.env", state_dir / ".env"]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    env = load_env(Path(args.state_dir))
    api_key = env.get("ELEVENLABS_API_KEY")
    voice_id = env.get("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        print(json.dumps({"ok": False, "error": "missing api key or voice id"}), file=sys.stderr)
        return 1

    payload = {
        "text": args.text,
        "model_id": env.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
        "language_code": "ko",
        "voice_settings": {
            "stability": float(env.get("ELEVENLABS_STABILITY", "0.42")),
            "similarity_boost": float(env.get("ELEVENLABS_SIMILARITY_BOOST", "0.82")),
            "style": float(env.get("ELEVENLABS_STYLE", "0.18")),
            "use_speaker_boost": env.get("ELEVENLABS_USE_SPEAKER_BOOST", "true").lower() == "true",
            "speed": float(env.get("ELEVENLABS_SPEED", "1.0")),
        },
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(resp.read())
        print(json.dumps({"ok": True, "path": str(out)}))
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({"ok": False, "error": f"http_{exc.code}: {body[:200]}"}), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
