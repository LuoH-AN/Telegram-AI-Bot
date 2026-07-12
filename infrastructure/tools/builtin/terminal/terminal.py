"""Terminal execution tools (allowlisted, with background jobs)."""

from __future__ import annotations

import asyncio

from infrastructure.tools.core import ToolContext, ToolResult, tool
from infrastructure.tools.core.sandbox import classify

from .background import (
    acknowledge_background_completion,
    arm_background_completion,
    check_background_job,
    kill_background_job,
    list_background_jobs,
    run_background,
    wait_background_job,
    write_background_job,
)
from .exec_fg import exec_foreground, resolve_cwd
from .store import get_session

TERMINAL_INSTRUCTION = (
    "\nTerminal tools:\n"
    "- `terminal`: run a shell command (foreground by default). Set background=true for long-running jobs.\n"
    "- For commands that may take more than a few seconds, set yield_ms=10000. The command becomes a persistent session only if it is still running.\n"
    "- `terminal_process`: list, poll, wait, write, submit, or kill persistent sessions by session_id.\n"
    "- Persistent sessions are owned by detached workers: they survive bot restarts and remain visible in later turns of the same conversation.\n"
    "- Use pty=true for interactive/TTY programs. Use terminal_process write/submit when a session needs input.\n"
    "- Destructive commands (rm -rf /, mkfs, fork bombs, dd to devices, shutdown) are blocked.\n"
    "- Risky commands (rm -r, sudo, force-push, curl|sh) automatically show the user approval buttons. The original tool call waits and resumes after their choice.\n"
    "- Do not ask the user for terminal approval in a separate assistant message; the terminal tool handles approval itself.\n"
    "\nCLI and plugin setup:\n"
    "- Use terminal for CLI/package installs and checks (npm/curl/pip, --version, real sample runs).\n"
    "- Terminal HOME, package-manager prefixes, caches, tools, and temporary files are routed into the fully backed-up persistent terminal filesystem under /data.\n"
    "- pip/npm/pnpm/cargo/go/uv/bun installs are automatically restored into PATH/PYTHONPATH after a cold restart; do not deliberately override their persistent prefixes.\n"
    "- Third-party skill managers (e.g. `npx skills add <url>`) run as their own setup; they do not register this agent's plugins.\n"
    "- This agent discovers external prompt plugins at `/data/plugins/<name>/SKILL.md`.\n"
)


def _job_in_context(ctx: ToolContext, job: dict | None) -> bool:
    if not job or int(job.get("user_id") or 0) != int(ctx.user_id):
        return False
    if ctx.session_id is None:
        return job.get("conversation_id") is None
    return job.get("conversation_id") == int(ctx.session_id)


@tool(toolset="system", skill="terminal", risk="confirm", danger=True, timeout=620, max_result_chars=20000, instruction=TERMINAL_INSTRUCTION, description="Execute a shell command without sandbox. Use yield_ms for seamless long-running execution, background for immediate persistent execution, and pty for interactive CLIs. Risky commands display approval buttons. Admin-only.")
async def terminal(
    ctx: ToolContext,
    command: str,
    cwd: str = "",
    timeout: int = 60,
    background: bool = False,
    yield_ms: int = 0,
    pty: bool = False,
) -> ToolResult:
    command = (command or "").strip()
    if not command:
        return ToolResult.error("empty_command", "command is required")
    cwd_path = resolve_cwd(cwd)
    verdict = classify(command)
    if verdict == "block":
        return ToolResult.error("blocked", "This command is blocked by the safety policy (destructive/irreversible). Reformulate it or ask the user to run it manually.", command=command)
    if verdict == "escalate":
        if ctx.confirm is None:
            return ToolResult.error("approval_unavailable", "This command requires interactive approval, but no approval UI is available. The command was not run.", command=command)
        choice = await ctx.confirm(command=command, cwd=str(cwd_path), timeout=300)
        if choice != "approve":
            code = "approval_timeout" if choice == "timeout" else "approval_denied"
            message = "Terminal approval timed out; the command was not run." if choice == "timeout" else "The user denied terminal approval; the command was not run."
            return ToolResult.error(code, message, command=command)
    managed_yield_ms = int(yield_ms)
    if pty and not background and managed_yield_ms <= 0:
        managed_yield_ms = 10_000
    if background or managed_yield_ms > 0:
        started = await asyncio.to_thread(
            run_background,
            command,
            cwd_path,
            user_id=ctx.user_id,
            chat_id=ctx.chat_id,
            conversation_id=ctx.session_id,
            pty=bool(pty),
            notify_on_exit=bool(background),
        )
        if background:
            return ToolResult.text(started)
        session_id = next(
            (line.split(":", 1)[1].strip() for line in started.splitlines() if line.startswith("Session:")),
            "",
        )
        if not session_id:
            return ToolResult.text(started)
        result = await asyncio.to_thread(
            wait_background_job,
            session_id,
            max(0.001, min(60, managed_yield_ms / 1000)),
            user_id=ctx.user_id,
            conversation_id=ctx.session_id,
        )
        job = await asyncio.to_thread(get_session, session_id)
        if _job_in_context(ctx, job) and job["status"] in {"starting", "running"}:
            await asyncio.to_thread(arm_background_completion, session_id)
        return ToolResult.text(result)
    return await asyncio.to_thread(exec_foreground, command, cwd_path, max(1, min(600, int(timeout))))


