"""Direct shell-mode helpers for skill terminal."""

from services.terminal_exec import execute_terminal_command

from .common import SKILL_TERMINAL_TIMEOUT_SECONDS

DIRECT_PREFIXES = ("cmd:", "exec:", "shell:")
TERMINAL_HELP_TEXT = (
    "skill_terminal usage:\n"
    "- direct command: cmd: npm install -g @mermaid-js/mermaid-cli\n"
    "- direct command: shell: python -m pip install httpie\n"
    "- inspect session: session\n"
    "- reset session: reset terminal\n"
    "- AI guided task: describe the goal in natural language\n\n"
    "Session features:\n"
    "- persistent cwd\n"
    "- persistent exported env vars\n"
    "- supports cd / pwd / env / export / unset / reset-session\n"
)


def looks_like_direct_command(goal: str) -> bool:
    text = (goal or "").strip().lower()
    if not text:
        return False
    if text.startswith(DIRECT_PREFIXES) or text in {"pwd", "env", "reset", "reset-session"}:
        return True
    prefixes = (
        "cd ", "ls", "cat ", "pwd", "env", "python ", "python3 ", "pip ", "pip3 ", "uv ", "npm ", "pnpm ", "yarn ",
        "npx ", "node ", "git ", "curl ", "wget ", "apt ", "apt-get ", "brew ", "cargo ", "go ", "docker ", "make ",
        "pytest", "ruff", "mypy", "bash ", "sh ",
    )
    return any(text.startswith(prefix) for prefix in prefixes)


def strip_direct_prefix(goal: str) -> str:
    text = (goal or "").strip()
    lower = text.lower()
    for prefix in DIRECT_PREFIXES:
        if lower.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def run_direct_terminal(user_id: int, goal: str) -> dict:
    command = strip_direct_prefix(goal)
    result = execute_terminal_command(
        user_id,
        command,
        session_name="default",
        timeout_seconds=SKILL_TERMINAL_TIMEOUT_SECONDS,
    )
    return {
        "ok": bool(result.get("ok")),
        "message": result["stdout"] or result["stderr"] or "(no output)",
        "steps": [{
            "step": 1,
            "summary": "direct terminal execution",
            "command": command,
            "cwd": result.get("cwd"),
            "session_name": result.get("session_name", "default"),
            "exit_code": result.get("exit_code"),
        }],
        "result": result,
    }

