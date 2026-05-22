from __future__ import annotations

import json
import os
from typing import Optional

from project_paths import SESSION, STATE, runtime_path

from .io import load_json, now_iso, save_json


WORKER_STATE_PATH = STATE / "automation_worker_state.json"
SUPERVISOR_STATE_PATH = STATE / "automation_supervisor_state.json"
HEALTH_PATH = STATE / "automation_health.json"
CONTROL_PATH = STATE / "automation_control.json"
LOCK_PATH = runtime_path("automation_worker.lock")
PID_PATH = SESSION / "automation-worker.pid"


def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, PermissionError, ValueError):
        return False
    return True


def release_lock() -> None:
    if LOCK_PATH.exists():
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass
    if PID_PATH.exists():
        try:
            PID_PATH.unlink()
        except OSError:
            pass


def acquire_lock() -> int:
    generation = 1
    if LOCK_PATH.exists():
        current = load_json(LOCK_PATH, {})
        current_pid = current.get("pid")
        current_gen = int(current.get("generation") or 0)
        generation = current_gen + 1
        if pid_alive(current_pid):
            raise RuntimeError("active worker lock exists")
    lock_data = {
        "pid": os.getpid(),
        "generation": generation,
        "started_at": now_iso(),
        "last_heartbeat_at": now_iso(),
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock_data, ensure_ascii=False, indent=2) + "\n")
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()) + "\n")
    return generation


def update_control_ready() -> None:
    control = load_json(CONTROL_PATH, {})
    control["launch_ready"] = True
    if control.get("requested_action") == "start":
        control["requested_action"] = None
        control["requested_at"] = None
        control["requested_by"] = None
        control["request_note"] = None
    save_json(CONTROL_PATH, control)


def update_runtime_state(
    *,
    enabled: bool,
    health: str,
    generation: int,
    phase: str,
    last_result: Optional[str] = None,
    last_error: Optional[str] = None,
    last_success: Optional[str] = None,
    action_result: Optional[str] = None,
    applied_action: Optional[str] = None,
) -> None:
    ts = now_iso()
    worker_state = load_json(WORKER_STATE_PATH, {})
    worker_state["enabled"] = enabled
    worker_state["last_run_at"] = ts
    if last_result is not None:
        worker_state["last_result"] = last_result
    save_json(WORKER_STATE_PATH, worker_state)

    supervisor = load_json(SUPERVISOR_STATE_PATH, {})
    supervisor["enabled"] = enabled
    supervisor["health"] = health
    supervisor["active_pid"] = os.getpid() if enabled else None
    supervisor["last_heartbeat_at"] = ts if enabled else supervisor.get("last_heartbeat_at")
    supervisor["last_success_at"] = last_success if last_success else supervisor.get("last_success_at")
    supervisor["last_error_at"] = ts if last_error else supervisor.get("last_error_at")
    supervisor["last_error_summary"] = last_error
    supervisor["duplicate_suspected"] = False
    supervisor["singleton_lock"] = {
        "path": str(LOCK_PATH),
        "active": enabled,
        "generation": generation if enabled else supervisor.get("singleton_lock", {}).get("generation", generation),
    }
    supervisor["pending_control_action"] = None
    if applied_action:
        supervisor["last_applied_action"] = applied_action
        supervisor["last_applied_at"] = ts
    if action_result:
        supervisor["last_action_result"] = action_result
    save_json(SUPERVISOR_STATE_PATH, supervisor)

    health_state = load_json(HEALTH_PATH, {})
    health_state["status"] = health
    health_state["pid"] = os.getpid() if enabled else None
    health_state["generation"] = generation
    health_state["started_at"] = health_state.get("started_at") or ts
    health_state["last_heartbeat_at"] = ts if enabled else health_state.get("last_heartbeat_at")
    health_state["current_phase"] = phase
    health_state["last_success_at"] = last_success if last_success else health_state.get("last_success_at")
    health_state["last_error_at"] = ts if last_error else health_state.get("last_error_at")
    health_state["last_error_summary"] = last_error
    save_json(HEALTH_PATH, health_state)

    if enabled and LOCK_PATH.exists():
        lock_data = load_json(LOCK_PATH, {})
        lock_data["last_heartbeat_at"] = ts
        lock_data["generation"] = generation
        LOCK_PATH.write_text(json.dumps(lock_data, ensure_ascii=False, indent=2) + "\n")


def stop_state(generation: int, result: str, applied_action: Optional[str] = None) -> None:
    ts = now_iso()
    worker_state = load_json(WORKER_STATE_PATH, {})
    worker_state["enabled"] = False
    worker_state["last_run_at"] = ts
    worker_state["last_result"] = result
    save_json(WORKER_STATE_PATH, worker_state)

    supervisor = load_json(SUPERVISOR_STATE_PATH, {})
    supervisor["enabled"] = False
    supervisor["health"] = "stopped"
    supervisor["active_pid"] = None
    supervisor["singleton_lock"] = {
        "path": str(LOCK_PATH),
        "active": False,
        "generation": generation,
    }
    supervisor["pending_control_action"] = None
    if applied_action:
        supervisor["last_applied_action"] = applied_action
        supervisor["last_applied_at"] = ts
        supervisor["last_action_result"] = result
    save_json(SUPERVISOR_STATE_PATH, supervisor)

    health_state = load_json(HEALTH_PATH, {})
    health_state["status"] = "stopped"
    health_state["pid"] = None
    health_state["generation"] = generation
    health_state["current_phase"] = "stopped"
    save_json(HEALTH_PATH, health_state)
