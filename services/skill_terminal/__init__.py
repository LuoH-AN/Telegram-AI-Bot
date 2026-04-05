"""Terminal workflow for direct shell usage and AI-guided task execution."""

from __future__ import annotations

import json

from .agent import run_agent_terminal
from .direct import TERMINAL_HELP_TEXT, looks_like_direct_command, run_direct_terminal
from services.terminal_session import get_terminal_session, reset_terminal_session
from services.user import get_user_settings


def _session_snapshot(user_id: int) -> dict:
    session = get_terminal_session(user_id, session_name="default")
    return {
        "cwd": session.cwd,
        "previous_cwd": session.previous_cwd,
        "env": session.env,
        "last_command": session.last_command,
        "last_exit_code": session.last_exit_code,
    }


def run_skill_terminal(user_id: int, goal: str) -> dict:
    settings = get_user_settings(user_id)
    stripped_goal = (goal or "").strip()
    lower_goal = stripped_goal.lower()
    if lower_goal in {"help", "?", ""}:
        return {"ok": True, "message": TERMINAL_HELP_TEXT, "steps": []}
    if lower_goal in {"session", "session info", "terminal session"}:
        return {"ok": True, "message": json.dumps(_session_snapshot(user_id), ensure_ascii=False, indent=2), "steps": []}
    if lower_goal in {"reset terminal", "reset session", "terminal reset"}:
        session = reset_terminal_session(user_id, session_name="default")
        return {"ok": True, "message": f"Terminal session reset. cwd={session.cwd}", "steps": []}
    if looks_like_direct_command(stripped_goal):
        return run_direct_terminal(user_id, stripped_goal)
    if not (settings.get("api_key") or ""):
        return {"ok": False, "message": "Please set API Key before using skill terminal.", "steps": []}
    return run_agent_terminal(user_id, goal, settings)


__all__ = ["run_skill_terminal"]

