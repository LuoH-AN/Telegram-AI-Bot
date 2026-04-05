"""HTML parsing core for markdown conversion."""

from __future__ import annotations

import re

from .html_utils import get_attr, process_text, resolve_url


def parse_html_to_markdown(html_content: str, *, base_url: str = "") -> str:
    output: list[str] = []
    list_stack: list[tuple[str, int]] = []
    in_pre = False
    tag_pattern = re.compile(r"<(/?)(\w+)([^>]*)>", re.IGNORECASE | re.DOTALL)
    matches = list(tag_pattern.finditer(html_content))
    pending_link_url = None
    last_pos = 0

    for match in matches:
        text_before = html_content[last_pos:match.start()]
        if text_before:
            output.append(process_text(text_before, in_pre=in_pre))
        last_pos = match.end()
        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()
        full_tag = match.group(0)
        if tag_name in ("script", "style", "noscript", "head"):
            close_pattern = re.compile(rf"</{tag_name}\s*>", re.IGNORECASE)
            close_match = close_pattern.search(html_content, last_pos)
            if close_match:
                last_pos = close_match.end()
            continue
        if tag_name == "a":
            if not is_closing:
                pending_link_url = resolve_url(get_attr(full_tag, "href"), base_url)
                output.append("[")
            elif pending_link_url:
                output.append(f"]({pending_link_url})")
                pending_link_url = None
            continue
        if tag_name == "img" and not is_closing:
            src = resolve_url(get_attr(full_tag, "src"), base_url)
            alt = get_attr(full_tag, "alt") or "image"
            output.append(f"![{alt}]({src})")
            continue
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            output.append(f"\n\n{'#' * int(tag_name[1])} " if not is_closing else "\n\n")
            continue
        if tag_name in ("ul", "ol"):
            if not is_closing:
                list_stack.append((tag_name, 0))
            elif list_stack:
                list_stack.pop()
            output.append("\n\n")
            continue
        if tag_name == "li" and not is_closing and list_stack:
            list_type, counter = list_stack[-1]
            indent = "  " * (len(list_stack) - 1)
            if list_type == "ol":
                counter += 1
                list_stack[-1] = ("ol", counter)
                output.append(f"\n{indent}{counter}. ")
            else:
                output.append(f"\n{indent}- ")
            continue
        if tag_name in ("strong", "b"):
            output.append("**")
        elif tag_name in ("em", "i"):
            output.append("*")
        elif tag_name == "code" and not in_pre:
            output.append("`")
        elif tag_name == "pre":
            if not is_closing:
                in_pre = True
                output.append("\n\n```\n")
            else:
                in_pre = False
                output.append("\n```\n\n")
        elif tag_name == "blockquote":
            output.append("\n\n> " if not is_closing else "\n\n")
        elif tag_name == "br":
            output.append("\n")
        elif tag_name == "hr":
            output.append("\n\n---\n\n")
        elif tag_name == "p":
            output.append("\n\n")
        elif tag_name == "table":
            output.append("\n\n")
        elif tag_name == "tr":
            output.append("\n|" if not is_closing else "")
        elif tag_name in ("th", "td"):
            output.append(" " if not is_closing else " |")
        elif tag_name == "div" and is_closing:
            output.append("\n")

    if last_pos < len(html_content):
        output.append(process_text(html_content[last_pos:], in_pre=in_pre))
    return "".join(output)
