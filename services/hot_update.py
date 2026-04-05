"""Git pull + in-process restart helpers for /update command."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from launcher import UPDATE_RESTART_EXIT_CODE

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(command: list[str], *, timeout: int = 1200) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=timeout)


def run_hot_update() -> dict:
    branch_proc = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_proc.returncode != 0:
        return {"ok": False, "message": (branch_proc.stderr or branch_proc.stdout or "failed to detect branch").strip()}
    branch = (branch_proc.stdout or "").strip() or "main"
    head_before = (_run(["git", "rev-parse", "HEAD"]).stdout or "").strip()

    fetch_proc = _run(["git", "fetch", "origin", branch])
    if fetch_proc.returncode != 0:
        return {"ok": False, "message": (fetch_proc.stderr or fetch_proc.stdout or "git fetch failed").strip()}

    pull_proc = _run(["git", "pull", "--ff-only", "origin", branch])
    if pull_proc.returncode != 0:
        return {"ok": False, "message": (pull_proc.stderr or pull_proc.stdout or "git pull failed").strip()}

    head_after = (_run(["git", "rev-parse", "HEAD"]).stdout or "").strip()
    changed = bool(head_before and head_after and head_before != head_after)
    output = (pull_proc.stdout or pull_proc.stderr or "").strip()
    requirements_changed = False
    if changed:
        diff_proc = _run(["git", "diff", "--name-only", head_before, head_after])
        if diff_proc.returncode == 0:
            files = [line.strip() for line in (diff_proc.stdout or "").splitlines() if line.strip()]
            requirements_changed = "requirements.txt" in files
    if changed and requirements_changed:
        pip_proc = _run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], timeout=3600)
        if pip_proc.returncode != 0:
            return {"ok": False, "message": (pip_proc.stderr or pip_proc.stdout or "pip install failed").strip()}
    if not changed:
        return {"ok": True, "changed": False, "branch": branch, "message": output or "Already up to date."}
    return {"ok": True, "changed": True, "branch": branch, "old": head_before, "new": head_after, "message": output or "Updated."}


def schedule_process_restart(*, delay_seconds: float = 1.2) -> None:
    def _worker() -> None:
        time.sleep(max(0.1, float(delay_seconds)))
        os._exit(UPDATE_RESTART_EXIT_CODE)

    threading.Thread(target=_worker, daemon=True).start()

