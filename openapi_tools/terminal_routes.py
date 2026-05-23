"""Terminal plugin HTTP routes for OpenWebUI tool server."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from plugins.terminal import TerminalTool

from .auth import require_token
from .schemas import PluginResponse, TerminalBgCheckRequest, TerminalExecRequest

router = APIRouter(prefix="/terminal", tags=["terminal"], dependencies=[Depends(require_token)])

_tool = TerminalTool()
_OPENWEBUI_USER_ID = 0


@router.post("/exec", response_model=PluginResponse, summary="Execute a shell command",
             description="Run a shell command on the bot host. Returns stdout/stderr/exit_code.")
def terminal_exec(payload: TerminalExecRequest) -> PluginResponse:
    args = {
        "action": "exec",
        "command": payload.command,
        "timeout": int(payload.timeout),
        "background": bool(payload.background),
    }
    if payload.cwd:
        args["cwd"] = payload.cwd
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "terminal", args))


@router.post("/bg/list", response_model=PluginResponse, summary="List background jobs",
             description="Return all known background terminal jobs and their status.")
def terminal_bg_list() -> PluginResponse:
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "terminal", {"action": "bg_list"}))


@router.post("/bg/check", response_model=PluginResponse, summary="Check a background job",
             description="Inspect a background job by its PID returned from a previous /terminal/exec background=true call.")
def terminal_bg_check(payload: TerminalBgCheckRequest) -> PluginResponse:
    args = {"action": "bg_check", "bg_pid": int(payload.bg_pid)}
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "terminal", args))
