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


def strip_style_blocks(text: str) -> str:
    """Remove embedded CSS/style blocks from HTML/Markdown text."""
    if not text:
        return ""

    cleaned = text
    # Raw HTML style/script/noscript blocks.
    cleaned = re.sub(
        r"<(?:style|script|noscript)\b[^>]*>.*?</(?:style|script|noscript)\s*>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Escaped HTML style blocks that can leak from upstream markdown generators.
    cleaned = re.sub(
        r"&lt;style\b[^&]*&gt;.*?&lt;/style&gt;",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


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
        return f"\x03LATEXCODE{len(code_placeholders) - 1}\x03"

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
        text = text.replace(f"\x03LATEXCODE{i}\x03", code)

    return text


def _format_cell(cell: str) -> str:
    """Convert inline Markdown in a table cell to Telegram HTML.

    Handles inline code, bold, italic, strikethrough, and placeholder restoration.
    """
    # Restore inline code placeholders first, then process markdown
    # Inline code placeholders: \x00INLINECODE{n}\x00 (may have lost \x00 via html.escape)
    codes = []

    def _save(m):
        codes.append(m.group(1))
        return f"\x02IC{len(codes) - 1}\x02"

    cell = re.sub(r'`([^`]+)`', _save, cell)

    # Escape HTML
    cell = html.escape(cell)

    # Bold
    cell = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', cell)
    cell = re.sub(r'__(.+?)__', r'<b>\1</b>', cell)
    # Italic
    cell = re.sub(r'(?<!\w)\*([^*]+?)\*(?!\w)', r'<i>\1</i>', cell)
    cell = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', cell)
    # Strikethrough
    cell = re.sub(r'~~(.+?)~~', r'<s>\1</s>', cell)

    # Restore inline code
    for i, code in enumerate(codes):
        cell = cell.replace(f"\x02IC{i}\x02", f"<code>{html.escape(code)}</code>")

    return cell


def _markdown_table_to_html(table_text: str) -> str:
    """Convert a markdown table block to Telegram-friendly HTML.

    Each data row is rendered as:
        <b>Header1</b>: Value1
        <b>Header2</b>: Value2
    with blank lines between rows.
    """
    lines = [l.strip() for l in table_text.strip().split('\n') if l.strip()]
    if len(lines) < 3:
        return html.escape(table_text)

    def parse_row(line: str) -> list[str]:
        s = line.strip()
        if s.startswith('|'):
            s = s[1:]
        if s.endswith('|'):
            s = s[:-1]
        return [c.strip() for c in s.split('|')]

    headers = parse_row(lines[0])
    rows = [parse_row(line) for line in lines[2:]]

    parts = []
    for row in rows:
        row_parts = []
        for i, cell in enumerate(row):
            h = html.escape(headers[i]) if i < len(headers) else ""
            formatted_cell = _format_cell(cell)
            if h:
                row_parts.append(f"<b>{h}</b>: {formatted_cell}")
            else:
                row_parts.append(formatted_cell)
        parts.append("\n".join(row_parts))

    return "\n\n".join(parts)


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
    - Blockquotes: > text -> <blockquote>text</blockquote>
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
        return f"\x02CODEBLOCK{len(code_blocks) - 1}\x02"

    # Match ```lang\ncode``` or ```code```
    text = re.sub(r'```(?:\w*\n)?(.*?)```|```(.*?)```', save_code_block, text, flags=re.DOTALL)

    # Extract and convert markdown tables BEFORE inline code extraction,
    # so that _format_cell sees the original backtick syntax in cells.
    table_placeholders = []

    def save_table(match):
        block = match.group(0)
        lines = [l.strip() for l in block.strip().split('\n') if l.strip()]
        if len(lines) < 3:
            return block
        # Validate separator row (second line must be like |---|---|)
        sep_inner = lines[1].strip().strip('|')
        sep_cells = [c.strip() for c in sep_inner.split('|')]
        if not all(re.match(r'^:?-+:?$', c) for c in sep_cells if c):
            return block
        table_html = _markdown_table_to_html(block)
        table_placeholders.append(table_html)
        return f"\x02TABLE{len(table_placeholders) - 1}\x02"

    text = re.sub(
        r'(?:^[ \t]*\|.+\|[ \t]*$\n?){3,}',
        save_table, text, flags=re.MULTILINE,
    )

    # Extract inline code (`...`) — AFTER tables so table cells keep backticks
    def save_inline_code(match):
        inline_codes.append(match.group(1))
        return f"\x02INLINECODE{len(inline_codes) - 1}\x02"

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

    # Blockquotes: > text -> <blockquote>text</blockquote>
    # Merge consecutive > lines into a single blockquote block
    def convert_blockquotes(t):
        lines = t.split('\n')
        result = []
        bq_lines = []

        def flush_bq():
            if bq_lines:
                content = '\n'.join(bq_lines)
                result.append(f'\x02BQSTART\x02{content}\x02BQEND\x02')
                bq_lines.clear()

        for line in lines:
            m = re.match(r'^>\s?(.*)', line)
            if m:
                bq_lines.append(m.group(1))
            else:
                flush_bq()
                result.append(line)
        flush_bq()
        return '\n'.join(result)

    text = convert_blockquotes(text)

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
        text = text.replace(f"\x02CODEBLOCK{i}\x02", f"<pre>{escaped_code}</pre>")

    # Restore inline code
    for i, code in enumerate(inline_codes):
        escaped_code = html.escape(code)
        text = text.replace(f"\x02INLINECODE{i}\x02", f"<code>{escaped_code}</code>")

    # Restore tables (already contain final HTML)
    for i, tbl in enumerate(table_placeholders):
        text = text.replace(f"\x02TABLE{i}\x02", tbl)

    # Restore blockquotes
    text = text.replace('\x02BQSTART\x02', '<blockquote>')
    text = text.replace('\x02BQEND\x02', '</blockquote>')

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


# ── HTML to Markdown conversion ──

def html_to_markdown(html_content: str, base_url: str = "") -> str:
    """Convert HTML content to Markdown format.

    Handles:
    - Links: <a href="url">text</a> → [text](url)
    - Images: <img src="url" alt="alt"> → ![alt](url)
    - Headings: <h1>-<h6> → # to ######
    - Lists: <ul>, <ol>, <li>
    - Tables: <table>, <tr>, <th>, <td>
    - Code: <code>, <pre>
    - Blockquotes: <blockquote>
    - Bold/Italic: <strong>, <b>, <em>, <i>
    - Line breaks and paragraphs

    Args:
        html_content: The HTML string to convert.
        base_url: Optional base URL for resolving relative links.

    Returns:
        Markdown formatted string.
    """
    from urllib.parse import urljoin

    if not html_content or not html_content.strip():
        return ""

    # Remove style/script blocks before parsing to avoid CSS leaking into output.
    html_content = strip_style_blocks(html_content)

    # Remove HTML comments (including Vue/Nuxt SSR markers like <!--[--> and <!--]-->)
    html_content = re.sub(r"<!--\[?-->", "", html_content)
    html_content = re.sub(r"<!--.*?-->", "", html_content, flags=re.DOTALL)

    # Simple HTML parser using regex (no external dependencies)
    # For complex HTML, consider using BeautifulSoup or html2text library

    result = []
    pos = 0
    length = len(html_content)

    # Track list state
    list_stack = []  # Stack of ('ul'|'ol', counter)
    in_pre = False
    in_code = False

    def resolve_url(url: str) -> str:
        """Resolve relative URL to absolute."""
        if not url:
            return url
        if url.startswith(("http://", "https://", "mailto:", "tel:", "#", "data:")):
            return url
        if base_url:
            return urljoin(base_url, url)
        return url

    def get_attr(tag: str, attr: str) -> str:
        """Extract attribute value from HTML tag."""
        import re
        pattern = rf'{attr}\s*=\s*["\']([^"\']*)["\']'
        match = re.search(pattern, tag, re.IGNORECASE)
        return match.group(1) if match else ""

    def process_text(text: str) -> str:
        """Process text content: decode entities, normalize whitespace."""
        import html
        # Decode HTML entities
        text = html.unescape(text)
        # Normalize whitespace (but preserve intentional line breaks in pre)
        if not in_pre:
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s*\n", "\n\n", text)
        return text

    def handle_tag(tag: str, is_closing: bool) -> str:
        """Handle HTML tags and return Markdown equivalent."""
        nonlocal in_pre, in_code

        tag_lower = tag.lower()

        # Skip processing inside pre
        if in_pre and tag_lower != "pre":
            return ""

        # Self-closing or opening tags
        if not is_closing:
            if tag_lower == "h1":
                return "\n\n# "
            elif tag_lower == "h2":
                return "\n\n## "
            elif tag_lower == "h3":
                return "\n\n### "
            elif tag_lower == "h4":
                return "\n\n#### "
            elif tag_lower == "h5":
                return "\n\n##### "
            elif tag_lower == "h6":
                return "\n\n###### "

            elif tag_lower == "p":
                return "\n\n"

            elif tag_lower == "br":
                return "\n"

            elif tag_lower == "hr":
                return "\n\n---\n\n"

            elif tag_lower in ("strong", "b"):
                return "**"
            elif tag_lower in ("em", "i"):
                return "*"

            elif tag_lower == "code":
                in_code = True
                return "`"
            elif tag_lower == "pre":
                in_pre = True
                return "\n\n```\n"

            elif tag_lower == "blockquote":
                return "\n\n> "

            elif tag_lower == "a":
                return "["  # Content follows, then ](url)

            elif tag_lower == "img":
                src = resolve_url(get_attr(tag, "src"))
                alt = get_attr(tag, "alt") or "image"
                return f"![{alt}]({src})"

            elif tag_lower == "ul":
                list_stack.append(("ul", 0))
                return "\n\n"
            elif tag_lower == "ol":
                list_stack.append(("ol", 0))
                return "\n\n"
            elif tag_lower == "li":
                if list_stack:
                    list_type, counter = list_stack[-1]
                    if list_type == "ol":
                        counter += 1
                        list_stack[-1] = ("ol", counter)
                        indent = "  " * (len(list_stack) - 1)
                        return f"\n{indent}{counter}. "
                    else:
                        indent = "  " * (len(list_stack) - 1)
                        return f"\n{indent}- "

            elif tag_lower == "table":
                return "\n\n"
            elif tag_lower == "thead":
                return ""
            elif tag_lower == "tbody":
                return ""
            elif tag_lower == "tr":
                return "\n|"
            elif tag_lower in ("th", "td"):
                return " "

            elif tag_lower == "div":
                return "\n"
            elif tag_lower == "span":
                return ""

            # Skip script, style, noscript content
            elif tag_lower in ("script", "style", "noscript", "head", "meta", "link"):
                return ""

        # Closing tags
        else:
            if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
                return "\n\n"

            elif tag_lower == "p":
                return "\n\n"

            elif tag_lower in ("strong", "b"):
                return "**"
            elif tag_lower in ("em", "i"):
                return "*"

            elif tag_lower == "code":
                in_code = False
                return "`"
            elif tag_lower == "pre":
                in_pre = False
                return "\n```\n\n"

            elif tag_lower == "blockquote":
                return "\n\n"

            elif tag_lower == "a":
                return "]()"  # Will be fixed with actual URL

            elif tag_lower == "ul":
                if list_stack:
                    list_stack.pop()
                return "\n\n"
            elif tag_lower == "ol":
                if list_stack:
                    list_stack.pop()
                return "\n\n"
            elif tag_lower == "li":
                return ""

            elif tag_lower == "tr":
                return ""
            elif tag_lower in ("th", "td"):
                return " |"
            elif tag_lower == "table":
                return "\n"

            elif tag_lower == "div":
                return "\n"
            elif tag_lower == "span":
                return ""

        return ""

    # Process HTML content
    output = []

    # Regex to find tags
    tag_pattern = re.compile(r"<(/?)(\w+)([^>]*)>", re.IGNORECASE | re.DOTALL)

    # Find all tags and their positions
    matches = list(tag_pattern.finditer(html_content))

    # Track links to insert URL after text
    pending_link_url = None
    last_pos = 0

    for match in matches:
        # Add text before this tag
        text_before = html_content[last_pos:match.start()]
        if text_before:
            output.append(process_text(text_before))

        last_pos = match.end()

        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()
        full_tag = match.group(0)
        attrs = match.group(3)

        # Skip script/style content
        if tag_name in ("script", "style", "noscript", "head"):
            # Find closing tag
            close_pattern = re.compile(rf"</{tag_name}\s*>", re.IGNORECASE)
            close_match = close_pattern.search(html_content, last_pos)
            if close_match:
                last_pos = close_match.end()
            continue

        # Handle link: store URL for after text
        if tag_name == "a" and not is_closing:
            pending_link_url = resolve_url(get_attr(full_tag, "href"))
            output.append("[")
        elif tag_name == "a" and is_closing and pending_link_url:
            output.append(f"]({pending_link_url})")
            pending_link_url = None

        # Handle image
        elif tag_name == "img" and not is_closing:
            src = resolve_url(get_attr(full_tag, "src"))
            alt = get_attr(full_tag, "alt") or "image"
            output.append(f"![{alt}]({src})")

        # Handle headings
        elif tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if not is_closing:
                level = int(tag_name[1])
                output.append(f"\n\n{'#' * level} ")
            else:
                output.append("\n\n")

        # Handle lists
        elif tag_name == "ul":
            if not is_closing:
                list_stack.append(("ul", 0))
                output.append("\n\n")
            else:
                if list_stack:
                    list_stack.pop()
                output.append("\n\n")
        elif tag_name == "ol":
            if not is_closing:
                list_stack.append(("ol", 0))
                output.append("\n\n")
            else:
                if list_stack:
                    list_stack.pop()
                output.append("\n\n")
        elif tag_name == "li":
            if not is_closing and list_stack:
                list_type, counter = list_stack[-1]
                indent = "  " * (len(list_stack) - 1)
                if list_type == "ol":
                    counter += 1
                    list_stack[-1] = ("ol", counter)
                    output.append(f"\n{indent}{counter}. ")
                else:
                    output.append(f"\n{indent}- ")

        # Handle formatting
        elif tag_name in ("strong", "b"):
            output.append("**")
        elif tag_name in ("em", "i"):
            output.append("*")
        elif tag_name == "code":
            # Skip backticks if already inside <pre>
            if not in_pre:
                if not is_closing:
                    in_code = True
                output.append("`")
                if is_closing:
                    in_code = False
        elif tag_name == "pre":
            if not is_closing:
                in_pre = True
                output.append("\n\n```\n")
            else:
                in_pre = False
                output.append("\n```\n\n")
        elif tag_name == "blockquote":
            if not is_closing:
                output.append("\n\n> ")
            else:
                output.append("\n\n")

        # Handle line breaks
        elif tag_name == "br":
            output.append("\n")
        elif tag_name == "hr":
            output.append("\n\n---\n\n")

        # Handle paragraphs
        elif tag_name == "p":
            output.append("\n\n")

        # Handle tables
        elif tag_name == "table":
            output.append("\n\n")
        elif tag_name == "tr":
            if not is_closing:
                output.append("\n|")
            else:
                output.append("")  # Row already has content, just ensure clean end
        elif tag_name in ("th", "td"):
            if not is_closing:
                output.append(" ")
            else:
                output.append(" |")

        # Handle div/span (minimal impact)
        elif tag_name == "div":
            if is_closing:
                output.append("\n")
        elif tag_name == "span":
            pass  # No markdown equivalent

    # Add remaining text
    if last_pos < len(html_content):
        output.append(process_text(html_content[last_pos:]))

    # Join and clean up
    result = "".join(output)

    # Clean up excessive newlines
    result = re.sub(r"\n{3,}", "\n\n", result)

    # Clean up spaces at start of lines
    result = re.sub(r"^ +$", "", result, flags=re.MULTILINE)

    # Clean up empty table cells markers
    result = re.sub(r"\| +\|", "| |", result)

    # Add header row separator for tables
    # First, merge table rows that are separated by blank lines
    def merge_table_rows(text: str) -> str:
        lines = text.split("\n")
        result_lines = []
        in_table = False

        for line in lines:
            is_table_row = line.strip().startswith("|") and line.strip().endswith("|")

            if is_table_row:
                if not in_table:
                    in_table = True
                result_lines.append(line)
            else:
                # Non-table line
                if in_table and line.strip() == "":
                    # Skip blank lines inside table
                    continue
                in_table = False
                result_lines.append(line)

        return "\n".join(result_lines)

    result = merge_table_rows(result)

    # Add separator after first table row
    def add_table_separator(text: str) -> str:
        lines = text.split("\n")
        result_lines = []
        separator_added = False

        for i, line in enumerate(lines):
            result_lines.append(line)

            is_table_row = line.strip().startswith("|") and line.strip().endswith("|")

            if is_table_row:
                if not separator_added:
                    # Check if next line is also a table row
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line.startswith("|") and not next_line.startswith("|-"):
                            cells = [c.strip() for c in line.split("|")[1:-1]]
                            if cells:
                                separator = "|" + "|".join(["---"] * len(cells)) + "|"
                                result_lines.append(separator)
                                separator_added = True
            else:
                # Reset for next table
                separator_added = False

        return "\n".join(result_lines)

    result = add_table_separator(result)

    # Fix pre+code: remove redundant backticks (shouldn't happen now, but keep as safety)
    result = re.sub(r"```\n`\n", "```\n", result)
    result = re.sub(r"\n`\n```\n", "\n```\n", result)

    return result.strip()
