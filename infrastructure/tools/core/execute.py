"""Async-native tool-call batch executor: validate, schedule, serialize."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

from .context import ToolContext, ToolResult
from .errors import error_content
from .events import bind_callback, emit, release_callback
from .registry import ToolEntry, registry
from .schema import validate

from infrastructure.config import TOOL_TIMEOUT

logger = logging.getLogger(__name__)


def _parse_arguments(raw) -> dict:
    text = raw.strip() if isinstance(raw, str) else str(raw or "").strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```")).strip()
    if not text or text.lower() == "null":
        return {}
    return json.loads(text)


def _truncate(content: str, limit: int) -> str:
    if 0 < limit < len(content):
        return content[:limit] + f"\n\n...(truncated, {len(content)} chars total)..."
    return content


def _resolve(tool_call, visible: dict[str, ToolEntry]):
    name = (tool_call.name or "").strip()
    entry = visible.get(name)
    if entry is None:
        return None, None, error_content("unknown_tool", f"Tool '{name}' is not available.", name=name)
    try:
        args = _parse_arguments(tool_call.arguments)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return entry, None, error_content("invalid_arguments", f"Invalid arguments: {exc}", raw=str(tool_call.arguments or "")[:500])
    if getattr(entry, "raw_args", False):
        return entry, args, None
    args, err = validate(entry.handler, args)
    if err:
        return entry, None, error_content("invalid_arguments", err, name=name)
    return entry, args, None


async def invoke_entry(entry: ToolEntry, ctx: ToolContext, args: dict) -> ToolResult:
    """Invoke a validated tool entry. Coerces non-ToolResult returns to text."""
    if entry.is_async:
        result = await entry.handler(ctx, **args)
    else:
        result = await asyncio.to_thread(entry.handler, ctx, **args)
    if isinstance(result, ToolResult):
        return result
    return ToolResult.text("" if result is None else str(result))


async def _run_one(user_id, item, build_context, event_callback):
    idx, tool_call, entry, args, preset_error = item
    name = (tool_call.name or "tool").strip()
    if preset_error is not None:
        emit(event_callback, user_id, "tool_error", index=idx, tool_name=name, reason="precheck")
        return idx, tool_call, preset_error
    ctx = build_context(user_id) if build_context else ToolContext(user_id=user_id)
    started = time.monotonic()
    emit(event_callback, user_id, "tool_start", index=idx, tool_name=name, arguments=args)
    timeout = getattr(entry, "timeout", 0) or TOOL_TIMEOUT
    try:
        invocation = asyncio.create_task(invoke_entry(entry, ctx, args))
        if getattr(entry, "side_effects", False):
            try:
                result = await asyncio.wait_for(asyncio.shield(invocation), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    "[user=%d] side-effecting tool %s exceeded %ds; waiting for a truthful outcome",
                    user_id,
                    name,
                    timeout,
                )
                emit(
                    event_callback,
                    user_id,
                    "tool_progress",
                    index=idx,
                    tool_name=name,
                    message="Operation exceeded its normal timeout and is finishing safely.",
                )
                result = await invocation
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(invocation)
                finally:
                    raise
        else:
            result = await asyncio.wait_for(invocation, timeout=timeout)
        content = _truncate(result.content, entry.max_result_chars)
        ok = result.ok
    except asyncio.TimeoutError:
        logger.warning("[user=%d] tool %s timed out after %ds", user_id, name, timeout)
        emit(event_callback, user_id, "tool_error", index=idx, tool_name=name, reason="timeout")
        content = error_content("timeout", f"Tool '{name}' timed out after {timeout}s", tool_name=name)
        ok = False
    except Exception as exc:
        logger.exception("[user=%d] tool %s failed", user_id, name)
        content = error_content("execution_failed", f"Tool execution failed: {exc}", exception_type=type(exc).__name__)
        ok = False
    elapsed = int((time.monotonic() - started) * 1000)
    emit(event_callback, user_id, "tool_end", index=idx, tool_name=name, ok=ok, elapsed_ms=elapsed)
    return idx, tool_call, content


async def execute_tool_calls(
    user_id: int,
    tool_calls: list,
    *,
    event_callback: Callable | None = None,
    build_context: Callable[[int], ToolContext] | None = None,
    visible: dict[str, ToolEntry] | None = None,
) -> list[dict]:
    if visible is None:
        visible = {entry.name: entry for entry in registry.all()}
    plan: list[tuple[int, object, ToolEntry | None, dict | None, str | None]] = []
    for idx, tool_call in enumerate(tool_calls):
        entry, args, error = _resolve(tool_call, visible)
        plan.append((idx, tool_call, entry, args, error))
    serial = any(item[2] and item[2].serial for item in plan)
    names = [(tc.name or "tool") for _, tc, *_ in plan]
    emit(event_callback, user_id, "tool_batch_start", count=sum(1 for p in plan if p[2]), total=len(tool_calls), serial=serial, tool_names=names)
    token = bind_callback(event_callback)
    try:
        if serial or len(plan) <= 1:
            results = []
            for item in plan:
                results.append(await _run_one(user_id, item, build_context, event_callback))
        else:
            results = await asyncio.gather(*[_run_one(user_id, item, build_context, event_callback) for item in plan])
    finally:
        release_callback(token)
    results.sort(key=lambda r: r[0])
    emit(event_callback, user_id, "tool_batch_end", count=len(results), total=len(tool_calls))
    return [{"role": "tool", "tool_call_id": tc.id, "content": content} for _, tc, content in results]
