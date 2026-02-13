"""Content filtering utilities."""

import re

# All supported thinking tag patterns (opening tags for detection)
_THINK_OPEN_TAGS = re.compile(
    r"<think>|<thinking>|<reasoning>|<reflection>|\[thinking\]|<\|think\|>",
    re.IGNORECASE,
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

    filtered = filtered.strip()

    # If filtering removed everything, strip tags only and keep the content.
    # Skip this during streaming — empty means "still thinking".
    if not streaming and not filtered and text.strip():
        filtered = re.sub(
            r"</?(?:think|thinking|reasoning|reflection)>|\[/?thinking\]|<\|/?think\|>",
            "",
            text,
        )
        filtered = filtered.strip()

    return filtered


def has_thinking_tags(text: str) -> bool:
    """Check if text contains any known thinking opening tag."""
    return bool(_THINK_OPEN_TAGS.search(text))
