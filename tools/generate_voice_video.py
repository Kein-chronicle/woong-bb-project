#!/usr/bin/env python3
"""
음성 포함 영상 생성 스크립트.
흐름: ElevenLabs TTS → Higgsfield 업로드 → Wan 2.7 영상 생성 → 다운로드 → Telegram 전송
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path("/Users/kein/Projects/woong-bb")
STATE_DIR = ROOT / "session"
VIDEO_DIR = ROOT / "videos" / "generated"


def load_env() -> dict:
    env = {}
    for p in [STATE_DIR / "elevenlabs.env", STATE_DIR / ".env"]:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    return env


def log(msg: str) -> None:
    print(f"[generate_voice_video] {msg}", flush=True)


# ── ElevenLabs TTS ────────────────────────────────────────────────────────────

def generate_tts(text: str, output_path: Path, env: dict) -> bool:
    api_key = env.get("ELEVENLABS_API_KEY")
    voice_id = env.get("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        log("TTS error: missing api key or voice id")
        return False
    payload = {
        "text": text,
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
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(resp.read())
        log(f"TTS saved: {output_path}")
        return True
    except Exception as exc:
        log(f"TTS failed: {exc}")
        return False


# ── Higgsfield HTTP helpers ───────────────────────────────────────────────────

HIGGS_BASE = "https://api.higgsfield.ai"


def _higgs_headers() -> dict:
    # Higgsfield MCP는 OAuth 기반 — 토큰은 MCP 세션에서만 사용 가능.
    # 여기서는 MCP CLI를 경유하는 대신 codex 툴 호출 지시를 출력한다.
    return {}


def higgs_upload_and_confirm(file_path: Path, media_type: str) -> str | None:
    """
    MCP를 직접 호출할 수 없어서, codex가 실행할 bash 명령들을 stdout에 출력.
    실제 실행은 codex가 한다.
    """
    # 이 함수는 직접 HTTP를 쏘는 대신 codex 지시를 생성하는 용도로 전환.
    return None


# ── 전체 파이프라인 (MCP 없는 버전) ────────────────────────────────────────

def generate_tts_only(text: str, label: str = "vid") -> Optional[Path]:
    """TTS만 생성하고 경로 반환."""
    env = load_env()
    today = time.strftime("%Y-%m-%d")
    audio_dir = ROOT / "voice-message" / today
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{label}_{time.strftime('%H%M%S')}.mp3"
    if generate_tts(text, audio_path, env):
        return audio_path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="음성 포함 영상 생성")
    parser.add_argument("--text", required=True, help="TTS 텍스트")
    parser.add_argument("--image", required=True, help="start_image 경로 (imagegen 결과)")
    parser.add_argument("--prompt", default="young woman looking at camera, natural selfie, slight movement, talking", help="영상 프롬프트")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--tts-only", action="store_true", help="TTS만 생성하고 경로 출력")
    args = parser.parse_args()

    env = load_env()
    today = time.strftime("%Y-%m-%d")

    # TTS 생성
    audio_dir = ROOT / "voice-message" / today
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"vid_{time.strftime('%H%M%S')}.mp3"
    if not generate_tts(args.text, audio_path, env):
        return 1

    if args.tts_only:
        print(json.dumps({"ok": True, "audio_path": str(audio_path)}))
        return 0

    image_path = Path(args.image)
    if not image_path.exists():
        log(f"image not found: {image_path}")
        return 1

    # MCP 명령어를 stdout으로 출력 — codex가 이를 읽고 실행
    instructions = {
        "ok": True,
        "audio_path": str(audio_path),
        "image_path": str(image_path),
        "video_dir": str(VIDEO_DIR / today),
        "prompt": args.prompt,
        "duration": args.duration,
        "next_steps": [
            f"1. mcp__higgsfield__media_upload filename='voice.mp3'",
            f"2. curl -sS -X PUT '<upload_url>' --data-binary @{audio_path} -H 'Content-Type: audio/mpeg'",
            f"3. mcp__higgsfield__media_confirm media_id=<audio_id> type='audio'",
            f"4. mcp__higgsfield__media_upload filename='frame.png'",
            f"5. curl -sS -X PUT '<upload_url>' --data-binary @{image_path} -H 'Content-Type: image/png'",
            f"6. mcp__higgsfield__media_confirm media_id=<img_id> type='image'",
            f"7. mcp__higgsfield__generate_video model='wan2_7' prompt='{args.prompt}' duration={args.duration} medias=[{{role:'start_image',value:<img_id>}},{{role:'audio',value:<audio_id>}}]",
            f"8. mcp__higgsfield__job_status jobId=<job_id> sync=true  (미완료시 반복)",
            f"9. mkdir -p {VIDEO_DIR / today} && curl -sL '<mp4_url>' -o {VIDEO_DIR / today}/hf_$(date +%H%M%S).mp4",
            f"10. python3 /Users/kein/.codex/skills/telegram-image-send/scripts/send_telegram_video.py --state-dir {STATE_DIR} --video <video_path>",
        ],
    }
    print(json.dumps(instructions, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    # Optional import fix
    from typing import Optional
    sys.exit(main())
