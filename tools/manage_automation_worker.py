#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from automation.io import load_json
from automation.runtime_state import CONTROL_PATH, HEALTH_PATH, PID_PATH, SUPERVISOR_STATE_PATH, WORKER_STATE_PATH, pid_alive
from project_paths import ROOT, STATE


LABEL = "com.kein.woongbb.automation-worker"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LABEL}.plist"
STDOUT_PATH = STATE / "automation_worker.launchd.stdout.log"
STDERR_PATH = STATE / "automation_worker.launchd.stderr.log"


def run_launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def launchctl_domain_target() -> str:
    return f"gui/{os.getuid()}"


def launchctl_service_target() -> str:
    return f"{launchctl_domain_target()}/{LABEL}"


def plist_text() -> str:
    python_exec = sys.executable
    worker_script = ROOT / "tools" / "automation_worker.py"
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "https://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python_exec}</string>
    <string>{worker_script}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>WOONG_BB_ROOT</key>
    <string>{root}</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>{root}</string>
  <key>RunAtLoad</key>
  <false/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>15</integer>
  <key>StandardOutPath</key>
  <string>{stdout_path}</string>
  <key>StandardErrorPath</key>
  <string>{stderr_path}</string>
</dict>
</plist>
""".format(
        label=LABEL,
        python_exec=python_exec,
        worker_script=worker_script,
        root=ROOT,
        stdout_path=STDOUT_PATH,
        stderr_path=STDERR_PATH,
    )


def cmd_status(_args: argparse.Namespace) -> int:
    worker_state = load_json(WORKER_STATE_PATH, {})
    supervisor_state = load_json(SUPERVISOR_STATE_PATH, {})
    health_state = load_json(HEALTH_PATH, {})
    control_state = load_json(CONTROL_PATH, {})

    launchctl_loaded = False
    launchctl_proc = run_launchctl("print", launchctl_service_target())
    if launchctl_proc.returncode == 0:
        launchctl_loaded = True
    detached_pid = None
    if PID_PATH.exists():
        try:
            detached_pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            detached_pid = None

    payload = {
        "label": LABEL,
        "plist_path": str(PLIST_PATH),
        "plist_exists": PLIST_PATH.exists(),
        "launchctl_loaded": launchctl_loaded,
        "pid_file_exists": PID_PATH.exists(),
        "detached_pid": detached_pid,
        "detached_pid_alive": pid_alive(detached_pid),
        "worker_state": worker_state,
        "supervisor_state": supervisor_state,
        "health_state": health_state,
        "control_state": control_state,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_print_plist(_args: argparse.Namespace) -> int:
    print(plist_text())
    return 0


def cmd_install_launch_agent(args: argparse.Namespace) -> int:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_text(), encoding="utf-8")
    if args.load:
        run_launchctl("bootout", launchctl_service_target())
        proc = run_launchctl("bootstrap", launchctl_domain_target(), str(PLIST_PATH))
        if proc.returncode != 0:
            raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "launchctl bootstrap failed")
    print(
        json.dumps(
            {
                "ok": True,
                "plist_path": str(PLIST_PATH),
                "loaded": bool(args.load),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_remove_launch_agent(args: argparse.Namespace) -> int:
    if args.unload:
        run_launchctl("bootout", launchctl_service_target())
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print(json.dumps({"ok": True, "plist_path": str(PLIST_PATH), "unloaded": bool(args.unload)}, ensure_ascii=False))
    return 0


def require_installed_plist() -> None:
    if not PLIST_PATH.exists():
        raise SystemExit(f"launch agent plist not found: {PLIST_PATH}")


def detached_worker_env() -> dict:
    env = os.environ.copy()
    env["WOONG_BB_ROOT"] = str(ROOT)
    return env


def worker_script_path() -> str:
    return str(ROOT / "tools" / "automation_worker.py")


def spawn_detached_worker() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    stdout_fp = STDOUT_PATH.open("a", encoding="utf-8")
    stderr_fp = STDERR_PATH.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, worker_script_path()],
        cwd=ROOT,
        stdout=stdout_fp,
        stderr=stderr_fp,
        env=detached_worker_env(),
        start_new_session=True,
        close_fds=True,
    )
    return proc.pid


def unload_launch_agent_if_loaded() -> None:
    run_launchctl("bootout", launchctl_service_target())


def stop_detached_worker() -> bool:
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return False
    if not pid_alive(pid):
        return False
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not pid_alive(pid):
            return True
        time.sleep(0.25)
    os.kill(pid, signal.SIGKILL)
    return True


def maybe_launchd_permission_error() -> bool:
    if not STDERR_PATH.exists():
        return False
    try:
        tail = STDERR_PATH.read_text(encoding="utf-8")[-1000:]
    except Exception:
        return False
    return "Operation not permitted" in tail and (
        "automation_worker.py" in tail or "manage_automation_worker.py" in tail
    )


def cmd_start(_args: argparse.Namespace) -> int:
    if PID_PATH.exists():
        try:
            current_pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            current_pid = None
        if pid_alive(current_pid):
            print(json.dumps({"ok": True, "action": "start", "mode": "detached", "pid": current_pid, "already_running": True}, ensure_ascii=False))
            return 0

    require_installed_plist()
    if not run_launchctl("print", launchctl_service_target()).returncode == 0:
        bootstrap = run_launchctl("bootstrap", launchctl_domain_target(), str(PLIST_PATH))
        if bootstrap.returncode != 0:
            raise SystemExit(bootstrap.stderr.strip() or bootstrap.stdout.strip() or "launchctl bootstrap failed")
    kickstart = run_launchctl("kickstart", "-k", launchctl_service_target())
    if kickstart.returncode == 0:
        time.sleep(1.0)
        if PID_PATH.exists():
            try:
                current_pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            except Exception:
                current_pid = None
            if pid_alive(current_pid):
                print(json.dumps({"ok": True, "action": "start", "mode": "launchd", "service": launchctl_service_target(), "pid": current_pid}, ensure_ascii=False))
                return 0
        if maybe_launchd_permission_error():
            unload_launch_agent_if_loaded()
            pid = spawn_detached_worker()
            print(json.dumps({"ok": True, "action": "start", "mode": "detached_fallback", "pid": pid}, ensure_ascii=False))
            return 0
        raise SystemExit("launchd kickstart returned success but worker did not stay alive")
    if maybe_launchd_permission_error():
        unload_launch_agent_if_loaded()
        pid = spawn_detached_worker()
        print(json.dumps({"ok": True, "action": "start", "mode": "detached_fallback", "pid": pid}, ensure_ascii=False))
        return 0
    raise SystemExit(kickstart.stderr.strip() or kickstart.stdout.strip() or "launchctl kickstart failed")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    detached_stopped = stop_detached_worker()
    proc = run_launchctl("bootout", launchctl_service_target())
    if proc.returncode not in {0, 3, 36, 113}:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "launchctl bootout failed")
    print(json.dumps({"ok": True, "action": "stop", "service": launchctl_service_target(), "detached_stopped": detached_stopped}, ensure_ascii=False))
    return 0


def cmd_restart(_args: argparse.Namespace) -> int:
    try:
        cmd_stop(_args)
    except SystemExit as exc:
        message = str(exc)
        if message and "No such process" not in message:
            raise
    return cmd_start(_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the woong-bb automation worker as a project-owned launchd service.")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    print_plist = sub.add_parser("print-plist")
    print_plist.set_defaults(func=cmd_print_plist)

    install = sub.add_parser("install-launch-agent")
    install.add_argument("--load", action="store_true", help="Also bootstrap the launch agent after writing the plist.")
    install.set_defaults(func=cmd_install_launch_agent)

    remove = sub.add_parser("remove-launch-agent")
    remove.add_argument("--unload", action="store_true", help="Also unload the launch agent before deleting the plist.")
    remove.set_defaults(func=cmd_remove_launch_agent)

    start = sub.add_parser("start")
    start.set_defaults(func=cmd_start)

    stop = sub.add_parser("stop")
    stop.set_defaults(func=cmd_stop)

    restart = sub.add_parser("restart")
    restart.set_defaults(func=cmd_restart)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
