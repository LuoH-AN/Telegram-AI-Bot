"""Tool call dispatch and status display for AI chat.

Handles executing tool calls, deduplication, timeout management,
and real-time status animation during tool execution.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING

from ai import ToolCall
from config import (
    MAX_TOOL_ROUNDS,
    TOOL_TIMEOUT,
    MAX_TOOL_ERROR_SNIPPETS,
)
from tools import process_tool_calls
from utils.ai_helpers import (
    effective_tool_timeout,
    tool_dedup_key,
)
from utils.platform_parity import SHARED_TOOL_STATUS_MAP

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def get_effective_tool_timeout(tool_calls: list[ToolCall]) -> int:
    """Return timeout for the handler-level wait_for."""
    return effective_tool_timeout(tool_calls, default_timeout=TOOL_TIMEOUT)


def is_tool_error_text(text: str) -> bool:
    """Heuristic: detect tool failures/timeouts from tool result text."""
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    return (
        normalized.startswith("error:")
        or "failed" in normalized
        or "rejected" in normalized
        or "timed out" in normalized
    )


def build_tool_status_lines(
    tool_calls: list[ToolCall],
    elapsed_seconds: int | None = None,
    overrides: dict[str, str] | None = None,
) -> list[str]:
    """Build deduplicated user-facing tool status lines."""
    order: list[str] = []
    counts: dict[str, int] = {}
    for tc in tool_calls:
        name = (tc.name or "").strip() or "tool"
        if name not in counts:
            order.append(name)
            counts[name] = 0
        counts[name] += 1

    lines: list[str] = []
    for name in order:
        base = (overrides or {}).get(name) or SHARED_TOOL_STATUS_MAP.get(name, f"Running {name}...")
        count_suffix = f" ×{counts[name]}" if counts[name] > 1 else ""
        elapsed_suffix = f" ({elapsed_seconds}s)" if elapsed_seconds is not None else ""
        lines.append(f"{base}{count_suffix}{elapsed_suffix}")
    return lines


def build_empty_response_fallback(tool_error_snippets: list[str]) -> str:
    """Build a user-facing fallback when the model returns empty content."""
    if not tool_error_snippets:
        return "(Empty response)"
    lines = "\n".join(f"- {snippet}" for snippet in tool_error_snippets[:MAX_TOOL_ERROR_SNIPPETS])
    return (
        "The model returned an empty response. Recent tool results:\n"
        f"{lines}\n"
        "Please retry."
    )


async def execute_tool_round(
    user_id: int,
    tool_calls: list[ToolCall],
    new_tool_calls: list[ToolCall],
    dup_indices: set[int],
    enabled_tools: str,
    display_text: str,
    thinking_prefix: str,
    stream_update: Callable,
    ctx: str,
) -> list[dict]:
    """Execute a round of tool calls with status animation.

    Handles deduplication, timeout, progress animation, and merges results
    in the original tool_calls order.

    Returns the merged list of tool results.
    """
    if new_tool_calls:
        timeout = get_effective_tool_timeout(new_tool_calls)
        tool_status_overrides: dict[str, str] = {}
        tool_status_dirty = asyncio.Event()
        tool_started_at = time.monotonic()
        tool_activity_lock = threading.Lock()
        tool_last_activity = time.monotonic()

        def _touch_tool_activity() -> None:
            nonlocal tool_last_activity
            with tool_activity_lock:
                tool_last_activity = time.monotonic()

        def _tool_activity_age() -> float:
            with tool_activity_lock:
                return time.monotonic() - tool_last_activity

        loop = asyncio.get_running_loop()

        def _on_tool_event(event: dict) -> None:
            event_type = str(event.get("type") or "").strip().lower()
            tool_name = str(event.get("tool_name") or "tool").strip() or "tool"
            _touch_tool_activity()

            if event_type == "tool_start":
                tool_status_overrides[tool_name] = SHARED_TOOL_STATUS_MAP.get(tool_name, f"Running {tool_name}...")
            elif event_type == "tool_progress":
                message = str(event.get("message") or "").strip()
                if message:
                    tool_status_overrides[tool_name] = message
            elif event_type == "tool_end":
                if not bool(event.get("ok", True)):
                    tool_status_overrides[tool_name] = f"{tool_name} failed"

            try:
                loop.call_soon_threadsafe(tool_status_dirty.set)
            except RuntimeError:
                pass

        # Animate status message while tools run
        _anim_active = True

        async def _animate_tool_status():
            try:
                while _anim_active:
                    try:
                        await asyncio.wait_for(tool_status_dirty.wait(), timeout=2.0)
                        tool_status_dirty.clear()
                    except asyncio.TimeoutError:
                        pass
                    if not _anim_active:
                        break
                    elapsed = max(1, int(time.monotonic() - tool_started_at))
                    animated_text = "\n".join(
                        build_tool_status_lines(
                            tool_calls,
                            elapsed_seconds=elapsed,
                            overrides=tool_status_overrides,
                        )
                    )
                    if display_text:
                        await stream_update(thinking_prefix + display_text + "\n\n" + animated_text)
                    else:
                        await stream_update(thinking_prefix + animated_text)
            except asyncio.CancelledError:
                pass

        tool_status_dirty.set()
        anim_task = asyncio.create_task(_animate_tool_status())

        try:
            tool_future = loop.run_in_executor(
                None,
                lambda: process_tool_calls(
                    user_id,
                    new_tool_calls,
                    enabled_tools=enabled_tools,
                    event_callback=_on_tool_event,
                ),
            )
            while True:
                try:
                    executed_results = await asyncio.wait_for(asyncio.shield(tool_future), timeout=1.0)
                    break
                except asyncio.TimeoutError:
                    if _tool_activity_age() > timeout:
                        raise asyncio.TimeoutError
        except asyncio.TimeoutError:
            logger.warning("%s tool timeout after %ds", ctx, timeout)
            executed_results = [
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Error: Tool execution timed out after {timeout}s.",
                }
                for tc in new_tool_calls
            ]
        finally:
            _anim_active = False
            anim_task.cancel()
    else:
        executed_results = []

    # Merge results in tool_calls order (dupes get immediate response)
    tool_results = []
    exec_idx = 0
    for i, tc in enumerate(tool_calls):
        if i in dup_indices:
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": "Already called with the same target. The result is in the conversation above. Please use it directly.",
            })
        else:
            tool_results.append(executed_results[exec_idx])
            exec_idx += 1

    return tool_results


def collect_tool_error_snippets(
    tool_results: list[dict],
    existing_snippets: list[str],
) -> list[str]:
    """Collect error snippets from tool results, deduplicating."""
    snippets = list(existing_snippets)
    for tr in tool_results:
        content = (tr.get("content") or "").strip()
        if not is_tool_error_text(content):
            continue
        snippet = content[:200] + ("..." if len(content) > 200 else "")
        if snippet in snippets:
            continue
        snippets.append(snippet)
        if len(snippets) > MAX_TOOL_ERROR_SNIPPETS:
            snippets = snippets[-MAX_TOOL_ERROR_SNIPPETS:]
    return snippets
