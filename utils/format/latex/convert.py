"""Low-level LaTeX content to Unicode conversion."""

from __future__ import annotations

import re

from .map import LATEX_SYMBOLS, SUBSCRIPT_MAP, SUPERSCRIPT_MAP


def convert_latex_content(latex: str) -> str:
    s = latex
    s = re.sub(r'\\(?:text|mathrm|mathbf|mathit|mathsf|textbf|textit)\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\(?:d?frac)\{([^}]*)\}\{([^}]*)\}', r'(\1)/(\2)', s)

    def _sqrt_n(match):
        n, x = match.group(1), match.group(2)
        return f"{n.translate(SUPERSCRIPT_MAP)}√({x})"

    s = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]*)\}', _sqrt_n, s)
    s = re.sub(r'\\sqrt\{([^}]*)\}', r'√(\1)', s)
    s = re.sub(r'\\overline\{([^}]*)\}', lambda m: m.group(1) + '\u0305', s)
    s = re.sub(r'\\hat\{([^}]*)\}', lambda m: m.group(1) + '\u0302', s)
    for cmd, uni in sorted(LATEX_SYMBOLS.items(), key=lambda x: -len(x[0])):
        s = s.replace(cmd, uni)

    def _sup(match):
        content = match.group(1)
        translated = content.translate(SUPERSCRIPT_MAP)
        return translated if translated != content else f"^({content})"

    def _sup_single(match):
        c = match.group(1)
        translated = c.translate(SUPERSCRIPT_MAP)
        return translated if translated != c else f"^{c}"

    def _sub(match):
        content = match.group(1)
        translated = content.translate(SUBSCRIPT_MAP)
        return translated if translated != content else f"_({content})"

    def _sub_single(match):
        c = match.group(1)
        translated = c.translate(SUBSCRIPT_MAP)
        return translated if translated != c else f"_{c}"

    s = re.sub(r'\^\{([^}]*)\}', _sup, s)
    s = re.sub(r'\^([0-9a-zA-Z])', _sup_single, s)
    s = re.sub(r'_\{([^}]*)\}', _sub, s)
    s = re.sub(r'_([0-9a-zA-Z])', _sub_single, s)
    s = re.sub(r'\\(?:left|right|big|Big|bigg|Bigg)\s*([(\[{)\]}|.])', r'\1', s)
    s = s.replace(r'\{', '{').replace(r'\}', '}')
    s = re.sub(r'\\[,;!\s]|\\q?quad', ' ', s)
    s = re.sub(r'\\([a-zA-Z]+)', r'\1', s)
    s = re.sub(r'  +', ' ', s)

    def _simplify_frac(match):
        num, den = match.group(1), match.group(2)
        has_op = lambda x: bool(re.search(r'[+\-\s]', x))
        return f"{f'({num})' if has_op(num) else num}/{f'({den})' if has_op(den) else den}"

    s = re.sub(r'\(([^()]+)\)/\(([^()]+)\)', _simplify_frac, s)
    return s.strip()
