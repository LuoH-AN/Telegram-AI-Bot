"""Execute runnable tool call items, serially or in parallel."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from config import TOOL_EXECUTOR_WORKERS

logger = logging.getLogger(__name__)


def _execute_one(user_id: int, item: tuple[int, object, object, str, dict], emit) -> tuple[int, dict]:
    idx, tool_call, tool, tool_name, args = item
    started_at = time.monotonic()
    emit("tool_start", index=idx, tool_name=tool_name, arguments=args)
    try:
        result = tool.execute(user_id, tool_name, args)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        logger.exception("[user=%d] tool execution failed: %s", user_id, tool_name)
        emit("tool_end", index=idx, tool_name=tool_name, ok=False, elapsed_ms=elapsed_ms, message=str(exc))
        return idx, {"role": "tool", "tool_call_id": tool_call.id, "content": f"Error: Tool execution failed - {exc}"}

    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    logger.info("[user=%d] tool call: %s(%s)", user_id, tool_name, json.dumps(args, ensure_ascii=False)[:200])
    preview = "OK"
    if result is not None:
        logger.info("[user=%d] tool result: %s (%d chars)", user_id, tool_name, len(result))
        preview = result[:180] + ("..." if len(result) > 180 else "")
    else:
        logger.info("[user=%d] tool result: %s -> OK (fire-and-forget)", user_id, tool_name)
    emit("tool_end", index=idx, tool_name=tool_name, ok=True, elapsed_ms=elapsed_ms, preview=preview)
    return idx, {"role": "tool", "tool_call_id": tool_call.id, "content": result if result is not None else "OK"}


def execute_runnable(user_id: int, runnable: list[tuple[int, object, object, str, dict]], *, force_serial: bool, emit) -> list[tuple[int, dict]]:
    if not runnable:
        return []
    if len(runnable) == 1 or force_serial:
        if force_serial and len(runnable) > 1:
            logger.info("[user=%d] serial-only tool detected, executing %d tool calls serially", user_id, len(runnable))
        return [_execute_one(user_id, item, emit) for item in runnable]

    workers = min(TOOL_EXECUTOR_WORKERS, len(runnable))
    logger.info("[user=%d] executing %d tool calls in parallel (workers=%d)", user_id, len(runnable), workers)
    pairs: list[tuple[int, dict]] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tool-call") as pool:
        futures = [pool.submit(_execute_one, user_id, item, emit) for item in runnable]
        for future in futures:
            pairs.append(future.result())
    return pairs

