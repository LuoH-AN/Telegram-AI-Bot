"""Terminal execution tools (allowlisted, with background jobs)."""

from __future__ import annotations

import asyncio

from infrastructure.tools.core import ToolContext, ToolResult, tool
from infrastructure.tools.core.sandbox import classify

from .background import check_background_job, list_background_jobs, run_background
from .exec_fg import exec_foreground, resolve_cwd

TERMINAL_INSTRUCTION = (
    "\nTerminal tools:\n"
    "- `terminal`: run a shell command (foreground by default). Set background=true for long-running jobs.\n"
    "- `terminal_bg_list`: list background jobs.\n"
    "- `terminal_bg_check`: check a background job by pid (use only a pid returned by a prior background run).\n"
    "- Destructive commands (rm -rf /, mkfs, fork bombs, dd to devices, shutdown) are blocked.\n"
    "- Risky commands (rm -r, sudo, force-push, curl|sh) return needs_confirmation. Ask the user, and if they agree, re-call terminal with the SAME command and confirmed=true.\n"
    "- Never set confirmed=true unless the user explicitly agreed to that exact command.\n"
    "\nCLI and plugin setup:\n"
    "- Use terminal for CLI/package installs and checks (npm/curl/pip, --version, real sample runs).\n"
    "- If global install is unavailable, install CLIs into a persistent path such as /data/bin and verify future shells find them.\n"
    "- Third-party skill managers (e.g. `npx skills add <url>`) run as their own setup; they do not register this agent's plugins.\n"
    "- This agent discovers external prompt plugins at `runtime/plugins/<name>/SKILL.md`.\n"
)


@tool(toolset="system", skill="terminal", risk="confirm", danger=True, timeout=620, max_result_chars=20000, instruction=TERMINAL_INSTRUCTION, description="Execute a shell command without sandbox. Foreground by default; background=true for long-running jobs. Risky commands need confirmed=true after the user agrees. Admin-only.")
async def terminal(ctx: ToolContext, command: str, cwd: str = "", timeout: int = 60, background: bool = False, confirmed: bool = False) -> ToolResult:
    command = (command or "").strip()
    if not command:
        return ToolResult.error("empty_command", "command is required")
    verdict = classify(command)
    if verdict == "block":
        return ToolResult.error("blocked", "This command is blocked by the safety policy (destructive/irreversible). Reformulate it or ask the user to run it manually.", command=command)
    if verdict == "escalate" and not confirmed:
        return ToolResult.error("needs_confirmation", "This command may be destructive. Ask the user to confirm before running it, then re-call with confirmed=true.", command=command)
    cwd_path = resolve_cwd(cwd)
    if background:
        return ToolResult.text(await asyncio.to_thread(run_background, command, cwd_path))
    return await asyncio.to_thread(exec_foreground, command, cwd_path, max(1, min(600, int(timeout))))


@tool(toolset="system", skill="terminal", danger=True, max_result_chars=4000, description="List currently running and recently finished background terminal jobs.")
async def terminal_bg_list(ctx: ToolContext) -> ToolResult:
    return ToolResult.text(await asyncio.to_thread(list_background_jobs))


@tool(toolset="system", skill="terminal", danger=True, serial=True, max_result_chars=20000, description="Check the status and output of a background terminal job by pid.")
async def terminal_bg_check(ctx: ToolContext, pid: int) -> ToolResult:
    if int(pid) <= 1:
        return ToolResult.error("invalid_pid", "pid must be a real PID returned by a previous background run (not 0/1).")
    return ToolResult.text(await asyncio.to_thread(check_background_job, int(pid)))
