#!/usr/bin/env python3
"""
photo_delivery_guard.py
브리지 레벨 snapshot/diff 대안:
worker 실행 전 PNG 목록 스냅샷 → 실행 후 신규 PNG 탐지 → sendPhoto 강제.

Usage:
  python3 photo_delivery_guard.py snapshot      # 실행 전 호출
  python3 photo_delivery_guard.py check-and-send  # 실행 후 호출

worker 프롬프트의 BEFORE_SNAP/find diff 방식을 브리지 책임으로 이관하는 대안.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

GENERATED_DIR = Path.home() / ".codex" / "generated_images"
STAGING_BASE  = Path("/Users/kein/Projects/woong-bb/images/generated")
SNAP_PATH     = Path("/Users/kein/Desktop/woong-bb/state/photo_snap_before.json")
STATE_DIR     = Path("/Users/kein/Projects/woong-bb/session")
SEND_SCRIPT   = Path("/Users/kein/.codex/skills/telegram-image-send/scripts/send_telegram_photo.py")
REGISTRY_PATH = STATE_DIR / "sent_images_registry.json"

# 로컬 이미지 API 폴백 (우선순위2) — 모든 경로(직접요청·선톡·약속) 공통 초크포인트에서 동작
STATE_BASE        = Path("/Users/kein/Projects/woong-bb/state")
IMAGE_SETTINGS_PATH = STATE_BASE / "image_generation_settings.json"
DAILY_SCHEDULE_PATH = STATE_BASE / "daily_schedule_state.json"
LOCAL_IMAGE_API_BASE = "http://172.30.1.71:7860"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 코덱스 세션 롤아웃에서 이미지 추출 (codex 0.141+ : image_gen이 파일 대신
#    이벤트 result에 base64로 반환 → generated_images 폴더 diff가 빈손이 됨) ──
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


def _parse_iso(s):
    """ISO8601 파싱 (Z 접미사 포함, py3.9 호환). 실패 시 None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _png_ok(raw) -> bool:
    return bool(raw) and len(raw) > 50000 and raw[:8] == b"\x89PNG\r\n\x1a\n"


ACTIVE_SESSION_ID_FILE = STATE_DIR / "codex-session.woongbbi.id"


def _active_session_id():
    """현재 woongbbi 코덱스 세션 id (롤아웃 파일명에 그대로 포함됨)."""
    try:
        sid = ACTIVE_SESSION_ID_FILE.read_text().strip()
        return sid or None
    except Exception:
        return None


def _candidate_rollouts() -> list:
    """스캔 대상 롤아웃 파일 목록. 활성 세션 파일을 최우선, 그 다음 최근 수정순."""
    import glob
    if not CODEX_SESSIONS_DIR.exists():
        return []
    files = glob.glob(str(CODEX_SESSIONS_DIR / "**" / "rollout-*.jsonl"), recursive=True)
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    sid = _active_session_id()
    if sid:
        pinned = [f for f in files if sid in os.path.basename(f)]
        others = [f for f in files if sid not in os.path.basename(f)]
        return pinned + others[:4]
    return files[:5]


def _scan_rollout_for_image(fp, after_dt):
    """롤아웃 1개에서 after_dt 이후 생성된 마지막 image_gen 결과(base64) → PNG bytes."""
    import base64
    latest = None
    try:
        with open(fp, errors="ignore") as fh:
            for line in fh:
                if "image_generation" not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                p = o.get("payload", {})
                if p.get("type") not in ("image_generation_end", "image_generation_call"):
                    continue
                res = p.get("result")
                if not res:
                    continue
                if after_dt:
                    edt = _parse_iso(o.get("timestamp", ""))
                    if edt and edt <= after_dt:
                        continue
                latest = res
    except Exception:
        return None
    if not latest:
        return None
    try:
        raw = base64.b64decode(latest)
    except Exception:
        return None
    return raw if _png_ok(raw) else None


def extract_rollout_image(after_dt):
    """활성 코덱스 세션 롤아웃에서 after_dt 이후 생성된 image_gen 결과(base64)를
    디코딩해 PNG bytes 반환. 활성 세션을 못 찾으면 최근 세션으로 폴백. 없으면 None.
    (codex 0.141+ : image_gen이 파일 대신 이벤트 result에 이미지를 담는다)"""
    for fp in _candidate_rollouts():
        raw = _scan_rollout_for_image(fp, after_dt)
        if raw:
            return raw
    return None


