#!/usr/bin/env python3
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"TELEGRAM_BOT_TOKEN\s*=\s*\d+:[A-Za-z0-9_-]{20,}"),
    re.compile(r"ELEVENLABS_API_KEY\s*=\s*\S{20,}"),
    re.compile(r"AZURE_SPEECH_KEY\s*=\s*\S{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_.-]{30,}"),
]
SKIP_DIRS = {".git", ".tmp", ".playwright-mcp", "session", "__pycache__"}


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def tracked_and_untracked_files() -> list[Path]:
    proc = run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git ls-files failed")
    return [ROOT / item for item in proc.stdout.split("\0") if item]


def project_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return files


def check_python() -> list[str]:
    errors = []
    for path in sorted(project_files()):
        if path.suffix != ".py":
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc.msg}")
    return errors


def check_node() -> list[str]:
    errors = []
    for path in sorted(project_files()):
        if path.suffix != ".mjs":
            continue
        proc = run(["node", "--check", str(path.relative_to(ROOT))])
        if proc.returncode != 0:
            errors.append(f"{path.relative_to(ROOT)}: {proc.stderr.strip()}")
    return errors


def check_imports() -> list[str]:
    errors = []
    for module in ["automation_worker"]:
        proc = run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, 'tools'); import %s" % module,
            ]
        )
        if proc.returncode != 0:
            errors.append(f"{module}: {(proc.stderr or proc.stdout).strip()}")
    return errors


def check_json() -> list[str]:
    errors = []
    for path in sorted(project_files()):
        if path.suffix != ".json":
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return errors


def check_jsonl() -> list[str]:
    errors = []
    for path in sorted(project_files()):
        if path.suffix != ".jsonl":
            continue
        with path.open(encoding="utf-8") as fp:
            for line_no, line in enumerate(fp, start=1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except Exception as exc:
                    errors.append(f"{path.relative_to(ROOT)}:{line_no}: {exc}")
    return errors


def check_secrets() -> list[str]:
    findings = []
    for path in sorted(tracked_and_untracked_files()):
        if not path.exists() or path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(str(rel))
                break
    return findings


def main() -> int:
    checks = {
        "python": check_python(),
        "node": check_node(),
        "imports": check_imports(),
        "json": check_json(),
        "jsonl": check_jsonl(),
        "secrets": check_secrets(),
    }
    ok = all(not errors for errors in checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
