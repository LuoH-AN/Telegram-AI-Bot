"""Message splitting helpers."""

from __future__ import annotations

from config import MAX_MESSAGE_LENGTH


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks that fit within platform limit."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current_chunk = ""
    for para in text.split("\n\n"):
        if len(current_chunk) + len(para) + 2 <= max_length:
            current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
            continue
        if current_chunk:
            chunks.append(current_chunk)
            current_chunk = ""
        if len(para) <= max_length:
            current_chunk = para
            continue
        for line in para.split("\n"):
            if len(current_chunk) + len(line) + 1 <= max_length:
                current_chunk = f"{current_chunk}\n{line}" if current_chunk else line
                continue
            if current_chunk:
                chunks.append(current_chunk)
            if len(line) > max_length:
                for index in range(0, len(line), max_length):
                    chunks.append(line[index : index + max_length])
                current_chunk = ""
            else:
                current_chunk = line
    if current_chunk:
        chunks.append(current_chunk)
    return chunks
