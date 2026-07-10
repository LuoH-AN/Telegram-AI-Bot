"""Terminal tool HTTP routes — exposed as its own FastAPI sub-app.

Dispatched through the unified tool registry (same path as the chat pipeline),
not a separate tool instance — single source of truth for schema and behavior.
The old single function with action=exec/bg_list/bg_check is now three native
tools (terminal, terminal_bg_list, terminal_bg_check).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import is_admin
from infrastructure.tools import invoke_tool

from .auth import cors_options, require_token
from .schemas import PluginResponse, TerminalBgCheckRequest, TerminalBgListRequest, TerminalExecRequest

router = APIRouter(tags=["terminal"], dependencies=[Depends(require_token)])

def _openapi_user_id() -> int:
    raw = (os.getenv("OPENAPI_TOOLS_USER_ID") or "").strip()
    if not raw.lstrip("-").isdigit():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAPI_TOOLS_USER_ID is not configured",
        )
    user_id = int(raw)
    if not is_admin(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OPENAPI_TOOLS_USER_ID must be listed in ADMIN_IDS or OWNER_ID",
        )
    return user_id


@router.post("/exec", response_model=PluginResponse, summary="Execute a shell command",
             description="Run a shell command on the bot host. Returns stdout/stderr/exit_code.")
async def terminal_exec(payload: TerminalExecRequest) -> PluginResponse:
    args: dict = {"command": payload.command, "timeout": int(payload.timeout), "background": bool(payload.background)}
    if payload.cwd:
        args["cwd"] = payload.cwd
    result = await invoke_tool(_openapi_user_id(), "terminal", args)
    return PluginResponse(result=result.content)


@router.post("/bg/list", response_model=PluginResponse, summary="List background jobs",
             description="Return all known background terminal jobs and their status.")
async def terminal_bg_list(_payload: TerminalBgListRequest) -> PluginResponse:
    result = await invoke_tool(_openapi_user_id(), "terminal_bg_list", {})
    return PluginResponse(result=result.content)


@router.post("/bg/check", response_model=PluginResponse, summary="Check a background job",
             description="Inspect a background job by its PID returned from a previous /exec background=true call.")
async def terminal_bg_check(payload: TerminalBgCheckRequest) -> PluginResponse:
    result = await invoke_tool(_openapi_user_id(), "terminal_bg_check", {"pid": int(payload.bg_pid)})
    return PluginResponse(result=result.content)


def build_terminal_app() -> FastAPI:
    """Standalone FastAPI sub-app for the terminal tool (own /openapi.json)."""
    app = FastAPI(
        title="Terminal Tool",
        version="1.0.0",
        description="Execute shell commands on the bot host. Import this URL into OpenWebUI as its own tool server.",
    )
    app.add_middleware(CORSMiddleware, **cors_options())
    app.include_router(router)
    return app
