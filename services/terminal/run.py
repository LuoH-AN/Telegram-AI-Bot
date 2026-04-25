"""Core terminal execution workflow."""

from __future__ import annotations

import subprocess

from services.log import record_terminal_command

from .builtins import apply_shell_builtin
from .state import get_terminal_session, reset_terminal_session, save_terminal_session
from .utils import clean_env, resolve_cwd, truncate_output, validate_command


def _session_payload(session) -> dict:
    return {
        "cwd": session.cwd,
        "previous_cwd": session.previous_cwd,
        "last_command": session.last_command,
        "last_exit_code": session.last_exit_code,
    }


def _final_payload(ok: bool, command: str, cwd: str, session_name: str, exit_code: int, stdout: str, stderr: str, session) -> dict:
    return {
        "ok": ok,
        "command": command,
        "cwd": cwd,
        "session_name": session_name,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "env": dict(session.env),
        "session": _session_payload(session),
    }


def execute_terminal_command(user_id: int, command: str, *, cwd: str | None = None, timeout_seconds: int = 900, session_name: str = "default") -> dict:
    session = get_terminal_session(user_id, session_name=session_name)
    builtin = apply_shell_builtin(command, session)
    if builtin is not None:
        if (command or "").strip() in {"reset", "reset-session"}:
            session = reset_terminal_session(user_id, session_name=session_name)
            builtin["stdout"] = session.cwd
        session.last_command, session.last_exit_code = command, builtin["exit_code"]
        save_terminal_session(user_id, session, session_name=session_name)
        stdout, stderr = truncate_output(builtin["stdout"]), truncate_output(builtin["stderr"])
        record_terminal_command(user_id, command=command, exit_code=builtin["exit_code"], cwd=session.cwd, stdout=stdout, stderr=stderr)
        return _final_payload(builtin["ok"], command, session.cwd, session_name, builtin["exit_code"], stdout, stderr, session)

    resolved_cwd = resolve_cwd(cwd, session.cwd)
    error = validate_command(command)
    if error:
        record_terminal_command(user_id, command=command, exit_code=-1, cwd=str(resolved_cwd), stdout="", stderr=error, blocked=True)
        return {"ok": False, "command": command, "cwd": str(resolved_cwd), "session_name": session_name, "exit_code": -1, "stdout": "", "stderr": error}
    if not resolved_cwd.exists() or not resolved_cwd.is_dir():
        stderr = f"Working directory does not exist: {resolved_cwd}"
        record_terminal_command(user_id, command=command, exit_code=-1, cwd=str(resolved_cwd), stdout="", stderr=stderr)
        return {"ok": False, "command": command, "cwd": str(resolved_cwd), "session_name": session_name, "exit_code": -1, "stdout": "", "stderr": stderr}

    try:
        env = clean_env()
        env.update(session.env)
        completed = subprocess.run(["bash", "-lc", command], cwd=str(resolved_cwd), env=env, capture_output=True, text=True, timeout=max(1, int(timeout_seconds)))
        stdout, stderr = truncate_output(completed.stdout), truncate_output(completed.stderr)
        session.previous_cwd, session.cwd = session.cwd, str(resolved_cwd)
        session.last_command, session.last_exit_code = command, completed.returncode
        save_terminal_session(user_id, session, session_name=session_name)
        record_terminal_command(user_id, command=command, exit_code=completed.returncode, cwd=str(resolved_cwd), stdout=stdout, stderr=stderr)
        return _final_payload(completed.returncode == 0, command, str(resolved_cwd), session_name, completed.returncode, stdout, stderr, session)
    except subprocess.TimeoutExpired as exc:
        stdout = truncate_output(exc.stdout)
        stderr = truncate_output(exc.stderr)
        timeout_message = f"Command execution timeout (>{int(timeout_seconds)}s)."
        stderr = f"{stderr}\n{timeout_message}".strip() if stderr else timeout_message
        session.previous_cwd, session.cwd = session.cwd, str(resolved_cwd)
        session.last_command, session.last_exit_code = command, 124
        save_terminal_session(user_id, session, session_name=session_name)
        record_terminal_command(user_id, command=command, exit_code=124, cwd=str(resolved_cwd), stdout=stdout, stderr=stderr)
        return _final_payload(False, command, str(resolved_cwd), session_name, 124, stdout, stderr, session)
