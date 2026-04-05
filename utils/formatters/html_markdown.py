"""HTML to Markdown conversion facade."""

from __future__ import annotations

from .html_cleanup import preprocess_html
from .html_parse import parse_html_to_markdown
from .html_tables import finalize_markdown


def html_to_markdown(html_content: str, base_url: str = "") -> str:
    """Convert HTML content to Markdown format."""
    cleaned = preprocess_html(html_content)
    if not cleaned:
        return ""
    parsed = parse_html_to_markdown(cleaned, base_url=base_url)
    return finalize_markdown(parsed)
