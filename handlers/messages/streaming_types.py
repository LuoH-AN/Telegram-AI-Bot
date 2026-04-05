"""Runtime state containers for streaming response loop."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LiveStreamState:
    full_response: str = ""
    full_reasoning: str = ""
    usage_info: dict | None = None
    tool_calls: list = field(default_factory=list)
    first_chunk: bool = True
    finish_reason: str | None = None
    last_update_time: float = 0.0
    last_update_length: int = 0
    stream_start_time: float = 0.0
    last_output_activity: float | None = None
    waiting_start_time: float = 0.0
    waiting_active: bool = False
    thinking_start_time: float | None = None
    thinking_seconds: int = 0
    thinking_locked: bool = False
