"""Persistent in-process terminal session state."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class TerminalSessionState:
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    previous_cwd: str | None = None
    last_command: str = ""
    last_exit_code: int | None = None
    updated_at: float = field(default_factory=time.time)


_LOCK = threading.RLock()
_SESSIONS: dict[tuple[int, str], TerminalSessionState] = {}


def _default_cwd() -> str:
    home = (os.getenv("HOME") or "").strip()
    if home:
        return str(Path(home).resolve())
    return str(REPO_ROOT)


def get_terminal_session(user_id: int, session_name: str = "default") -> TerminalSessionState:
    key = (int(user_id), (session_name or "default").strip() or "default")
    with _LOCK:
        session = _SESSIONS.get(key)
        if session is None:
            session = TerminalSessionState(cwd=_default_cwd())
            _SESSIONS[key] = session
        return TerminalSessionState(
            cwd=session.cwd,
            env=dict(session.env),
            previous_cwd=session.previous_cwd,
            last_command=session.last_command,
            last_exit_code=session.last_exit_code,
            updated_at=session.updated_at,
        )


def save_terminal_session(user_id: int, session: TerminalSessionState, session_name: str = "default") -> None:
    key = (int(user_id), (session_name or "default").strip() or "default")
    with _LOCK:
        session.updated_at = time.time()
        _SESSIONS[key] = TerminalSessionState(
            cwd=session.cwd,
            env=dict(session.env),
            previous_cwd=session.previous_cwd,
            last_command=session.last_command,
            last_exit_code=session.last_exit_code,
            updated_at=session.updated_at,
        )


def reset_terminal_session(user_id: int, session_name: str = "default") -> TerminalSessionState:
    session = TerminalSessionState(cwd=_default_cwd())
    save_terminal_session(user_id, session, session_name=session_name)
    return get_terminal_session(user_id, session_name=session_name)
