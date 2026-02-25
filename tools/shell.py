"""Shell tool — execute commands in the container."""

import logging
import os
import re
import subprocess

from .registry import BaseTool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 120
_MAX_OUTPUT = 10000
_HEAD_TAIL = 4000

# Patterns that should be blocked
_BLOCKED_PATTERNS = [
    r'\brm\s+-[^\s]*r[^\s]*f\s+/',          # rm -rf /
    r'\brm\s+-[^\s]*f[^\s]*r\s+/',          # rm -fr /
    r'\bshutdown\b',
    r'\breboot\b',
    r'\bpoweroff\b',
    r'\bhalt\b',
    r'\binit\s+[06]\b',
    r'\bmkfs\b',
    r'\bdd\b.*\bof=/dev/',                   # dd writing to devices
    r'\bsudo\b',
    r'\bsu\s',
    r':\(\)\s*\{\s*:\|:\s*&\s*\}\s*;',       # fork bomb :(){ :|:& };:
    r'\biptables\b',
    r'\bnft\b',
    r'\bcrontab\b',
    r'\bchmod\s+[0-7]*s',                    # setuid
    r'\bchown\s+-R\s+.*\s+/',               # recursive chown on /
    r'\bmount\b',
    r'\bumount\b',
    r'\bsystemctl\b',
    r'\bservice\b',
    r'\bnsenter\b',
    r'\bunshare\b',
    r'>\s*/dev/[sh]d',                       # redirect to block devices
    r'\bkill\s+-9\s+1\b',                    # kill init
    r'\bpkill\b.*-9',
    r'\bkillall\b',
]
_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

# Environment variable keywords to scrub
_SENSITIVE_KEYWORDS = [
    "TOKEN", "SECRET", "KEY", "PASSWORD", "PASSWD",
    "DATABASE_URL", "CREDENTIAL", "AUTH",
]


def _is_blocked(command: str) -> str | None:
    """Return a reason string if the command is blocked, else None."""
    for pattern in _BLOCKED_RE:
        if pattern.search(command):
            return f"Command blocked by security policy (matched: {pattern.pattern})"
    return None


def _clean_env() -> dict[str, str]:
    """Return a copy of os.environ with sensitive variables removed."""
    env = {}
    for k, v in os.environ.items():
        upper = k.upper()
        if any(kw in upper for kw in _SENSITIVE_KEYWORDS):
            continue
        env[k] = v
    return env


def _truncate_output(text: str) -> str:
    """Truncate output to _MAX_OUTPUT chars, keeping head and tail."""
    if len(text) <= _MAX_OUTPUT:
        return text
    head = text[:_HEAD_TAIL]
    tail = text[-_HEAD_TAIL:]
    skipped = len(text) - _HEAD_TAIL * 2
    return f"{head}\n\n... [{skipped} characters truncated] ...\n\n{tail}"


class ShellTool(BaseTool):
    """Execute shell commands in the container."""

    @property
    def name(self) -> str:
        return "shell"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "shell_exec",
                    "description": (
                        "Execute a shell command in the container and return the output. "
                        "Supports pipes, redirects, and chained commands. "
                        "Use for file operations, running scripts, system info, etc."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute",
                            },
                            "timeout": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": _MAX_TIMEOUT,
                                "default": _DEFAULT_TIMEOUT,
                                "description": f"Timeout in seconds (1-{_MAX_TIMEOUT}, default {_DEFAULT_TIMEOUT})",
                            },
                            "working_directory": {
                                "type": "string",
                                "description": "Working directory for the command (default: per-user temp dir)",
                            },
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name != "shell_exec":
            return f"Unknown tool: {tool_name}"

        command = (arguments.get("command") or "").strip()
        if not command:
            return "Error: No command provided."

        # Security check
        reason = _is_blocked(command)
        if reason:
            logger.warning("[user=%d] shell command blocked: %s", user_id, command[:200])
            return f"Error: {reason}"

        # Timeout
        timeout = _DEFAULT_TIMEOUT
        if arguments.get("timeout") is not None:
            try:
                timeout = max(1, min(_MAX_TIMEOUT, int(arguments["timeout"])))
            except (TypeError, ValueError):
                pass

        # Working directory
        default_cwd = f"/tmp/shell/{user_id}"
        cwd = (arguments.get("working_directory") or "").strip() or default_cwd
        os.makedirs(cwd, exist_ok=True)

        # Execute
        logger.info("[user=%d] shell_exec: %s (timeout=%ds, cwd=%s)", user_id, command[:200], timeout, cwd)
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=_clean_env(),
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            logger.warning("[user=%d] shell command timed out after %ds: %s", user_id, timeout, command[:200])
            return f"Error: Command timed out after {timeout} seconds."
        except Exception as e:
            logger.exception("[user=%d] shell exec error", user_id)
            return f"Error: {e}"

        # Build output
        parts = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        if result.returncode != 0:
            parts.append(f"[exit code: {result.returncode}]")

        output = "\n".join(parts) if parts else "(no output)"
        return _truncate_output(output)

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the shell_exec tool to execute shell commands in the container.\n"
            "Use it when the user asks you to run commands, write/run scripts, check system info, "
            "process files, or perform tasks that require a terminal.\n"
            "You can use pipes, redirects, and chain multiple commands.\n"
            "Each user has their own working directory at /tmp/shell/<user_id>/.\n"
        )
