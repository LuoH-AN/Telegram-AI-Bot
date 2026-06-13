"""Pre-cleanup for HTML->Markdown conversion."""

from __future__ import annotations

import re

from ..style import strip_style_blocks


def preprocess_html(html_content: str) -> str:
    if not html_content or not html_content.strip():
        return ""
    html_content = strip_style_blocks(html_content)
    html_content = re.sub(r"<!--\[?-->", "", html_content)
    html_content = re.sub(r"<!--.*?-->", "", html_content, flags=re.DOTALL)
    return html_content
