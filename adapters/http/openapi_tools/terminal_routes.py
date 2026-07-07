"""Terminal tool HTTP routes — exposed as its own FastAPI sub-app.

Dispatched through the unified tool registry (same path as the chat pipeline),
not a separate tool instance — single source of truth for schema and behavior.
The old single function with action=exec/bg_list/bg_check is now three native
tools (terminal, terminal_bg_list, terminal_bg_check).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.tools import invoke_tool

from .auth import require_token
from .schemas import PluginResponse, TerminalBgCheckRequest, TerminalBgListRequest, TerminalExecRequest

router = APIRouter(tags=["terminal"], dependencies=[Depends(require_token)])

_OPENWEBUI_USER_ID = 0


@router.post("/exec", response_model=PluginResponse, summary="Execute a shell command",
             description="Run a shell command on the bot host. Returns stdout/stderr/exit_code.")
async def terminal_exec(payload: TerminalExecRequest) -> PluginResponse:
    args: dict = {"command": payload.command, "timeout": int(payload.timeout), "background": bool(payload.background)}
    if payload.cwd:
        args["cwd"] = payload.cwd
    result = await invoke_tool(_OPENWEBUI_USER_ID, "terminal", args)
    return PluginResponse(result=result.content)


@router.post("/bg/list", response_model=PluginResponse, summary="List background jobs",
             description="Return all known background terminal jobs and their status.")
async def terminal_bg_list(_payload: TerminalBgListRequest) -> PluginResponse:
    result = await invoke_tool(_OPENWEBUI_USER_ID, "terminal_bg_list", {})
    return PluginResponse(result=result.content)


@router.post("/bg/check", response_model=PluginResponse, summary="Check a background job",
             description="Inspect a background job by its PID returned from a previous /exec background=true call.")
async def terminal_bg_check(payload: TerminalBgCheckRequest) -> PluginResponse:
    result = await invoke_tool(_OPENWEBUI_USER_ID, "terminal_bg_check", {"pid": int(payload.bg_pid)})
    return PluginResponse(result=result.content)


def build_terminal_app() -> FastAPI:
    """Standalone FastAPI sub-app for the terminal tool (own /openapi.json)."""
    app = FastAPI(
        title="Terminal Tool",
        version="1.0.0",
        description="Execute shell commands on the bot host. Import this URL into OpenWebUI as its own tool server.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app
