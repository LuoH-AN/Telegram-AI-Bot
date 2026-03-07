"""Cron tool — create, list, and delete scheduled AI tasks."""

import logging

from .registry import BaseTool
from cache.manager import cache

logger = logging.getLogger(__name__)

MAX_TASKS_PER_USER = 10

CRON_CREATE_TOOL = {
    "type": "function",
    "function": {
        "name": "cron_create",
        "description": (
            "Create a scheduled task that runs periodically. "
            "The prompt will be sent to the AI at the scheduled time, "
            "and the result will be sent to the user on the current platform."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for this task (e.g. '日报', 'weather')",
                },
                "cron_expression": {
                    "type": "string",
                    "description": (
                        "Standard 5-field cron expression: minute hour day month weekday. "
                        "Examples: '0 8 * * *' (daily 8AM), '*/30 * * * *' (every 30min), "
                        "'0 9 * * 1-5' (weekdays 9AM). Time zone is UTC+8 (Beijing)."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "The instruction to execute at the scheduled time. Can reference tools like search.",
                },
            },
            "required": ["name", "cron_expression", "prompt"],
        },
    },
}

CRON_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "cron_list",
        "description": "List all scheduled tasks for the current user.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

CRON_DELETE_TOOL = {
    "type": "function",
    "function": {
        "name": "cron_delete",
        "description": "Delete a scheduled task by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the task to delete",
                },
            },
            "required": ["name"],
        },
    },
}

CRON_RUN_TOOL = {
    "type": "function",
    "function": {
        "name": "cron_run",
        "description": "Manually trigger a scheduled task to run immediately. The result will be sent as a separate message on the current platform.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the task to run",
                },
            },
            "required": ["name"],
        },
    },
}


class CronTool(BaseTool):
    """Tool for managing scheduled (cron) tasks."""

    @property
    def name(self) -> str:
        return "cron"

    def definitions(self) -> list[dict]:
        return [CRON_CREATE_TOOL, CRON_LIST_TOOL, CRON_DELETE_TOOL, CRON_RUN_TOOL]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name == "cron_create":
            return self._create(user_id, arguments)
        elif tool_name == "cron_list":
            return self._list(user_id)
        elif tool_name == "cron_delete":
            return self._delete(user_id, arguments)
        elif tool_name == "cron_run":
            return self._run(user_id, arguments)
        return f"Unknown tool: {tool_name}"

    def _create(self, user_id: int, arguments: dict) -> str:
        name = (arguments.get("name") or "").strip()
        cron_expr = (arguments.get("cron_expression") or "").strip()
        prompt = (arguments.get("prompt") or "").strip()

        if not name:
            return "Error: name is required."
        if not cron_expr:
            return "Error: cron_expression is required."
        if not prompt:
            return "Error: prompt is required."

        # Validate cron expression
        parts = cron_expr.split()
        if len(parts) != 5:
            return f"Error: cron_expression must have 5 fields (minute hour day month weekday), got {len(parts)}."

        task = cache.add_cron_task(user_id, name, cron_expr, prompt)
        if task is None:
            # Check if it's a duplicate or limit reached
            existing = cache.get_cron_tasks(user_id)
            if len(existing) >= MAX_TASKS_PER_USER:
                return f"Error: Maximum {MAX_TASKS_PER_USER} tasks reached. Delete some tasks first."
            return f"Error: A task named '{name}' already exists. Use a different name or delete it first."

        logger.info("[user=%d] cron task created: %s (%s)", user_id, name, cron_expr)
        return f"Scheduled task '{name}' created successfully.\nSchedule: {cron_expr}\nPrompt: {prompt}"

    def _list(self, user_id: int) -> str:
        tasks = cache.get_cron_tasks(user_id)
        if not tasks:
            return "No scheduled tasks. Use cron_create to create one."

        lines = []
        for t in tasks:
            status = "enabled" if t["enabled"] else "disabled"
            last_run = str(t["last_run_at"]) if t["last_run_at"] else "never"
            lines.append(
                f"- {t['name']} [{status}]\n"
                f"  Schedule: {t['cron_expression']}\n"
                f"  Prompt: {t['prompt'][:80]}{'...' if len(t['prompt']) > 80 else ''}\n"
                f"  Last run: {last_run}"
            )
        return f"Scheduled tasks ({len(tasks)}/{MAX_TASKS_PER_USER}):\n\n" + "\n\n".join(lines)

    def _delete(self, user_id: int, arguments: dict) -> str:
        name = (arguments.get("name") or "").strip()
        if not name:
            return "Error: name is required."

        if cache.delete_cron_task(user_id, name):
            logger.info("[user=%d] cron task deleted: %s", user_id, name)
            return f"Task '{name}' deleted successfully."
        return f"Error: Task '{name}' not found."

    def _run(self, user_id: int, arguments: dict) -> str:
        name = (arguments.get("name") or "").strip()
        if not name:
            return "Error: name is required."

        from services.cron import run_cron_task
        return run_cron_task(user_id, name)

    def get_instruction(self) -> str:
        return (
            "\n\nYou can manage scheduled tasks using cron tools "
            "(cron_create, cron_list, cron_delete, cron_run). "
            "Tasks run on a cron schedule (UTC+8 Beijing time) and send results to the user on the current platform. "
            "Use cron_run to manually trigger a task immediately. "
            "The prompt can use tools like web_search. Max 10 tasks per user."
        )
