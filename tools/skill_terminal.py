"""Terminal execution tool for AI - no restrictions."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .base import BaseTool

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


class SkillTerminalTool(BaseTool):
    """Terminal tool callable by AI with no security restrictions."""

    @property
    def name(self) -> str:
        return "terminal"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "terminal",
                    "description": "Execute terminal commands. Can be used to install dependencies, download files, manipulate filesystem, manage processes, and any other terminal operations. No security restrictions.",
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (optional, defaults to repository root)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60)",
                },
            },
            "required": ["command"],
        }

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        command = str(arguments.get("command", "")).strip()
        cwd = str(arguments.get("cwd", "")).strip() or str(REPO_ROOT)
        timeout = int(arguments.get("timeout", 60))

        if not command:
            return "Error: command is required."

        # Normalize working directory
        cwd_path = Path(cwd)
        if not cwd_path.is_absolute():
            cwd_path = REPO_ROOT / cwd_path
        cwd_path = cwd_path.resolve()

        logger.info(
            "skill_terminal: user=%s, command=%s, cwd=%s", user_id, command, cwd_path
        )

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output_parts = []
            if result.stdout:
                output_parts.append(f"stdout:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"stderr:\n{result.stderr}")
            output_parts.append(f"exit_code: {result.returncode}")

            return "\n\n".join(output_parts)

        except subprocess.TimeoutExpired:
            return f"Error: command execution timeout ({timeout}s)."
        except Exception as e:
            logger.exception("skill_terminal execution failed")
            return f"Error: {e}"
