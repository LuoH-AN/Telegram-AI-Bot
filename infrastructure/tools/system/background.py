"""Background terminal job operations."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from .state import BG_JOBS, BG_LOCK, ensure_log_dir

logger = logging.getLogger(__name__)


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PIP_BREAK_SYSTEM_PACKAGES", "1")
    env.setdefault("PIP_ROOT_USER_ACTION", "ignore")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    return env


def run_background(command: str, cwd_path: Path) -> str:
    log_file = ensure_log_dir() / f"bg_{time.strftime('%Y%m%d_%H%M%S')}.log"
    try:
        with open(log_file, "w") as log_handle:
            proc = subprocess.Popen(["bash", "-lc", command], cwd=str(cwd_path), env=_base_env(), stdout=log_handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        pid = proc.pid
        with BG_LOCK:
            BG_JOBS[pid] = {"command": command, "cwd": str(cwd_path), "started_at": time.time(), "log_file": log_file, "done": False, "exit_code": None}

        def _wait() -> None:
            proc.wait()
            with BG_LOCK:
                if pid in BG_JOBS:
                    BG_JOBS[pid]["done"] = True
                    BG_JOBS[pid]["exit_code"] = proc.returncode

        threading.Thread(target=_wait, daemon=True).start()
        logger.info("bg_job: pid=%d, cmd=%s, log=%s", pid, command[:80], log_file)
        return f"Background job started.\nPID: {pid}\nLog: {log_file}\nCommand: {command}\nUse terminal_bg_check with pid={pid} to check status."
    except Exception as exc:
        logger.exception("bg_job start failed")
        return f"Error starting background job: {exc}"


def _read_log(log_file: Path) -> str:
    try:
        output = log_file.read_text(encoding="utf-8", errors="replace")
        if len(output) > 4000:
            output = output[:3000] + f"\n\n...(truncated, {len(output)} chars total)...\n" + output[-1000:]
        return output
    except Exception:
        return "(unable to read log)"


def check_background_job(pid: int) -> str:
    with BG_LOCK:
        job = BG_JOBS.get(pid)
    if not job:
        return f"Background job not found: PID {pid}."
    output = _read_log(job["log_file"]) if job["log_file"].exists() else ""
    elapsed = int(time.time() - job["started_at"])
    lines = [f"PID: {pid}", f"Status: {'done' if job['done'] else 'running'}", f"Exit code: {job['exit_code']}" if job["done"] else "", f"Elapsed: {elapsed}s", f"Command: {job['command']}"]
    if output:
        lines.append(f"\nOutput:\n{output}")
    return "\n".join(line for line in lines if line)


def list_background_jobs() -> str:
    with BG_LOCK:
        if not BG_JOBS:
            return "No background jobs."
        jobs = list(BG_JOBS.items())
    now = time.time()
    lines = ["Background jobs:"]
    for pid, job in jobs:
        status = "done" if job["done"] else "running"
        elapsed = int(now - job["started_at"])
        exit_info = f", exit={job['exit_code']}" if job["done"] else ""
        lines.append(f"  PID {pid}: [{status}] {elapsed}s{exit_info} - {job['command'][:60]}")
    return "\n".join(lines)
