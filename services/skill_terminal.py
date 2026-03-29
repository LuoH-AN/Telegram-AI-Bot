"""AI-driven terminal workflow for installing and managing skills."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .terminal_exec import DEFAULT_TIMEOUT_SECONDS, REPO_ROOT, execute_terminal_command
from .user import get_user_settings
from openai import OpenAI

logger = logging.getLogger(__name__)

MAX_TERMINAL_STEPS = 8
SKILL_TERMINAL_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_SECONDS

_SYSTEM_PROMPT = """You are a local Skill terminal agent. Your goal is to complete Skill installation, organization, deletion, and debugging through step-by-step shell commands.

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


def _safe_json_loads(payload: str) -> dict | None:
    try:
        value = json.loads(payload)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _build_messages(goal: str, history: list[dict]) -> list[dict]:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "User goal:\n"
                f"{goal.strip()}\n\n"
                f"Repository root: {REPO_ROOT}\n"
                "If you need to install or organize Skills, prioritize actions around runtime_skills, manifest.json, handler.py, and GitHub skill sources."
            ),
        },
    ]
    messages.extend(history)
    return messages


def _normalize_cwd(cwd: str | None) -> str:
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
    if REPO_ROOT == resolved or REPO_ROOT in resolved.parents:
        return str(resolved)
    return str(REPO_ROOT)


def _coerce_step(payload: dict | None, fallback_error: str) -> dict:
    if not payload:
        return {
            "done": True,
            "command": "",
            "cwd": str(REPO_ROOT),
            "summary": "Model did not return valid JSON.",
            "final_message": fallback_error,
        }
    done = bool(payload.get("done"))
    command = str(payload.get("command") or "").strip()
    final_message = str(payload.get("final_message") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    cwd = _normalize_cwd(str(payload.get("cwd") or ""))
    if not done and not command:
        done = True
        final_message = final_message or fallback_error
    if done and not final_message:
        final_message = summary or "Skill terminal process completed."
    return {
        "done": done,
        "command": command,
        "cwd": cwd,
        "summary": summary,
        "final_message": final_message,
    }


def run_skill_terminal(user_id: int, goal: str) -> dict:
    settings = get_user_settings(user_id)
    api_key = settings.get("api_key") or ""
    if not api_key:
        return {
            "ok": False,
            "message": "Please set API Key before using skill terminal.",
            "steps": [],
        }
    client = OpenAI(api_key=api_key, base_url=settings["base_url"])
    model = settings.get("model") or ""
    history: list[dict] = []
    steps: list[dict] = []

    for index in range(1, MAX_TERMINAL_STEPS + 1):
        messages = _build_messages(goal, history)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw_response = response.choices[0].message.content or ""
        step = _coerce_step(_safe_json_loads(raw_response), "Skill terminal did not return executable action.")
        steps.append(
            {
                "step": index,
                "summary": step["summary"],
                "command": step["command"],
                "cwd": step["cwd"],
            }
        )
        history.append({"role": "assistant", "content": json.dumps(step, ensure_ascii=False)})
        if step["done"]:
            return {
                "ok": True,
                "message": step["final_message"],
                "steps": steps,
                "raw_response": raw_response,
            }

        result = execute_terminal_command(
            user_id,
            step["command"],
            cwd=step["cwd"],
            timeout_seconds=SKILL_TERMINAL_TIMEOUT_SECONDS,
        )
        history.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "command_result": result,
                        "instruction": "Based on the command result above, decide the next step; if the task is completed or cannot continue, set done=true.",
                    },
                    ensure_ascii=False,
                ),
            }
        )
        if not result["ok"] and result["exit_code"] == -1:
            return {
                "ok": False,
                "message": result["stderr"] or "Skill terminal command rejected.",
                "steps": steps,
            }

    logger.warning("skill_terminal exceeded max steps for user %s", user_id)
    return {
        "ok": False,
        "message": "Skill terminal reached maximum steps, task not completed.",
        "steps": steps,
    }
