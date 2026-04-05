"""Shared constants/helpers for skill terminal workflow."""

from __future__ import annotations

import json
from pathlib import Path

from services.terminal_exec import DEFAULT_TIMEOUT_SECONDS, REPO_ROOT

MAX_TERMINAL_STEPS = 8
SKILL_TERMINAL_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_SECONDS
SYSTEM_PROMPT = """You are a local Skill terminal agent. Your goal is to complete Skill installation, organization, deletion, and debugging through step-by-step shell commands.

Constraints:
1. You can only return one JSON object each time, no markdown output.
2. JSON format must be:
   {"done": boolean, "command": string, "cwd": string, "summary": string, "final_message": string}
3. When done=false, you must provide the next command; when done=true, set command to empty string.
4. cwd must be a path within the repository, preferably /root/Telegram-AI-Bot.
5. Focus on Skill installation/management, avoid unrelated system operations.
6. When command output is sufficient to reach a conclusion, immediately set done=true.
7. If failure prevents continuation, set done=true and clearly explain the failure reason in final_message.
"""


def safe_json_loads(payload: str) -> dict | None:
    try:
        value = json.loads(payload)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def build_messages(goal: str, history: list[dict]) -> list[dict]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "User goal:\n"
                f"{goal.strip()}\n\n"
                f"Repository root: {REPO_ROOT}\n"
                "If you need to install or organize Skills, prioritize runtime_skills, manifest.json, handler.py, and GitHub skill sources."
            ),
        },
    ]
    messages.extend(history)
    return messages


def normalize_cwd(cwd: str | None) -> str:
    raw = (cwd or "").strip()
    if not raw:
        return str(REPO_ROOT)
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        resolved = path.resolve()
    except Exception:
        return str(REPO_ROOT)
    return str(resolved) if REPO_ROOT == resolved or REPO_ROOT in resolved.parents else str(REPO_ROOT)


def coerce_step(payload: dict | None, fallback_error: str) -> dict:
    if not payload:
        return {"done": True, "command": "", "cwd": str(REPO_ROOT), "summary": "Model did not return valid JSON.", "final_message": fallback_error}
    done = bool(payload.get("done"))
    command = str(payload.get("command") or "").strip()
    final_message = str(payload.get("final_message") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    cwd = normalize_cwd(str(payload.get("cwd") or ""))
    if not done and not command:
        done, final_message = True, (final_message or fallback_error)
    if done and not final_message:
        final_message = summary or "Skill terminal process completed."
    return {"done": done, "command": command, "cwd": cwd, "summary": summary, "final_message": final_message}

