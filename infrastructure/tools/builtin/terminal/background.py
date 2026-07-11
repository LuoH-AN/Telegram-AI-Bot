"""Reconnectable background terminal session operations."""

from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

from shared.terminal_environment import build_persistent_terminal_env

from .state import REPO_ROOT, ensure_control_dir, ensure_log_dir
from .rootfs import ensure_rootfs
from .store import (
    acknowledge_completion_event,
    arm_completion_event,
    create_session,
    get_session,
    list_sessions,
    mark_stale_sessions,
    update_session,
)

logger = logging.getLogger(__name__)


def _base_env() -> dict[str, str]:
    return build_persistent_terminal_env(os.environ)


def _session_id() -> str:
    return secrets.token_hex(5)


def _read_log(path: str | Path, *, limit: int = 12000) -> str:
    try:
        output = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(output) <= limit:
        return output
    head = max(0, limit - 4000)
    return output[:head] + f"\n\n...(truncated, {len(output)} chars total)...\n" + output[-4000:]


def _format_job(job: dict, *, include_output: bool = True) -> str:
    elapsed_end = job.get("ended_at") or time.time()
    elapsed = max(0, int(elapsed_end - job["started_at"]))
    lines = [
        f"Session: {job['session_id']}",
        f"PID: {job.get('pid') or 'starting'}",
        f"Status: {job['status']}",
        f"Exit code: {job.get('exit_code')}" if job.get("exit_code") is not None else "",
        f"Elapsed: {elapsed}s",
        f"CWD: {job['cwd']}",
        f"Command: {job['command']}",
    ]
    if include_output:
        output = _read_log(job["log_file"])
        if output:
            lines.append(f"\nOutput:\n{output}")
    return "\n".join(line for line in lines if line)


