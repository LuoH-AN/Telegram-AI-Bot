"""Text formatting utilities."""

import html
import re

from config import MAX_MESSAGE_LENGTH

# LaTeX symbol → Unicode mapping
_LATEX_SYMBOLS = {
    # Operators
    r"\times": "×", r"\div": "÷", r"\pm": "±", r"\mp": "∓",
    r"\cdot": "·", r"\ast": "∗", r"\star": "⋆", r"\circ": "∘",
    # Dots
    r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯", r"\vdots": "⋮",
    # Relations
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥",
    r"\neq": "≠", r"\ne": "≠", r"\approx": "≈", r"\equiv": "≡",
    r"\sim": "∼", r"\propto": "∝", r"\ll": "≪", r"\gg": "≫",
    # Arrows
    r"\to": "→", r"\rightarrow": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐",
    r"\leftrightarrow": "↔", r"\Leftrightarrow": "⇔",
    r"\mapsto": "↦", r"\uparrow": "↑", r"\downarrow": "↓",
    # Big operators
    r"\sum": "∑", r"\prod": "∏", r"\int": "∫",
    r"\iint": "∬", r"\iiint": "∭", r"\oint": "∮",
    # Set / logic
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\supset": "⊃",
    r"\subseteq": "⊆", r"\supseteq": "⊇",
    r"\cup": "∪", r"\cap": "∩", r"\emptyset": "∅", r"\varnothing": "∅",
    r"\forall": "∀", r"\exists": "∃", r"\nexists": "∄",
    r"\neg": "¬", r"\land": "∧", r"\lor": "∨",
    # Misc
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇",
    r"\angle": "∠", r"\triangle": "△", r"\perp": "⊥", r"\parallel": "∥",
    r"\degree": "°", r"\prime": "′",
    # Greek lowercase
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\theta": "θ", r"\vartheta": "ϑ", r"\iota": "ι", r"\kappa": "κ",
    r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ",
    r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ",
    r"\upsilon": "υ", r"\phi": "φ", r"\varphi": "φ", r"\chi": "χ",
    r"\psi": "ψ", r"\omega": "ω",
    # Greek uppercase
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Upsilon": "Υ",
    r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
}

_SUPERSCRIPT_MAP = str.maketrans("0123456789+-=()niax", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵃˣ")
_SUBSCRIPT_MAP = str.maketrans("0123456789+-=()aeiourx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢₒᵤᵣₓ")


def _convert_latex_content(latex: str) -> str:
    """Convert LaTeX math content (without delimiters) to Unicode text."""
    s = latex

    # \text{...}, \mathrm{...}, \mathbf{...} etc. → content
    s = re.sub(r'\\(?:text|mathrm|mathbf|mathit|mathsf|textbf|textit)\{([^}]*)\}', r'\1', s)

    # \frac{a}{b} → a/b
    s = re.sub(r'\\(?:d?frac)\{([^}]*)\}\{([^}]*)\}', r'(\1)/(\2)', s)

    # \sqrt[n]{x} → ⁿ√(x)
    def _sqrt_n(m):
        n, x = m.group(1), m.group(2)
        sup = n.translate(_SUPERSCRIPT_MAP)
        return f"{sup}√({x})"
    s = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]*)\}', _sqrt_n, s)

    # \sqrt{x} → √(x)
    s = re.sub(r'\\sqrt\{([^}]*)\}', r'√(\1)', s)

    # \overline{x} → x̄  (combining overline)
    s = re.sub(r'\\overline\{([^}]*)\}', lambda m: m.group(1) + '\u0305', s)

    # \hat{x} → x̂
    s = re.sub(r'\\hat\{([^}]*)\}', lambda m: m.group(1) + '\u0302', s)

    # Replace known symbols (sorted longest first to avoid partial matches)
    for cmd, uni in sorted(_LATEX_SYMBOLS.items(), key=lambda x: -len(x[0])):
        s = s.replace(cmd, uni)

    # Superscripts: ^{content}
    def _sup(m):
        content = m.group(1)
        translated = content.translate(_SUPERSCRIPT_MAP)
        if translated != content:
            return translated
        return f"^({content})"
    s = re.sub(r'\^\{([^}]*)\}', _sup, s)

    # Single char superscript: ^x
    def _sup_single(m):
        c = m.group(1)
        t = c.translate(_SUPERSCRIPT_MAP)
        return t if t != c else f"^{c}"
    s = re.sub(r'\^([0-9a-zA-Z])', _sup_single, s)

    # Subscripts: _{content}
    def _sub(m):
        content = m.group(1)
        translated = content.translate(_SUBSCRIPT_MAP)
        if translated != content:
            return translated
        return f"_({content})"
    s = re.sub(r'_\{([^}]*)\}', _sub, s)

    # Single char subscript: _x
    def _sub_single(m):
        c = m.group(1)
        t = c.translate(_SUBSCRIPT_MAP)
        return t if t != c else f"_{c}"
    s = re.sub(r'_([0-9a-zA-Z])', _sub_single, s)

    # \left( \right) \left[ \right] etc. → plain delimiters
    s = re.sub(r'\\(?:left|right|big|Big|bigg|Bigg)\s*([(\[{)\]}|.])', r'\1', s)

    # \{ \} → { }
    s = s.replace(r'\{', '{').replace(r'\}', '}')

    # \, \; \! \quad \qquad → space
    s = re.sub(r'\\[,;!\s]|\\q?quad', ' ', s)

    # Cleanup leftover backslash commands: \commandname → commandname
    s = re.sub(r'\\([a-zA-Z]+)', r'\1', s)

    # Collapse multiple spaces
    s = re.sub(r'  +', ' ', s)

    # Simplify redundant parens in fractions: strip parens from parts without operators
    def _simplify_frac(m):
        num, den = m.group(1), m.group(2)
        has_op = lambda x: bool(re.search(r'[+\-\s]', x))
        num_str = f"({num})" if has_op(num) else num
        den_str = f"({den})" if has_op(den) else den
        return f"{num_str}/{den_str}"
    s = re.sub(r'\(([^()]+)\)/\(([^()]+)\)', _simplify_frac, s)

    return s.strip()


