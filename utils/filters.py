"""Content filtering utilities."""

import re
import uuid

# Raw tool call markup patterns (e.g., Qwen-style models)
_RAW_TOOL_SECTION_RE = re.compile(
    r'<\|tool_calls_section_begin\|>(.*?)<\|tool_calls_section_end\|>',
    re.DOTALL,
)
_RAW_TOOL_SECTION_OPEN_RE = re.compile(
    r'<\|tool_calls_section_begin\|>.*$',
    re.DOTALL,
)
_RAW_TOOL_CALL_RE = re.compile(
    r'<\|tool_call_begin\|>\s*(\S+?)(?::\d+)?\s*'
    r'<\|tool_call_argument_begin\|>\s*(.*?)\s*<\|tool_call_end\|>',
    re.DOTALL,
)


def filter_thinking_content(text: str, streaming: bool = False) -> str:
    """Filter out thinking/reasoning content from the response.

    Handles both complete and incomplete (streaming) thinking blocks.
    For incomplete blocks, removes from opening tag to end of text.

    Args:
        text: The text to filter.
        streaming: If True, skip the fallback that keeps content when all text
                   is inside think tags. During streaming, returning empty means
                   "still thinking" which lets the caller show a thinking indicator.
    """
    filtered = text

    # First, remove complete blocks
    filtered = re.sub(r"<think>.*?</think>", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<thinking>.*?</thinking>", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<reasoning>.*?</reasoning>", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<reflection>.*?</reflection>", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"\[thinking\].*?\[/thinking\]", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<\|think\|>.*?<\|/think\|>", "", filtered, flags=re.DOTALL)

    # Then, remove incomplete/unclosed blocks (for streaming)
    filtered = re.sub(r"<think>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<thinking>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<reasoning>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<reflection>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"\[thinking\].*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<\|think\|>.*$", "", filtered, flags=re.DOTALL)

    # Remove raw tool call markup (models may output tool calls as plain text)
    filtered = _RAW_TOOL_SECTION_RE.sub('', filtered)
    filtered = _RAW_TOOL_SECTION_OPEN_RE.sub('', filtered)

    filtered = filtered.strip()

    # If filtering removed everything, strip tags only and keep the content.
    # Skip this during streaming — empty means "still thinking".
    if not streaming and not filtered and text.strip():
        filtered = re.sub(
            r"</?(?:think|thinking|reasoning|reflection)>|\[/?thinking\]|<\|/?think\|>",
            "",
            text,
        )
        filtered = _RAW_TOOL_SECTION_RE.sub('', filtered)
        filtered = _RAW_TOOL_SECTION_OPEN_RE.sub('', filtered)
        filtered = filtered.strip()

    return filtered


def parse_raw_tool_calls(text: str) -> tuple[list[dict], str]:
    """Parse raw tool call markup that some models output as plain text.

    Models like Qwen may emit tool calls as text markup instead of using
    the API's structured tool_calls field.  This function extracts them.

    Returns:
        (tool_calls, cleaned_text) where tool_calls is a list of dicts
        with 'id', 'name', and 'arguments' keys.
    """
    match = _RAW_TOOL_SECTION_RE.search(text)
    if not match:
        return [], text

    section = match.group(1)
    calls = []
    for m in _RAW_TOOL_CALL_RE.finditer(section):
        name = m.group(1).strip()
        args = m.group(2).strip()
        calls.append({
            "id": f"raw_{uuid.uuid4().hex[:8]}",
            "name": name,
            "arguments": args,
        })

    cleaned = _RAW_TOOL_SECTION_RE.sub('', text).strip()
    return calls, cleaned
