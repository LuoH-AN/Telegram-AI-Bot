"""Content filtering utilities."""

import json
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
_LIKELY_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


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
    filtered = re.sub(r"<internal>.*?</internal>", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"\[thinking\].*?\[/thinking\]", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<\|think\|>.*?<\|/think\|>", "", filtered, flags=re.DOTALL)

    # Then, remove incomplete/unclosed blocks (for streaming)
    filtered = re.sub(r"<think>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<thinking>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<reasoning>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<reflection>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<internal>.*$", "", filtered, flags=re.DOTALL)
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
            r"</?(?:think|thinking|reasoning|reflection|internal)>|\[/?thinking\]|<\|/?think\|>",
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
    if match:
        section = match.group(1)
        calls = []
        for m in _RAW_TOOL_CALL_RE.finditer(section):
            name = m.group(1).strip()
            args = m.group(2).strip()
            if not _LIKELY_TOOL_NAME_RE.match(name):
                continue
            calls.append({
                "id": f"raw_{uuid.uuid4().hex[:8]}",
                "name": name,
                "arguments": args or "{}",
            })

        cleaned = _RAW_TOOL_SECTION_RE.sub('', text).strip()
        if calls:
            return calls, cleaned
        text = cleaned

    return _parse_json_tool_calls(text)


def _parse_json_tool_calls(text: str) -> tuple[list[dict], str]:
    """Parse bare JSON tool-call objects emitted as plain text.

    Some providers/models emit sequences like:
      {"name":"crawl4ai_fetch","arguments":{"url":"https://..."}}
      {"tool_name":"crawl4ai_fetch","url":"https://..."}
    when structured tool_calls are unavailable.
    """
    decoder = json.JSONDecoder()
    calls: list[dict] = []
    spans: list[tuple[int, int]] = []

    i = 0
    size = len(text)
    while i < size:
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, end = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            i += 1
            continue

        end_idx = i + end
        call = _extract_tool_call_obj(obj)
        if call:
            calls.append(call)
            spans.append((i, end_idx))
            i = end_idx
            continue
        i += 1

    if not spans:
        return [], text

    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            parts.append(text[cursor:start])
        cursor = end
    if cursor < len(text):
        parts.append(text[cursor:])
    cleaned = "".join(parts).strip()
    return calls, cleaned


def _extract_tool_call_obj(obj) -> dict | None:
    if not isinstance(obj, dict):
        return None

    name = ""
    args_obj = None

    if isinstance(obj.get("name"), str) and "arguments" in obj:
        name = obj["name"].strip()
        args_obj = obj.get("arguments")
    elif isinstance(obj.get("tool_name"), str):
        name = obj["tool_name"].strip()
        if "parameters" in obj:
            args_obj = obj.get("parameters")
        elif "arguments" in obj:
            args_obj = obj.get("arguments")
        else:
            args_obj = {
                k: v
                for k, v in obj.items()
                if k not in {"tool_name", "name", "tool", "arguments", "parameters"}
            }
    elif isinstance(obj.get("tool"), str):
        name = obj["tool"].strip()
        if "parameters" in obj:
            args_obj = obj.get("parameters")
        elif "arguments" in obj:
            args_obj = obj.get("arguments")
        else:
            args_obj = {
                k: v
                for k, v in obj.items()
                if k not in {"tool_name", "name", "tool", "arguments", "parameters"}
            }

    if not _LIKELY_TOOL_NAME_RE.match(name):
        return None

    args_dict = _normalize_tool_arguments(args_obj)
    return {
        "id": f"raw_{uuid.uuid4().hex[:8]}",
        "name": name,
        "arguments": json.dumps(args_dict, ensure_ascii=False),
    }


def _normalize_tool_arguments(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {"input": parsed}
        except json.JSONDecodeError:
            return {"input": value}
    return {"input": value}