def _send_png_bytes(raw: bytes, source: str, trigger_kind: str) -> bool:
    """PNG bytes를 staging 저장 → sendPhoto → registry 기록. 성공 시 True."""
    today = datetime.now().strftime("%Y-%m-%d")
    staged_dir = STAGING_BASE / today
    staged_dir.mkdir(parents=True, exist_ok=True)
    dest = staged_dir / f"{datetime.now().strftime('%H%M%S')}_{source}.png"
    try:
        dest.write_bytes(raw)
    except Exception as e:
        print(f"{source} staging 실패: {e}")
        return False
    result = subprocess.run(
        [sys.executable, str(SEND_SCRIPT), "--state-dir", str(STATE_DIR), "--image", str(dest)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"{source} sendPhoto 실패 (exit {result.returncode}): {result.stderr[:150]}")
        return False
    try:
        registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
        registry[str(dest)] = {
            "sent_at": now_iso(), "source": source,
            "staged_path": str(dest), "trigger_kind": trigger_kind,
        }
        REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2))
    except Exception:
        pass
    update_pending_status("succeeded")
    print(f"OK: {source} 전송 성공: {dest}")
    return True


def rollout_fallback(trigger_kind: str, after_dt) -> bool:
    """우선순위1.5: 코덱스 세션 롤아웃에서 image_gen 결과 추출 → 전송. 성공 시 True.
    롤아웃 append 지연 대비 1회 재시도."""
    import time
    raw = extract_rollout_image(after_dt)
    if not raw:
        time.sleep(1.5)
        raw = extract_rollout_image(after_dt)
    if not raw:
        return False
    return _send_png_bytes(raw, "codex_rollout", trigger_kind)


def cmd_send_rollout(after_epoch_ms=None, trigger_kind="direct_request"):
    """브릿지 위임용: 스냅샷 없이 코덱스 롤아웃 base64에서 최근 image_gen 결과를
    추출해 전송. (codex 0.141+ 파일 미생성 → 브릿지 findLatestGeneratedImage가
    항상 빈손이 되는 문제의 단일 전송 진실원천.)
    after_epoch_ms 이후 생성분만 대상(배치 시작 시각 전달, 15초 버퍼). 성공 시 exit 0."""
    from datetime import timedelta
    if after_epoch_ms is not None:
        after_dt = datetime.fromtimestamp(after_epoch_ms / 1000).astimezone() - timedelta(seconds=15)
    else:
        after_dt = datetime.now().astimezone() - timedelta(minutes=5)
    if rollout_fallback(trigger_kind, after_dt):
        return
    print("send-rollout: 롤아웃에서 신규 image_gen 결과 없음")
    sys.exit(1)


def get_all_pngs() -> list:
    """~/.codex/generated_images 전체 PNG 목록 반환."""
    pngs = []
    if GENERATED_DIR.exists():
        for root, _, files in os.walk(GENERATED_DIR):
            for f in files:
                if f.endswith(".png"):
                    pngs.append(str(Path(root) / f))
    return sorted(pngs)


def cmd_snapshot():
    """worker 실행 전: 현재 PNG 목록 저장."""
    pngs = get_all_pngs()
    snap = {"snapped_at": now_iso(), "files": pngs}
    SNAP_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2))
    print(f"snapshot: {len(pngs)}개 기록됨")


PENDING_PHOTO_PATH = Path("/Users/kein/Desktop/woong-bb/state/pending_proactive_photo.json")

FAIL_CODES = {
    "no_snap": "image_gen_not_called",
    "no_new_png": "image_gen_not_called",
    "staging_failed": "staging_copy_failed",
    "sendphoto_failed": "sendphoto_failed",
    "registry_failed": "registry_write_failed",
}


def update_pending_status(status: str, fail_code: str = "") -> None:
    try:
        data = json.loads(PENDING_PHOTO_PATH.read_text()) if PENDING_PHOTO_PATH.exists() else {}
        data["status"] = status
        data["resolved_at"] = now_iso()
        if fail_code:
            data["fail_code"] = fail_code
        elif "fail_code" in data:
            del data["fail_code"]
        PENDING_PHOTO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _local_api_health_ok() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(LOCAL_IMAGE_API_BASE + "/api/health", timeout=8) as r:
            return getattr(r, "status", 200) == 200
    except Exception:
        return False


