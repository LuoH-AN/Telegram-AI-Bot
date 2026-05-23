"""Search plugin HTTP routes — exposed as its own FastAPI sub-app."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plugins.search.tool import SearchTool

from .auth import require_token
from .schemas import PluginResponse, SearchQueryRequest, SearchStatusRequest

router = APIRouter(tags=["search"], dependencies=[Depends(require_token)])

_tool = SearchTool()
_OPENWEBUI_USER_ID = 0


@router.post("/query", response_model=PluginResponse, summary="Run a web search",
             description="Execute a web search via Tavily. Returns JSON-encoded results.")
def search_query(payload: SearchQueryRequest) -> PluginResponse:
    args: dict = {
        "action": "search",
        "query": payload.query,
        "top_k": int(payload.top_k),
        "timeout": int(payload.timeout),
    }
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "search", args))


@router.post("/status", response_model=PluginResponse, summary="Search backend status (key pool)")
def search_status(payload: SearchStatusRequest) -> PluginResponse:
    args = {"action": "status", "timeout": int(payload.timeout)}
    return PluginResponse(result=_tool.execute(_OPENWEBUI_USER_ID, "search", args))


def build_search_app() -> FastAPI:
    """Standalone FastAPI sub-app for the search tool (own /openapi.json)."""
    app = FastAPI(
        title="Search Tool",
        version="2.0.0",
        description="Tavily-backed web search. Import this URL into OpenWebUI as its own tool server.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app
