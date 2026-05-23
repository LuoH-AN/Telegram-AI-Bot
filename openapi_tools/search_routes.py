"""Search plugin HTTP routes for OpenWebUI tool server."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from plugins.search.tool import SearchTool

from .auth import require_token
from .schemas import PluginResponse, SearchControlRequest, SearchQueryRequest

router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(require_token)])

_tool = SearchTool()
_OPENWEBUI_USER_ID = 0


def _control_args(payload: SearchControlRequest, action: str) -> dict:
    args: dict = {"action": action, "timeout": int(payload.timeout)}
    if payload.port is not None:
        args["port"] = int(payload.port)
    return args


@router.post("/query", response_model=PluginResponse, summary="Run a web search",
             description="Execute a web search via the integrated search skill. Returns JSON-encoded results.")
def search_query(payload: SearchQueryRequest) -> PluginResponse:
    args: dict = {
        "action": "search",
        "query": payload.query,
        "top_k": int(payload.top_k),
        "timeout": int(payload.timeout),
    }
    if payload.port is not None:
        args["port"] = int(payload.port)
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "search", args))


@router.post("/status", response_model=PluginResponse, summary="Search service status")
def search_status(payload: SearchControlRequest) -> PluginResponse:
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "search", _control_args(payload, "status")))


@router.post("/install", response_model=PluginResponse, summary="Install search binary/repo")
def search_install(payload: SearchControlRequest) -> PluginResponse:
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "search", _control_args(payload, "install")))


@router.post("/start", response_model=PluginResponse, summary="Start local search service")
def search_start(payload: SearchControlRequest) -> PluginResponse:
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "search", _control_args(payload, "start")))


@router.post("/stop", response_model=PluginResponse, summary="Stop local search service")
def search_stop(payload: SearchControlRequest) -> PluginResponse:
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "search", _control_args(payload, "stop")))
