#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime
from pathlib import Path

from project_paths import ROOT
STATE_PATH = ROOT / "session" / "setting_mode_autopush.json"
IGNORED_AUTOPUSH_PATHS = {
    "state/automation_health.json",
    "state/automation_supervisor_state.json",
    "state/automation_worker_state.json",
    "state/runtime/automation_worker.lock",
}


def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "schema_version": 1,
            "enabled": True,
            "last_run_at": None,
            "last_commit": None,
            "last_push": None,
            "last_result": None,
            "last_changed_files": [],
        }
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    state = load_state()
    state["last_run_at"] = now_iso()
    if state.get("enabled") is False:
        state["last_result"] = "disabled"
        save_state(state)
        print(json.dumps({"ok": True, "result": "disabled"}, ensure_ascii=False))
        return 0

    status = run_git("status", "--porcelain")
    if status.returncode != 0:
        state["last_result"] = "git_status_failed"
        save_state(state)
        print(json.dumps({"ok": False, "step": "status", "stderr": status.stderr.strip()}, ensure_ascii=False))
        return 1

    lines = [line for line in status.stdout.splitlines() if line.strip()]
    if not lines:
        state["last_result"] = "clean"
        state["last_changed_files"] = []
        save_state(state)
        print(json.dumps({"ok": True, "result": "clean"}, ensure_ascii=False))
        return 0

    changed_files = [line[3:] for line in lines if len(line) > 3]
    changed_files = [path for path in changed_files if path not in IGNORED_AUTOPUSH_PATHS]
    if not changed_files:
        state["last_result"] = "ignored_runtime_changes_only"
        state["last_changed_files"] = []
        save_state(state)
        print(json.dumps({"ok": True, "result": "ignored_runtime_changes_only"}, ensure_ascii=False))
        return 0
    state["last_changed_files"] = changed_files

    add = run_git("add", "-A", "--", *changed_files)
    if add.returncode != 0:
        state["last_result"] = "git_add_failed"
        save_state(state)
        print(json.dumps({"ok": False, "step": "add", "stderr": add.stderr.strip()}, ensure_ascii=False))
        return 1

    commit_message = f"Auto-push setting mode changes at {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}"
    commit = run_git("commit", "-m", commit_message)
    if commit.returncode != 0:
        combined = f"{commit.stdout}\n{commit.stderr}"
        if "nothing to commit" in combined:
            state["last_result"] = "nothing_to_commit"
            save_state(state)
            print(json.dumps({"ok": True, "result": "nothing_to_commit"}, ensure_ascii=False))
            return 0
        state["last_result"] = "git_commit_failed"
        save_state(state)
        print(json.dumps({"ok": False, "step": "commit", "stderr": commit.stderr.strip()}, ensure_ascii=False))
        return 1

    head = run_git("rev-parse", "HEAD")
    commit_sha = head.stdout.strip() if head.returncode == 0 else None
    state["last_commit"] = {"sha": commit_sha, "message": commit_message, "at": now_iso()}

    push = run_git("push", "origin", "main")
    if push.returncode != 0:
        state["last_result"] = "git_push_failed"
        save_state(state)
        print(json.dumps({"ok": False, "step": "push", "stderr": push.stderr.strip()}, ensure_ascii=False))
        return 1

    state["last_push"] = {"branch": "main", "at": now_iso(), "commit": commit_sha}
    state["last_result"] = "pushed"
    save_state(state)
    print(
        json.dumps(
            {
                "ok": True,
                "result": "pushed",
                "commit": commit_sha,
                "changed_files": changed_files,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