LAST_PHOTO_REQUEST_CONTEXT_PATH = STATE_DIR / "last_photo_request_context.json"
_REQUEST_CONTEXT_MAX_AGE_MIN = 10


def _read_request_context_hint() -> str:
    """codex-telegram-woongbbi-worker가 남긴 원 요청 텍스트를 읽는다.
    ReActor는 얼굴 없인 못 도니, 씬은 항상 셀카 포맷을 유지하되 이 텍스트를 곁들여서
    실패한 원래 요청(예: '라면 사진')과 무관한 랜덤 셀카가 나가는 걸 줄인다."""
    try:
        if not LAST_PHOTO_REQUEST_CONTEXT_PATH.exists():
            return ""
        data = json.loads(LAST_PHOTO_REQUEST_CONTEXT_PATH.read_text())
        text = str(data.get("text") or "").strip()
        at = _parse_iso(data.get("at"))
        if not text or not at:
            return ""
        age_min = (datetime.now().astimezone() - at).total_seconds() / 60
        if age_min > _REQUEST_CONTEXT_MAX_AGE_MIN:
            return ""
        return text[:80]
    except Exception:
        return ""


def _build_local_scene(context_hint: str = "") -> str:
    """오늘 셋업 의상 + 시간대 + 롱헤어로 일상 바스트 셀피 scene (얼굴 크게=화질 안정, 레벨2).
    ReActor는 얼굴 스왑 기반이라 셀카 포맷 자체는 못 벗어남 — 원 요청 맥락은 곁들이는 정도로만 반영."""
    outfit = "casual summer homewear, oversized white t-shirt"
    try:
        sched = json.loads(DAILY_SCHEDULE_PATH.read_text()) if DAILY_SCHEDULE_PATH.exists() else {}
        o = (sched.get("morning", {}) or {}).get("outfit", "")
        if "민소매" in o:
            outfit = "sleeveless top, casual summer homewear"
        elif "후디" in o:
            outfit = "loose hoodie, casual homewear"
        elif "반팔" in o or "티셔츠" in o:
            outfit = "oversized white t-shirt, casual summer homewear"
    except Exception:
        pass
    hour = datetime.now().hour
    if hour < 11:
        setting = "cozy bedroom, soft morning light"
    elif hour < 18:
        setting = "home interior, natural daylight"
    else:
        setting = "home interior, warm evening light"
    scene = (f"long straight black hair, {outfit}, {setting}, bust shot, front facing, "
             "natural warm smile, looking at camera, highly detailed face, sharp focus")
    # 로컬 모델(ReActor 얼굴스왑)은 사람 셀카만 안정적으로 뽑음.
    # 원 요청의 구체 상황/오브젝트(예: '라면 사진', '지하철에서')를 씬에 주입하면
    # 사람 아닌 장면·소품을 억지로 그리다 퀄리티가 무너지므로 context_hint는 반영하지 않는다.
    return scene


