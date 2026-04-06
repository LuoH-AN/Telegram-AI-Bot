"""Terminal execution tool for AI - no restrictions."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ..core.base import BaseTool
from .background import check_background_job, list_background_jobs, run_background
from .persist import persist_install_command
from .state import REPO_ROOT

logger = logging.getLogger(__name__)


class TerminalTool(BaseTool):
    @property
    def name(self) -> str:
        return "terminal"

    def definitions(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "terminal",
                "description": (
                    "Execute terminal commands without sandbox restrictions. "
                    "Use action=exec for normal commands, action=bg_list to list background jobs, "
                    "and action=bg_check with a real bg_pid from previous background run."
                ),
                "parameters": self._parameters(),
            },
        }]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["exec", "bg_list", "bg_check"],
                    "description": "Operation to run. Prefer explicit action.",
                },
                "command": {"type": "string", "description": "Shell command to execute"},
                "cwd": {"type": "string", "description": "Working directory (default repository root)"},
                "timeout": {"type": "integer", "description": "Foreground timeout seconds (default 60)"},
                "background": {"type": "boolean", "description": "Run command in background"},
                "bg_pid": {"type": "integer", "description": "PID for action=bg_check"},
                "bg_check": {"type": "integer", "description": "Deprecated alias of bg_pid"},
                "bg_list": {"type": "boolean", "description": "Deprecated alias of action=bg_list"},
            },
            "required": [],
        }

    def get_instruction(self) -> str:
        return (
            "\nTerminal tool usage:\n"
            "- For normal shell commands, call terminal with action='exec' and command.\n"
            "- Only call action='bg_check' when you already have a real PID returned by a previous background run.\n"
            "- Never use bg_check with 0/1 or guessed values.\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        action = self._resolve_action(arguments)
        if action == "bg_list":
            return list_background_jobs()
        if action == "bg_check":
            pid_value = arguments.get("bg_pid")
            if pid_value is None:
                pid_value = arguments.get("bg_check")
            try:
                pid = int(pid_value)
            except Exception:
                return (
                    "Error: action=bg_check requires integer bg_pid. "
                    "Use action=exec with command for normal terminal commands."
                )
            if pid <= 1:
                return (
                    "Error: invalid bg_pid. Do not use guessed values like 0/1. "
                    "Use action=bg_check only with a PID returned by a previous background run."
                )
            return check_background_job(pid)
        if action != "exec":
            return (
                "Error: invalid action. Use one of: exec, bg_list, bg_check.\n"
                "Examples:\n"
                "- {\"action\":\"exec\",\"command\":\"pwd && ls -la\"}\n"
                "- {\"action\":\"bg_list\"}\n"
                "- {\"action\":\"bg_check\",\"bg_pid\":12345}"
            )

        command = str(arguments.get("command", "")).strip()
        if not command:
            return "Error: action=exec requires non-empty command."
        cwd = str(arguments.get("cwd", "")).strip() or str(REPO_ROOT)
        cwd_path = Path(cwd)
        if not cwd_path.is_absolute():
            cwd_path = REPO_ROOT / cwd_path
        cwd_path = cwd_path.resolve()

        if arguments.get("background"):
            return run_background(command, cwd_path, logger)

        timeout = int(arguments.get("timeout", 60))
        logger.info("skill_terminal: user=%s, command=%s, cwd=%s", user_id, command, cwd_path)
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            parts = []
            if result.stdout:
                parts.append(f"stdout:\n{result.stdout}")
            if result.stderr:
                parts.append(f"stderr:\n{result.stderr}")
            parts.append(f"exit_code: {result.returncode}")
            if result.returncode == 0:
                persist_note = persist_install_command(command)
                if persist_note:
                    parts.append(persist_note)
            return "\n\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"Error: command execution timeout ({timeout}s). Consider using background=true for long-running commands."
        except Exception as exc:
            logger.exception("skill_terminal execution failed")
            return f"Error: {exc}"

    @staticmethod
    def _resolve_action(arguments: dict) -> str:
        action = str(arguments.get("action", "")).strip().lower()
        if action:
            return action
        if arguments.get("bg_list"):
            return "bg_list"
        if arguments.get("bg_pid") is not None or arguments.get("bg_check") is not None:
            return "bg_check"
        if str(arguments.get("command", "")).strip():
            return "exec"
        return ""

