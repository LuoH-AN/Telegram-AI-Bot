"""AI-guided terminal execution loop."""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from services.terminal_exec import execute_terminal_command

from .common import MAX_TERMINAL_STEPS, SKILL_TERMINAL_TIMEOUT_SECONDS, build_messages, coerce_step, safe_json_loads

logger = logging.getLogger(__name__)


def run_agent_terminal(user_id: int, goal: str, settings: dict) -> dict:
    client = OpenAI(api_key=settings.get("api_key") or "", base_url=settings["base_url"])
    model = settings.get("model") or ""
    history: list[dict] = []
    steps: list[dict] = []

    for index in range(1, MAX_TERMINAL_STEPS + 1):
        response = client.chat.completions.create(
            model=model,
            messages=build_messages(goal, history),
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw_response = response.choices[0].message.content or ""
        step = coerce_step(safe_json_loads(raw_response), "Skill terminal did not return executable action.")
        steps.append({"step": index, "summary": step["summary"], "command": step["command"], "cwd": step["cwd"]})
        history.append({"role": "assistant", "content": json.dumps(step, ensure_ascii=False)})
        if step["done"]:
            return {"ok": True, "message": step["final_message"], "steps": steps, "raw_response": raw_response}

        result = execute_terminal_command(
            user_id,
            step["command"],
            cwd=step["cwd"],
            timeout_seconds=SKILL_TERMINAL_TIMEOUT_SECONDS,
            session_name="default",
        )
        history.append(
            {
                "role": "user",
                "content": json.dumps(
                    {"command_result": result, "instruction": "Based on the command result above, decide the next step; if complete or blocked, set done=true."},
                    ensure_ascii=False,
                ),
            }
        )
        if not result["ok"] and result["exit_code"] == -1:
            return {"ok": False, "message": result["stderr"] or "Skill terminal command rejected.", "steps": steps}

    logger.warning("skill_terminal exceeded max steps for user %s", user_id)
    return {"ok": False, "message": "Skill terminal reached maximum steps, task not completed.", "steps": steps}