def latex_to_unicode(text: str) -> str:
    """Convert LaTeX math expressions in text to readable Unicode.

    Handles both display math ($$...$$) and inline math ($...$).
    """
    if '$' not in text:
        return text

    # Protect code blocks and inline code from LaTeX processing
    code_placeholders = []

    def _save_code(m):
        code_placeholders.append(m.group(0))
        return f"\x01LATEXCODE{len(code_placeholders) - 1}\x01"

    text = re.sub(r'```.*?```', _save_code, text, flags=re.DOTALL)
    text = re.sub(r'`[^`]+`', _save_code, text)

    # Display math: $$...$$
    text = re.sub(r'\$\$(.*?)\$\$', lambda m: _convert_latex_content(m.group(1)), text, flags=re.DOTALL)

    # Inline math: $...$
    # Only match if content looks like actual LaTeX:
    # - Contains backslash commands, superscript, subscript, or braces
    # - OR contains a letter variable followed by a math operator (e.g. "A = B")
    # This avoids false positives on dollar amounts like "$50"
    def _inline_math(m):
        content = m.group(1)
        if re.search(r'[\\^_{}]|[a-zA-Z]\s*[=+\-<>]', content):
            return _convert_latex_content(content)
        return m.group(0)  # Not LaTeX, keep as-is

    text = re.sub(r'(?<!\$)\$(?!\$)((?:[^$\\]|\\.)+?)\$(?!\$)', _inline_math, text)

    # Restore code
    for i, code in enumerate(code_placeholders):
        text = text.replace(f"\x01LATEXCODE{i}\x01", code)

    return text


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML.

    Handles common Markdown syntax and converts to HTML that Telegram supports:
    - Headers: # text -> <b>text</b> (Telegram doesn't support h1-h6)
    - Horizontal rules: --- or *** or ___ -> ──────────
    - Unordered lists: - item / * item / + item -> • item
    - Ordered lists: 1. item (normalized spacing)
    - Bold: **text** or __text__ -> <b>text</b>
    - Italic: *text* or _text_ -> <i>text</i>
    - Code: `code` -> <code>code</code>
    - Code blocks: ```code``` -> <pre>code</pre>
    - Strikethrough: ~~text~~ -> <s>text</s>
    - Links: [text](url) -> <a href="url">text</a>
    """
    if not text:
        return text

    # Convert LaTeX math to Unicode before any other processing
    text = latex_to_unicode(text)

    # First, escape HTML special characters in the original text
    # But we need to be careful not to escape our converted HTML tags
    # So we'll process step by step

    # Store code blocks and inline code to protect them from other processing
    code_blocks = []
    inline_codes = []

    # Extract code blocks first (```...```)
    def save_code_block(match):
        code_blocks.append(match.group(1) or match.group(2))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    # Match ```lang\ncode``` or ```code```
    text = re.sub(r'```(?:\w*\n)?(.*?)```|```(.*?)```', save_code_block, text, flags=re.DOTALL)

    # Extract inline code (`...`)
    def save_inline_code(match):
        inline_codes.append(match.group(1))
        return f"\x00INLINECODE{len(inline_codes) - 1}\x00"

    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # Convert headers BEFORE escaping (# won't be escaped anyway)
    # Headers: # text, ## text, etc. -> bold text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', text, flags=re.MULTILINE)

    # Convert horizontal rules BEFORE escaping
    # ---, ***, ___ (3 or more) -> unicode line
    text = re.sub(r'^[-*_]{3,}\s*$', '──────────', text, flags=re.MULTILINE)

    # Convert lists BEFORE escaping
    # Unordered: - item, * item, + item -> • item
    # (must be done before italic to avoid * conflicts)
    text = re.sub(r'^([ \t]*)[-*+]\s+', r'\1• ', text, flags=re.MULTILINE)
    # Ordered: 1. item -> 1. item (normalize spacing only)
    text = re.sub(r'^([ \t]*)(\d+)\.\s+', r'\1\2. ', text, flags=re.MULTILINE)

    # Now escape HTML in the remaining text
    text = html.escape(text)

    # Convert Markdown to HTML
    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic: *text* or _text_ (but not inside words for _)
    text = re.sub(r'(?<!\w)\*([^*]+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', text)

    # Strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # Links: [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Restore code blocks
    for i, code in enumerate(code_blocks):
        escaped_code = html.escape(code)
        text = text.replace(f"\x00CODEBLOCK{i}\x00", f"<pre>{escaped_code}</pre>")

    # Restore inline code
    for i, code in enumerate(inline_codes):
        escaped_code = html.escape(code)
        text = text.replace(f"\x00INLINECODE{i}\x00", f"<code>{escaped_code}</code>")

    return text


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks that fit within Telegram's limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    # Split by paragraphs first
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_length:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            # If current chunk is not empty, save it
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # If paragraph itself is too long, split by lines
            if len(para) > max_length:
                lines = para.split("\n")
                for line in lines:
                    if len(current_chunk) + len(line) + 1 <= max_length:
                        if current_chunk:
                            current_chunk += "\n" + line
                        else:
                            current_chunk = line
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        # If line itself is too long, force split
                        if len(line) > max_length:
                            for i in range(0, len(line), max_length):
                                chunks.append(line[i : i + max_length])
                            current_chunk = ""
                        else:
                            current_chunk = line
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