@tool(toolset="system", skill="terminal", danger=True, serial=True, timeout=70, max_result_chars=20000, description="Manage persistent terminal sessions. action=list|poll|wait|write|submit|kill. wait blocks up to timeout seconds; write sends raw data; submit appends a newline.")
async def terminal_process(
    ctx: ToolContext,
    action: str,
    session_id: str = "",
    data: str = "",
    timeout: int = 30,
) -> ToolResult:
    action = (action or "").strip().lower()
    if action == "list":
        return ToolResult.text(
            await asyncio.to_thread(
                list_background_jobs,
                user_id=ctx.user_id,
                conversation_id=ctx.session_id,
            )
        )
    if not session_id.strip():
        return ToolResult.error("missing_session_id", "session_id is required for this action")
    if action == "poll":
        result = await asyncio.to_thread(
            check_background_job,
            session_id,
            user_id=ctx.user_id,
            conversation_id=ctx.session_id,
        )
        job = await asyncio.to_thread(get_session, session_id)
        if (
            _job_in_context(ctx, job)
            and job["status"] not in {"starting", "running"}
            and not ctx.env.get("terminal_completion_session_id")
        ):
            await asyncio.to_thread(acknowledge_background_completion, session_id)
        return ToolResult.text(result)
    if action == "wait":
        result = await asyncio.to_thread(
            wait_background_job,
            session_id,
            max(0, min(60, int(timeout))),
            user_id=ctx.user_id,
            conversation_id=ctx.session_id,
        )
        job = await asyncio.to_thread(get_session, session_id)
        if (
            _job_in_context(ctx, job)
            and job["status"] not in {"starting", "running"}
            and not ctx.env.get("terminal_completion_session_id")
        ):
            await asyncio.to_thread(acknowledge_background_completion, session_id)
        return ToolResult.text(result)
    if action in {"write", "submit"}:
        return ToolResult.text(
            await asyncio.to_thread(
                write_background_job,
                session_id,
                data,
                submit=action == "submit",
                user_id=ctx.user_id,
                conversation_id=ctx.session_id,
            )
        )
    if action == "kill":
        return ToolResult.text(
            await asyncio.to_thread(
                kill_background_job,
                session_id,
                user_id=ctx.user_id,
                conversation_id=ctx.session_id,
            )
        )
    return ToolResult.error("invalid_action", "action must be list, poll, wait, write, submit, or kill")


@tool(toolset="system", skill="terminal", danger=True, max_result_chars=4000, description="List currently running and recently finished background terminal jobs.")
async def terminal_bg_list(ctx: ToolContext) -> ToolResult:
    return ToolResult.text(
        await asyncio.to_thread(
            list_background_jobs,
            user_id=ctx.user_id,
            conversation_id=ctx.session_id,
        )
    )


@tool(toolset="system", skill="terminal", danger=True, serial=True, max_result_chars=20000, description="Check the status and output of a background terminal job by pid.")
async def terminal_bg_check(ctx: ToolContext, pid: int) -> ToolResult:
    if int(pid) <= 1:
        return ToolResult.error("invalid_pid", "pid must be a real PID returned by a previous background run (not 0/1).")
    result = await asyncio.to_thread(
        check_background_job,
        int(pid),
        user_id=ctx.user_id,
        conversation_id=ctx.session_id,
    )
    job = await asyncio.to_thread(get_session, int(pid))
    if _job_in_context(ctx, job) and job["status"] not in {"starting", "running"}:
        await asyncio.to_thread(acknowledge_background_completion, int(pid))
    return ToolResult.text(result)
