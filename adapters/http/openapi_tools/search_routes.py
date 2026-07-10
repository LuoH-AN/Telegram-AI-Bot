"""Search tool HTTP routes — exposed as its own FastAPI sub-app.

Dispatched through the unified tool registry (same path as the chat pipeline),
not a separate tool instance — single source of truth for schema and behavior.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.tools import invoke_tool

from .auth import cors_options, require_token
from .schemas import PluginResponse, SearchQueryRequest, SearchStatusRequest

router = APIRouter(tags=["search"], dependencies=[Depends(require_token)])

_OPENWEBUI_USER_ID = 0


@router.post("/query", response_model=PluginResponse, summary="Run a web search",
             description="Execute a web search via Exa. Returns JSON-encoded results.")
async def search_query(payload: SearchQueryRequest) -> PluginResponse:
    result = await invoke_tool(_OPENWEBUI_USER_ID, "search", {
        "action": "search",
        "query": payload.query,
        "top_k": int(payload.top_k),
        "timeout": int(payload.timeout),
        "category": payload.category,
        "time_range": payload.time_range,
        "include_domains": payload.include_domains,
        "exclude_domains": payload.exclude_domains,
        "search_type": payload.search_type,
        "exact_match": payload.exact_match,
        "user_location": payload.user_location,
        "include_content": payload.include_content,
        "content_top_k": payload.content_top_k,
    })
    return PluginResponse(result=result.content)


@router.post("/status", response_model=PluginResponse, summary="Search backend status (key pool)")
async def search_status(payload: SearchStatusRequest) -> PluginResponse:
    result = await invoke_tool(_OPENWEBUI_USER_ID, "search", {"action": "status", "timeout": int(payload.timeout)})
    return PluginResponse(result=result.content)


def build_search_app() -> FastAPI:
    """Standalone FastAPI sub-app for the search tool (own /openapi.json)."""
    app = FastAPI(
        title="Search Tool",
        version="2.0.0",
        description="Exa-backed web search. Import this URL into OpenWebUI as its own tool server.",
    )
    app.add_middleware(CORSMiddleware, **cors_options())
    app.include_router(router)
    return app
