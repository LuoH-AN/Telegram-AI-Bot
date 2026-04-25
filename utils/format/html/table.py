"""Table and final cleanup helpers for markdown output."""

from __future__ import annotations

import re


def merge_table_rows(text: str) -> str:
    lines = text.split("\n")
    result: list[str] = []
    in_table = False
    for line in lines:
        is_table_row = line.strip().startswith("|") and line.strip().endswith("|")
        if is_table_row:
            in_table = True
            result.append(line)
            continue
        if in_table and line.strip() == "":
            continue
        in_table = False
        result.append(line)
    return "\n".join(result)


def add_table_separator(text: str) -> str:
    lines = text.split("\n")
    result: list[str] = []
    separator_added = False
    for index, line in enumerate(lines):
        result.append(line)
        is_row = line.strip().startswith("|") and line.strip().endswith("|")
        if not is_row:
            separator_added = False
            continue
        if separator_added or index + 1 >= len(lines):
            continue
        next_line = lines[index + 1].strip()
        if next_line.startswith("|") and not next_line.startswith("|-"):
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if cells:
                result.append("|" + "|".join(["---"] * len(cells)) + "|")
                separator_added = True
    return "\n".join(result)


def finalize_markdown(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^ +$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\| +\|", "| |", text)
    text = merge_table_rows(text)
    text = add_table_separator(text)
    text = re.sub(r"```\n`\n", "```\n", text)
    text = re.sub(r"\n`\n```\n", "\n```\n", text)
    return text.strip()
