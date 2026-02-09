"""Content filtering utilities."""

import re


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
    # Remove <think>...</think> blocks (Claude style)
    filtered = re.sub(r"<think>.*?</think>", "", filtered, flags=re.DOTALL)
    # Remove <thinking>...</thinking> blocks
    filtered = re.sub(r"<thinking>.*?</thinking>", "", filtered, flags=re.DOTALL)
    # Remove <reasoning>...</reasoning> blocks
    filtered = re.sub(r"<reasoning>.*?</reasoning>", "", filtered, flags=re.DOTALL)
    # Remove [thinking]...[/thinking] blocks
    filtered = re.sub(r"\[thinking\].*?\[/thinking\]", "", filtered, flags=re.DOTALL)

    # Then, remove incomplete/unclosed blocks (for streaming)
    # Remove from opening tag to end of text if no closing tag
    filtered = re.sub(r"<think>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<thinking>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"<reasoning>.*$", "", filtered, flags=re.DOTALL)
    filtered = re.sub(r"\[thinking\].*$", "", filtered, flags=re.DOTALL)

    filtered = filtered.strip()

    # If filtering removed everything, strip tags only and keep the content.
    # Skip this during streaming — empty means "still thinking".
    if not streaming and not filtered and text.strip():
        filtered = re.sub(
            r"</?(?:think|thinking|reasoning)>|\[/?thinking\]", "", text
        )
        filtered = filtered.strip()

    return filtered
