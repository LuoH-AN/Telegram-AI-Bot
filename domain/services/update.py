"""Git pull + in-process restart helpers for /update command."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from infrastructure.cache import sync_to_database
from entrypoints.launcher import UPDATE_RESTART_EXIT_CODE


def _find_repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "main.py").is_file() and (parent / "domain").is_dir():
            return parent
    return path.parents[2]


REPO_ROOT = _find_repo_root()


def _run(command: list[str], *, timeout: int = 1200) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=timeout)


def _bootstrap_git_repo(branch: str) -> tuple[bool, str]:
    repo_url = (os.getenv("HOT_UPDATE_REPO_URL", "") or "").strip()
    if not repo_url:
        return False, f"HOT_UPDATE_REPO_URL is required when {REPO_ROOT} has no .git metadata."
    for command in (
        ["git", "init"],
        ["git", "config", "--global", "--add", "safe.directory", str(REPO_ROOT)],
        ["git", "remote", "remove", "origin"],
    ):
        _run(command, timeout=60)
    add_remote = _run(["git", "remote", "add", "origin", repo_url], timeout=120)
    if add_remote.returncode != 0:
        return False, (add_remote.stderr or add_remote.stdout or "git remote add failed").strip()
    fetch = _run(["git", "fetch", "--depth=1", "origin", branch], timeout=1200)
    if fetch.returncode != 0:
        return False, (fetch.stderr or fetch.stdout or "git fetch failed").strip()
    reset = _run(["git", "reset", "--hard", "FETCH_HEAD"], timeout=300)
    if reset.returncode != 0:
        return False, (reset.stderr or reset.stdout or "git reset failed").strip()
    checkout = _run(["git", "checkout", "-B", branch], timeout=60)
    if checkout.returncode != 0:
        return False, (checkout.stderr or checkout.stdout or "git checkout failed").strip()
    return True, "git metadata initialized"


def run_hot_update() -> dict:
    branch = (os.getenv("HOT_UPDATE_BRANCH", "") or "").strip() or "main"
    bootstrapped = False
    bootstrap_message = ""
    if not (REPO_ROOT / ".git").exists():
        ok, bootstrap_message = _bootstrap_git_repo(branch)
        if not ok:
            return {"ok": False, "message": bootstrap_message}
        bootstrapped = True
        head_before = ""
        output = bootstrap_message
    else:
        head_before = (_run(["git", "rev-parse", "HEAD"]).stdout or "").strip()

        fetch_proc = _run(["git", "fetch", "origin", branch])
        if fetch_proc.returncode != 0:
            return {"ok": False, "message": (fetch_proc.stderr or fetch_proc.stdout or "git fetch failed").strip()}

        pull_proc = _run(["git", "pull", "--ff-only", "origin", branch])
        if pull_proc.returncode != 0:
            return {"ok": False, "message": (pull_proc.stderr or pull_proc.stdout or "git pull failed").strip()}
        output = (pull_proc.stdout or pull_proc.stderr or "").strip()

    head_after = (_run(["git", "rev-parse", "HEAD"]).stdout or "").strip()
    changed = bootstrapped or bool(head_before and head_after and head_before != head_after)
    requirements_changed = bootstrapped
    if changed and head_before:
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
    return {
        "ok": True,
        "changed": True,
        "branch": branch,
        "old": "no-git" if bootstrapped else head_before,
        "new": head_after,
        "message": output or "Updated.",
    }


def schedule_process_restart(*, delay_seconds: float = 1.2) -> None:
    def _worker() -> None:
        time.sleep(max(0.1, float(delay_seconds)))
        if os.getenv("BOT_LAUNCHER_MANAGED") == "1":
            os._exit(UPDATE_RESTART_EXIT_CODE)
        try:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        except Exception:
            os._exit(UPDATE_RESTART_EXIT_CODE)

    threading.Thread(target=_worker, daemon=True).start()


def run_safe_restart() -> dict:
    try:
        sync_to_database()
    except Exception as exc:
        return {"ok": False, "message": f"Failed to sync data before restart: {exc}"}
    return {"ok": True, "message": "State synced successfully."}