def _generate_via_local_api(scene: str):
    import urllib.request
    import base64
    neg = ("innerwear, lingerie, underwear, naked, nsfw, short hair, bob cut, blurry, low quality, "
           "food, objects, props, text, complex background, crowd, multiple people, vehicle interior")
    payload = json.dumps({
        "scene": scene, "face_swap": True, "seed": -1, "mode": "daily",
        "width": 832, "height": 1216, "negative": neg, "negative_prompt": neg,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        LOCAL_IMAGE_API_BASE + "/api/reactor", data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8"))
        b64 = data.get("image")
        return base64.b64decode(b64) if b64 else None
    except Exception as e:
        print(f"local api generate fail: {str(e)[:150]}")
        return None


def local_api_fallback(trigger_kind: str) -> bool:
    """우선순위2: 로컬 이미지 API로 생성→스테이징→sendPhoto. 성공 시 True."""
    try:
        settings = json.loads(IMAGE_SETTINGS_PATH.read_text()) if IMAGE_SETTINGS_PATH.exists() else {}
    except Exception:
        settings = {}
    if not settings.get("generation_enabled", True):
        return False
    if not _local_api_health_ok():
        print("local api health 실패 — 폴백 skip")
        return False
    png = _generate_via_local_api(_build_local_scene())
    if not png:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    staged_dir = STAGING_BASE / today
    staged_dir.mkdir(parents=True, exist_ok=True)
    dest = staged_dir / f"{datetime.now().strftime('%H%M%S')}_localapi.png"
    try:
        dest.write_bytes(png)
    except Exception as e:
        print(f"local api staging 실패: {e}")
        return False
    result = subprocess.run(
        [sys.executable, str(SEND_SCRIPT), "--state-dir", str(STATE_DIR), "--image", str(dest)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"local api sendPhoto 실패 (exit {result.returncode}): {result.stderr[:150]}")
        return False
    try:
        registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
        registry[str(dest)] = {
            "sent_at": now_iso(), "source": "local_api_fallback",
            "staged_path": str(dest), "trigger_kind": trigger_kind,
        }
        REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2))
    except Exception:
        pass
    update_pending_status("succeeded")
    print(f"OK: 로컬 API 폴백 전송 성공: {dest}")
    return True


def cmd_check_and_send(trigger_kind: str = "direct_request"):
    """worker 실행 후: 신규 PNG 탐지 → staging 복사 → sendPhoto.
    신규 PNG가 없으면(기존 imagegen 미호출/실패) 로컬 이미지 API로 폴백."""
    if not SNAP_PATH.exists():
        print("snapshot 없음 — 세션 기록 추출 시도")
        from datetime import timedelta
        if rollout_fallback(trigger_kind, datetime.now().astimezone() - timedelta(minutes=5)):
            return
        print("세션 기록 추출 실패 — 로컬 API 폴백 시도")
        if local_api_fallback(trigger_kind):
            return
        update_pending_status("failed", FAIL_CODES["no_snap"])
        sys.exit(1)

    snap = json.loads(SNAP_PATH.read_text())
    old_files = set(snap.get("files", []))
    new_files = [f for f in get_all_pngs() if f not in old_files]

    if not new_files:
        # codex 0.141+ : image_gen이 파일을 안 떨굼 → 세션 기록 base64에서 추출
        print("신규 PNG 없음(폴더) — 코덱스 세션 기록에서 추출 시도")
        after_dt = _parse_iso(snap.get("snapped_at"))
        SNAP_PATH.unlink(missing_ok=True)
        if rollout_fallback(trigger_kind, after_dt):
            return
        print("세션 기록 추출 실패 — 로컬 API 폴백 시도")
        if local_api_fallback(trigger_kind):
            return
        update_pending_status("failed", FAIL_CODES["no_new_png"])
        sys.exit(1)

    # 최신 파일 1개 선택
    newest = sorted(new_files)[-1]

    # staging 복사
    today = datetime.now().strftime("%Y-%m-%d")
    staged_dir = STAGING_BASE / today
    staged_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    dest = staged_dir / f"{ts}_generated.png"
    import shutil
    try:
        shutil.copy2(newest, dest)
        print(f"staging: {dest}")
    except Exception as e:
        print(f"FAIL: staging 실패: {e}")
        update_pending_status("failed", FAIL_CODES["staging_failed"])
        SNAP_PATH.unlink(missing_ok=True)
        sys.exit(1)

    # sendPhoto 호출
    result = subprocess.run(
        [sys.executable, str(SEND_SCRIPT), "--state-dir", str(STATE_DIR), "--image", str(dest)],
        capture_output=True, text=True, timeout=30,
    )
    SNAP_PATH.unlink(missing_ok=True)
    if result.returncode == 0:
        print(f"OK: sendPhoto 성공: {dest}")
        try:
            registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
            registry[str(dest)] = {
                "sent_at": now_iso(),
                "source_path": newest,
                "staged_path": str(dest),
                "trigger_kind": trigger_kind,
            }
            REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2))
        except Exception:
            pass
        update_pending_status("succeeded")
    else:
        print(f"FAIL: sendPhoto 실패 (exit {result.returncode}): {result.stderr[:200]}")
        update_pending_status("failed", FAIL_CODES["sendphoto_failed"])
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["snapshot", "check-and-send", "send-rollout"])
    parser.add_argument("--after-epoch-ms", type=int, default=None)
    args = parser.parse_args()

    if args.action == "snapshot":
        cmd_snapshot()
    elif args.action == "check-and-send":
        cmd_check_and_send()
    elif args.action == "send-rollout":
        cmd_send_rollout(args.after_epoch_ms)
