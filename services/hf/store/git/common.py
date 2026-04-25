"""Git backend helpers for HF dataset storage."""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
import tempfile

from ..config import LFS_LOG_TAIL_LINES


def ensure_git_backend(store) -> bool:
    if not store._enabled:
        return False
    if shutil.which("git"):
        return True
    store._logger.warning("HF dataset storage disabled: git is unavailable.")
    store._enabled = False
    return False


def git_repo_url(store) -> str:
    return f"https://huggingface.co/datasets/{store.repo_id}"


def git_local_dir(store) -> str:
    if store._git_repo_dir:
        return store._git_repo_dir
    digest = hashlib.sha256(f"{store.repo_id}:{store.branch}".encode("utf-8")).hexdigest()[:16]
    store._git_repo_dir = os.path.join(tempfile.gettempdir(), "gemen_hf_git", digest)
    return store._git_repo_dir


def git_auth_header(store) -> str:
    username = store.username or "__token__"
    basic = base64.b64encode(f"{username}:{store.token}".encode("utf-8")).decode("ascii")
    return f"AUTHORIZATION: Basic {basic}"


def read_lfs_log_excerpt(repo_dir: str) -> str:
    log_dir = os.path.join(repo_dir, ".git", "lfs", "logs")
    if not os.path.isdir(log_dir):
        return ""
    try:
        entries = [os.path.join(log_dir, name) for name in os.listdir(log_dir) if name.endswith(".log")]
    except OSError:
        return ""
    if not entries:
        return ""
    entries.sort(key=os.path.getmtime, reverse=True)
    try:
        with open(entries[0], "r", encoding="utf-8", errors="ignore") as handle:
            tail = handle.readlines()[-LFS_LOG_TAIL_LINES:]
    except OSError:
        return ""
    filtered = [line.rstrip() for line in tail if line.strip() and "authorization" not in line.lower() and "token" not in line.lower()]
    return "\n".join(filtered[-20:]).strip()


def is_lfs_push_error(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    if "lfs" not in lowered:
        return False
    return "lfs:" in lowered or "git-lfs" in lowered or ("lfs" in lowered and "error" in lowered)


def run_git(store, args: list[str], *, cwd: str | None = None, network: bool = False, check: bool = True):
    cmd = ["git"]
    if network:
        cmd.extend(["-c", f"http.extraHeader={git_auth_header(store)}"])
    cmd.extend(args)
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    if check and result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return result