def _scoped_job(
    identifier: str | int,
    *,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> dict | None:
    job = get_session(identifier)
    if not job:
        return None
    if user_id is not None and int(job["user_id"]) != int(user_id):
        return None
    if conversation_id is not None and job.get("conversation_id") != int(conversation_id):
        return None
    return job


def run_background(
    command: str,
    cwd_path: Path,
    *,
    user_id: int = 0,
    chat_id: int | None = None,
    conversation_id: int | None = None,
    pty: bool = False,
    notify_on_exit: bool = False,
) -> str:
    ensure_rootfs()
    session_id = _session_id()
    log_file = ensure_log_dir() / f"{session_id}.log"
    socket_path = ensure_control_dir() / f"{session_id}.sock"
    started_at = time.time()
    create_session({
        "session_id": session_id,
        "user_id": int(user_id),
        "chat_id": chat_id,
        "conversation_id": conversation_id,
        "command": command,
        "cwd": str(cwd_path),
        "worker_pid": None,
        "pid": None,
        "status": "starting",
        "exit_code": None,
        "started_at": started_at,
        "ended_at": None,
        "last_output_at": started_at,
        "log_file": str(log_file),
        "socket_path": str(socket_path),
        "pty": 1 if pty else 0,
        "notify_on_exit": 1 if notify_on_exit else 0,
        "delivery_status": "pending",
        "delivery_attempts": 0,
        "delivery_error": None,
        "claimed_at": None,
        "delivered_at": None,
        "completion_response": None,
    })
    try:
        subprocess.Popen(
            [sys.executable, "-m", "infrastructure.tools.builtin.terminal.worker", session_id],
            cwd=str(REPO_ROOT),
            env=_base_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        deadline = time.monotonic() + 2
        job = get_session(session_id)
        while job and job["status"] == "starting" and time.monotonic() < deadline:
            time.sleep(0.02)
            job = get_session(session_id)
        logger.info("terminal session started: session=%s command=%s", session_id, command[:80])
        job = job or get_session(session_id)
        return _format_job(job, include_output=True) if job else f"Terminal session created: {session_id}"
    except Exception as exc:
        update_session(session_id, status="failed", ended_at=time.time())
        logger.exception("terminal session start failed")
        return f"Error starting terminal session {session_id}: {exc}"


def check_background_job(
    identifier: str | int,
    *,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> str:
    mark_stale_sessions()
    job = _scoped_job(identifier, user_id=user_id, conversation_id=conversation_id)
    if not job:
        return f"Terminal session not found: {identifier}."
    return _format_job(job)


def wait_background_job(
    identifier: str | int,
    timeout: float = 30,
    *,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> str:
    deadline = time.monotonic() + max(0, min(60, float(timeout)))
    while True:
        mark_stale_sessions()
        job = _scoped_job(identifier, user_id=user_id, conversation_id=conversation_id)
        if not job:
            return f"Terminal session not found: {identifier}."
        if job["status"] not in {"starting", "running"} or time.monotonic() >= deadline:
            return _format_job(job)
        time.sleep(0.2)


def list_background_jobs(*, user_id: int | None = None, conversation_id: int | None = None) -> str:
    mark_stale_sessions()
    jobs = list_sessions(user_id=user_id, conversation_id=conversation_id)
    if not jobs:
        return "No terminal sessions."
    now = time.time()
    lines = ["Terminal sessions:"]
    for job in jobs:
        ended = job.get("ended_at") or now
        elapsed = max(0, int(ended - job["started_at"]))
        lines.append(
            f"  {job['session_id']} [{job['status']}] {elapsed}s pid={job.get('pid') or '-'} "
            f"- {job['command'][:100]}"
        )
    return "\n".join(lines)


def _control(
    identifier: str | int,
    payload: dict,
    *,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> str:
    job = _scoped_job(identifier, user_id=user_id, conversation_id=conversation_id)
    if not job:
        return f"Terminal session not found: {identifier}."
    if job["status"] not in {"starting", "running"}:
        return f"Session {job['session_id']} is {job['status']}; it is no longer controllable."
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(job["socket_path"])
            client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            response = b""
            while b"\n" not in response:
                part = client.recv(65536)
                if not part:
                    break
                response += part
        result = json.loads(response.decode("utf-8").splitlines()[0])
        if result.get("ok"):
            return f"Session {job['session_id']}: {payload['action']} accepted."
        return f"Session {job['session_id']}: {result.get('error') or 'control failed'}."
    except Exception as exc:
        return f"Session {job['session_id']} control failed: {exc}"


def write_background_job(
    identifier: str | int,
    data: str,
    *,
    submit: bool = False,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> str:
    return _control(
        identifier,
        {"action": "write", "data": str(data) + ("\n" if submit else "")},
        user_id=user_id,
        conversation_id=conversation_id,
    )


def kill_background_job(
    identifier: str | int,
    *,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> str:
    return _control(
        identifier,
        {"action": "kill"},
        user_id=user_id,
        conversation_id=conversation_id,
    )


def active_session_prompt(*, user_id: int, conversation_id: int | None) -> str:
    mark_stale_sessions()
    running = [
        row for row in list_sessions(user_id=user_id, conversation_id=conversation_id, limit=12)
        if row["status"] in {"starting", "running"}
    ]
    if not running:
        return ""
    lines = ["Active terminal sessions for this conversation:"]
    for row in running:
        lines.append(
            f"- session_id={row['session_id']} status={row['status']} pid={row.get('pid') or '-'} "
            f"cwd={row['cwd']} command={row['command'][:160]}"
        )
    lines.append(
        "Use terminal_process to poll, wait, write input, or kill these sessions; "
        "do not forget ongoing work."
    )
    return "\n".join(lines)


def arm_background_completion(identifier: str | int) -> None:
    job = get_session(identifier)
    if job:
        arm_completion_event(job["session_id"])


def acknowledge_background_completion(identifier: str | int) -> None:
    job = get_session(identifier)
    if job:
        acknowledge_completion_event(job["session_id"])
