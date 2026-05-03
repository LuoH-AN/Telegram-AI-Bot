"""Lifecycle and status management for SoSearch server."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import requests

from .constants import LOG_DIR, REPO_DIR, STATE_LOCK
from .install import find_binary_candidates
from .state import load_state, save_state


def pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop_server() -> dict:
    with STATE_LOCK:
        state = load_state()
        pid = int(state.get("pid") or 0)
        if pid <= 1 or not pid_alive(pid):
            save_state({})
            return {"ok": True, "message": "SoSearch is not running."}
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as exc:
            return {"ok": False, "message": f"Failed to stop SoSearch pid={pid}: {exc}"}

        for _ in range(20):
            if not pid_alive(pid):
                save_state({})
                return {"ok": True, "message": f"Stopped SoSearch pid={pid}."}
            time.sleep(0.2)

        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        save_state({})
        return {"ok": True, "message": f"Force-stopped SoSearch pid={pid}."}


def ensure_started(*, port: int, binary_path: Path, timeout_seconds: int, cwd_path: Path) -> dict:
    with STATE_LOCK:
        state = load_state()
        pid = int(state.get("pid") or 0)
        if pid > 1 and pid_alive(pid) and int(state.get("port") or 0) == port:
            return {"ok": True, "message": f"SoSearch already running (pid={pid}, port={port}).", "pid": pid}

    stop_server()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"sosearch_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_file, "ab") as handle:
        proc = subprocess.Popen(
            [str(binary_path)],
            cwd=str(cwd_path),
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "PORT": str(port)},
        )
    payload = {
        "pid": proc.pid,
        "port": port,
        "binary": str(binary_path),
        "repo_dir": str(REPO_DIR),
        "log_file": str(log_file),
        "started_at": int(time.time()),
    }
    with STATE_LOCK:
        save_state(payload)
    ready = wait_ready(port=port, timeout_seconds=timeout_seconds)
    if not ready:
        stop_server()
        return {"ok": False, "message": f"SoSearch failed to start on port {port}. Check log: {log_file}"}
    return {"ok": True, "message": f"SoSearch started on port {port} (pid={proc.pid}).", "pid": proc.pid, "log_file": str(log_file)}


def wait_ready(*, port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + max(3, min(120, timeout_seconds))
    url = f"http://127.0.0.1:{port}/search"
    while time.time() < deadline:
        try:
            resp = requests.get(url, params={"q": "ping"}, timeout=3)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def status_payload(*, port: int) -> dict:
    with STATE_LOCK:
        state = load_state()
    pid = int(state.get("pid") or 0)
    running = pid_alive(pid)
    if not running:
        pid = 0
    binary = ""
    for candidate in find_binary_candidates():
        if candidate.exists():
            binary = str(candidate)
            break
    return {
        "ok": True,
        "installed_repo": (REPO_DIR / ".git").exists(),
        "binary_available": bool(binary),
        "binary": binary or None,
        "running": running,
        "pid": pid if running else None,
        "port": int(state.get("port") or port),
        "repo_dir": str(REPO_DIR),
        "log_file": state.get("log_file"),
    }

