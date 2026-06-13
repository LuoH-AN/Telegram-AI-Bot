"""Pydantic request models for OpenAPI tool server."""

from __future__ import annotations

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
    query: str = Field(..., description="Search query text")
    top_k: int = Field(default=8, ge=1, le=20, description="Max results")
    timeout: int = Field(default=20, ge=3, le=120, description="HTTP timeout seconds")


class SearchStatusRequest(BaseModel):
    timeout: int = Field(default=20, ge=3, le=120, description="HTTP timeout seconds")


class PluginResponse(BaseModel):
    result: str = Field(..., description="Raw tool output (JSON string or text)")
