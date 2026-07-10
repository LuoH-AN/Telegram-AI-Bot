"""Pydantic request models for OpenAPI tool server."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TerminalExecRequest(BaseModel):
    command: str = Field(..., description="Shell command to execute")
    cwd: str = Field(default="", description="Working directory (default repo root)")
    timeout: int = Field(default=60, ge=1, le=3600, description="Foreground timeout seconds")
    background: bool = Field(default=False, description="Run in background and return pid")


class TerminalBgListRequest(BaseModel):
    include_completed: bool = Field(default=True, description="Include completed jobs in the result")


class TerminalBgCheckRequest(BaseModel):
    bg_pid: int = Field(..., ge=2, description="PID returned from a previous background run")


class SearchQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Focused search query text")
    top_k: int = Field(default=5, ge=1, le=20, description="Max results")
    timeout: int = Field(default=20, ge=3, le=120, description="HTTP timeout seconds")
    category: Literal["", "company", "research paper", "news", "personal site", "financial report", "people"] = Field(default="", description="Optional Exa search category")
    time_range: Literal["", "day", "week", "month", "year"] = Field(default="", description="Optional recency filter")
    include_domains: str = Field(default="", description="Optional comma-separated domain allowlist")
    exclude_domains: str = Field(default="", description="Optional comma-separated domain blocklist")
    search_type: Literal["auto", "fast", "instant", "deep-lite", "deep", "deep-reasoning"] = Field(default="auto", description="Exa search mode")
    exact_match: bool = Field(default=False, description="Require the complete query phrase in returned evidence")
    user_location: str = Field(default="", max_length=2, description="Optional two-letter ISO country code")
    include_content: bool = Field(default=True, description="Include extracted evidence from top pages")
    content_top_k: int = Field(default=3, ge=0, le=5, description="Top pages eligible for fallback extraction")


class SearchStatusRequest(BaseModel):
    timeout: int = Field(default=20, ge=3, le=120, description="HTTP timeout seconds")


class PluginResponse(BaseModel):
    result: str = Field(..., description="Raw tool output (JSON string or text)")
