"""Content filtering utilities."""
import re

_THINKING_BLOCK_PATTERNS = [
    re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<reflection>(.*?)</reflection>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<internal>(.*?)</internal>", re.DOTALL | re.IGNORECASE),
    re.compile(r"\[thinking\](.*?)\[/thinking\]", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\|think\|>(.*?)<\|/think\|>", re.DOTALL | re.IGNORECASE),
]
_THINKING_COMPLETE_PATTERNS = [
    r"<think>.*?</think>",
    r"<thinking>.*?</thinking>",
    r"<reasoning>.*?</reasoning>",
    r"<reflection>.*?</reflection>",
    r"<internal>.*?</internal>",
    r"\[thinking\].*?\[/thinking\]",
    r"<\|think\|>.*?<\|/think\|>",
]
_THINKING_INCOMPLETE_PATTERNS = [
    r"<think>.*$",
    r"<thinking>.*$",
    r"<reasoning>.*$",
    r"<reflection>.*$",
    r"<internal>.*$",
    r"\[thinking\].*$",
    r"<\|think\|>.*$",
]
_TAG_STRIP_PATTERN = r"</?(?:think|thinking|reasoning|reflection|internal)>|\[/?thinking\]|<\|/?think\|>"


def filter_thinking_content(text: str, streaming: bool = False) -> str:
    filtered = text
    for pattern in _THINKING_COMPLETE_PATTERNS:
        filtered = re.sub(pattern, "", filtered, flags=re.DOTALL)
    for pattern in _THINKING_INCOMPLETE_PATTERNS:
        filtered = re.sub(pattern, "", filtered, flags=re.DOTALL)
    filtered = filtered.strip()

    if not streaming and not filtered and text.strip():
        filtered = re.sub(_TAG_STRIP_PATTERN, "", text).strip()
    return filtered


def extract_thinking_blocks(text: str) -> tuple[str, str]:
    if not text:
        return "", text

    spans: list[tuple[int, int, str]] = []
    for pattern in _THINKING_BLOCK_PATTERNS:
        for match in pattern.finditer(text):
            content = match.group(1) if match.lastindex else ""
            spans.append((match.start(), match.end(), content))
    if not spans:
        return "", text

    spans.sort(key=lambda item: item[0])
    merged: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, content in spans:
        if start < last_end:
            continue
        merged.append((start, end, content))
        last_end = end

    blocks: list[str] = []
    cleaned_parts: list[str] = []
    last_idx = 0
    for start, end, content in merged:
        cleaned_parts.append(text[last_idx:start])
        last_idx = end
        snippet = (content or "").strip()
        if snippet:
            blocks.append(snippet)
    cleaned_parts.append(text[last_idx:])

    thinking_text = "\n\n".join(blocks).strip()
    cleaned_text = "".join(cleaned_parts)
    return thinking_text, cleaned_text


def format_thinking_block(thinking_text: str, *, seconds: int | float | None = None, max_chars: int = 1200) -> str:
    raw = (thinking_text or "").strip()
    if not raw:
        return ""

    if max_chars > 0 and len(raw) > max_chars:
        trimmed = raw[:max_chars]
        last_break = trimmed.rfind("\n")
        if last_break >= max_chars * 0.6:
            trimmed = trimmed[:last_break]
        raw = trimmed.rstrip() + "\n... (truncated)"

    title = "Thoughts"
    if seconds is not None and seconds > 0:
        title = f"{title} ({int(seconds)}s)"

    return f"**{title}**\n\x02BQXSTART\x02{raw}\x02BQXEND\x02\n\n"
