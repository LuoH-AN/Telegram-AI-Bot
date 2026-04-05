"""Terminal execution tool for AI - no restrictions."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .base import BaseTool
from .terminal_persist import persist_install_command
from .terminal_bg_ops import check_bg_job, list_bg_jobs, run_background
from .terminal_bg_state import REPO_ROOT

logger = logging.getLogger(__name__)


class SkillTerminalTool(BaseTool):
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
                    "Use background=true for long-running commands; query with bg_check/bg_list."
                ),
                "parameters": self._parameters(),
            },
        }]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "cwd": {"type": "string", "description": "Working directory (default repository root)"},
                "timeout": {"type": "integer", "description": "Foreground timeout seconds (default 60)"},
                "background": {"type": "boolean", "description": "Run command in background"},
                "bg_check": {"type": "integer", "description": "Check background job by PID"},
                "bg_list": {"type": "boolean", "description": "List all background jobs"},
            },
            "required": [],
        }

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        if arguments.get("bg_list"):
            return list_bg_jobs()
        if arguments.get("bg_check") is not None:
            return check_bg_job(int(arguments["bg_check"]))

        command = str(arguments.get("command", "")).strip()
        if not command:
            return "Error: command is required (unless using bg_list or bg_check)."
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
