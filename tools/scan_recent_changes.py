"""
scan_recent_changes.py — 오빠 PC 최근 변경 사항 스캔 (v2 dev review용)

타이머로 주기적 실행. 결과를 state/dev_review_state.json에 저장.
automation_worker.py의 dev_review_check 트리거가 이 결과를 읽어 선톡 생성.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(os.environ.get("WOONG_BB_ROOT", Path(__file__).resolve().parents[1])).resolve()
STATE = ROOT / "state"
DEV_REVIEW_PATH = STATE / "dev_review_state.json"

KST = timezone(timedelta(hours=9))

PROJECT_ROOTS = [
    # 오빠 앱/게임 프로젝트만 — 웅삐 자신 코드나 인프라는 제외
    Path.home() / "Projects" / "steam-game-project" / "whale-survivors",
    Path.home() / "Desktop" / "app-projects",
    Path.home() / "Desktop" / "product-api",
    Path.home() / "Desktop" / "web-project",
    Path.home() / "Desktop" / "unityproject",
    # 제외: woong-bb/ (웅삐 자신 프로젝트), bots/ (인프라) — 세션 오염 방지
]

HOURS_LOOKBACK = 2


def now_kst() -> datetime:
    return datetime.now(KST)


def run(cmd: list[str], cwd: Optional[Path] = None) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def get_recent_commits(project_path: Path, hours: int = HOURS_LOOKBACK) -> list[dict]:
    """git log --since X hours ago"""
    if not (project_path / ".git").exists():
        # 하위에서 git 찾기
        for sub in project_path.glob("*"):
            if sub.is_dir() and (sub / ".git").exists():
                return _git_log(sub, hours)
        return []
    return _git_log(project_path, hours)


def _git_log(path: Path, hours: int) -> list[dict]:
    since = f"{hours} hours ago"
    out = run(["git", "log", f"--since={since}", "--oneline", "--no-walk", "--all"], cwd=path)
    if not out:
        return []
    commits = []
    for line in out.splitlines()[:5]:
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append({"hash": parts[0], "message": parts[1]})
    return commits


def get_unpushed_commits(project_path: Path) -> int:
    """미push 커밋 수"""
    if not (project_path / ".git").exists():
        return 0
    out = run(["git", "rev-list", "--count", "@{u}..", "HEAD"], cwd=project_path)
    try:
        return int(out)
    except (ValueError, TypeError):
        return 0


def get_recent_modified_files(project_path: Path, hours: int = HOURS_LOOKBACK) -> list[str]:
    """최근 수정 파일 목록"""
    cutoff = now_kst() - timedelta(hours=hours)
    result = []
    exts = {".py", ".ts", ".tsx", ".js", ".dart", ".swift", ".kt", ".cs", ".json", ".md"}
    try:
        for f in project_path.rglob("*"):
            if f.is_file() and f.suffix in exts:
                if any(skip in str(f) for skip in ["node_modules", ".git", "__pycache__", ".dart_tool"]):
                    continue
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=KST)
                if mtime > cutoff:
                    result.append(str(f.relative_to(project_path)))
    except Exception:
        pass
    return result[:10]


def scan_all() -> dict:
    results = []
    has_changes = False

    for project_path in PROJECT_ROOTS:
        if not project_path.exists():
            continue
        proj_name = project_path.name
        commits = get_recent_commits(project_path)
        modified = get_recent_modified_files(project_path)
        unpushed = get_unpushed_commits(project_path)

        if commits or modified or unpushed:
            has_changes = True
            results.append({
                "project": proj_name,
                "path": str(project_path),
                "recent_commits": commits,
                "modified_files": modified,
                "unpushed_count": unpushed,
            })

    state = {
        "schema_version": 1,
        "scanned_at": now_kst().isoformat(),
        "has_changes": has_changes,
        "projects": results,
        "summary_for_proactive": _build_summary(results) if has_changes else None,
    }
    return state


def _build_summary(projects: list[dict]) -> str:
    """선톡 생성에 쓸 짧은 요약 텍스트"""
    parts = []
    for p in projects:
        name = p["project"]
        commits = p["recent_commits"]
        modified = p["modified_files"]
        unpushed = p["unpushed_count"]
        if commits:
            parts.append(f"{name}: 커밋 {len(commits)}개 ({commits[0]['message'][:30]})")
        elif modified:
            parts.append(f"{name}: 파일 {len(modified)}개 수정됨")
        if unpushed:
            parts.append(f"{name}: 미push {unpushed}개")
    return " / ".join(parts[:3])


def main() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    state = scan_all()
    DEV_REVIEW_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    if state["has_changes"]:
        print(f"[dev_review] 변경 감지: {state['summary_for_proactive']}")
    else:
        print("[dev_review] 변경 없음")


if __name__ == "__main__":
    main()
