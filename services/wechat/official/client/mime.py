"""MIME and extension helpers."""

from __future__ import annotations

import mimetypes
from pathlib import Path

EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".silk": "audio/silk",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    "image/bmp": ".bmp", "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm", "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi", "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/silk": ".silk",
    "application/pdf": ".pdf", "application/zip": ".zip", "application/x-tar": ".tar", "application/gzip": ".gz",
    "text/plain": ".txt", "text/csv": ".csv",
}


def get_mime_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in EXTENSION_TO_MIME:
        return EXTENSION_TO_MIME[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def get_extension_from_mime(mime_type: str) -> str:
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    return MIME_TO_EXTENSION.get(mime, ".bin")
