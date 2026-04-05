"""Main model/tool-call loop for Discord chat streaming."""
from __future__ import annotations
import asyncio
from ai import get_ai_client
from handlers.messages.streaming import stream_response
from utils import extract_thinking_blocks, filter_thinking_content
from ..config import SHOW_THINKING_MAX_CHARS, logger

def _append_thinking_segments(*, show_thinking: bool, full_response: str, reasoning_content: str | None, thinking_segments: list[str]) -> None:
    if not show_thinking:
        return
    tag_thinking, _ = extract_thinking_blocks(full_response)
    for segment in (reasoning_content, tag_thinking):
        cleaned = (segment or "").strip()
        if cleaned and (not thinking_segments or thinking_segments[-1] != cleaned):
            thinking_segments.append(cleaned)
async def run_stream_loop(
    *,
    user_id: int,
    log_ctx: str,
    settings: dict,
    messages: list[dict],
    reasoning_effort: str,
    stream_mode: str,
    show_thinking: bool,
    runtime,
) -> dict:
    from tools import get_all_tools, process_tool_calls

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_thinking_seconds = 0
    truncated_prefix = ""
    last_text_response = ""
    thinking_segments: list[str] = []
    tool_definitions = get_all_tools(enabled_tools="all")
    while True:
        full_response, usage_info, thinking_seconds, finish_reason, reasoning_content, tool_calls = await stream_response(
            get_ai_client(user_id),
            messages,
            settings["model"],
            settings["temperature"],
            reasoning_effort,
            runtime.stream_update,
            runtime.status_update,
            show_waiting=(not truncated_prefix),
            stream_mode=stream_mode,
            include_thought_prefix=True,
            stream_cursor=True,
            show_thinking=show_thinking,
            thinking_max_chars=SHOW_THINKING_MAX_CHARS,
            tools=tool_definitions,
        )
        total_thinking_seconds += thinking_seconds
        _append_thinking_segments(show_thinking=show_thinking, full_response=full_response, reasoning_content=reasoning_content, thinking_segments=thinking_segments)
        if usage_info:
            total_prompt_tokens += usage_info.get("prompt_tokens") or 0
            total_completion_tokens += usage_info.get("completion_tokens") or 0
        if full_response.strip():
            last_text_response = full_response
        if tool_calls:
            logger.info("%s model requested %d tool calls", log_ctx, len(tool_calls))
            if full_response.strip():
                await runtime.render_pump.drain()
                display_text = filter_thinking_content(full_response).strip()
                if display_text:
                    await runtime.outbound.deliver_final(display_text)
                    runtime.clear_placeholder_reference()
            tool_results = await asyncio.to_thread(
                process_tool_calls,
                user_id,
                tool_calls,
                "all",
                runtime.tool_event_callback,
            )
            messages.append({"role": "assistant", "content": full_response or "", "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}} for tc in tool_calls]})
            for result in tool_results:
                messages.append(result)
            continue
        if finish_reason == "length":
            logger.info("%s response truncated (finish_reason=length), requesting continuation", log_ctx)
            truncated_text = full_response or ""
            truncated_prefix += truncated_text
            messages.append({"role": "assistant", "content": truncated_text})
            messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
            continue
        break
    combined_response = truncated_prefix + last_text_response if truncated_prefix else last_text_response
    return {
        "messages": messages,
        "final_text_raw": combined_response,
        "last_text_response": last_text_response,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "thinking_seconds": total_thinking_seconds,
        "thinking_segments": thinking_segments,
    }
