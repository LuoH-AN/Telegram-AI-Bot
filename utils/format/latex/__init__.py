"""LaTeX conversion for mixed prose/code text."""

from __future__ import annotations

import re

from .convert import convert_latex_content


def latex_to_unicode(text: str) -> str:
    """Convert LaTeX math expressions in text to readable Unicode."""
    if "$" not in text:
        return text
    code_placeholders = []

    def _save_code(match):
        code_placeholders.append(match.group(0))
        return f"\x03LATEXCODE{len(code_placeholders) - 1}\x03"

    text = re.sub(r'```.*?```', _save_code, text, flags=re.DOTALL)
    text = re.sub(r'`[^`]+`', _save_code, text)
    text = re.sub(r'\$\$(.*?)\$\$', lambda m: convert_latex_content(m.group(1)), text, flags=re.DOTALL)

    def _inline_math(match):
        content = match.group(1)
        if re.search(r'[\\^_{}]|[a-zA-Z]\s*[=+\-<>]', content):
            return convert_latex_content(content)
        return match.group(0)

    text = re.sub(r'(?<!\$)\$(?!\$)((?:[^$\\]|\\.)+?)\$(?!\$)', _inline_math, text)
    for index, code in enumerate(code_placeholders):
        text = text.replace(f"\x03LATEXCODE{index}\x03", code)
    return text
