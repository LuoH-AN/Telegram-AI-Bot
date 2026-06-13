"""Terminal plugin HTTP routes — exposed as its own FastAPI sub-app."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.plugins.terminal import TerminalTool

from .auth import require_token
from .schemas import PluginResponse, TerminalBgCheckRequest, TerminalExecRequest

router = APIRouter(tags=["terminal"], dependencies=[Depends(require_token)])

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
             description="Inspect a background job by its PID returned from a previous /exec background=true call.")
def terminal_bg_check(payload: TerminalBgCheckRequest) -> PluginResponse:
    args = {"action": "bg_check", "bg_pid": int(payload.bg_pid)}
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "terminal", args))


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
