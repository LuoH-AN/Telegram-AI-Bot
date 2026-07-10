"""Resolve existing URL or local-path sources into (bytes, filename)."""

from __future__ import annotations

import mimetypes
import urllib.parse
from pathlib import Path

from infrastructure.config import TOOL_FILE_ROOTS
from infrastructure.tools.http_client import SafeRedirectHandler as _SafeRedirectHandler
from infrastructure.tools.http_client import assert_safe_url as _assert_safe_url
from infrastructure.tools.http_client import download_url

MAX_BYTES = 50 * 1024 * 1024
_DEFAULT_EXT = {"image": ".png", "voice": ".mp3", "video": ".mp4", "document": ".bin"}

_SECRET_SUFFIXES = (".pem", ".key", ".ppk", ".p12", ".keystore", ".kdbx")
_SECRET_NAMES = {
    ".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "shadow",
    ".npmrc", ".pypirc", ".htpasswd", "credentials", ".netrc", ".git-credentials",
}
_SECRET_NAME_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".env")


def _ext_from_kind(kind: str) -> str:
    return _DEFAULT_EXT.get(kind, ".bin")


def _name_from_url(url: str, kind: str) -> str:
    base = Path(urllib.parse.urlparse(url).path).name or "download"
    if not Path(base).suffix:
        base += _ext_from_kind(kind)
    return base


def fetch_url(url: str, *, kind: str) -> tuple[bytes, str]:
    resource = download_url(
        url,
        max_bytes=MAX_BYTES,
        timeout=30,
        user_agent="Telegram-AI-Bot/send_file",
    )
    final_url = resource.final_url
    data = resource.data
    ctype = resource.content_type
    name = _name_from_url(final_url, kind)
    if "." not in name:
        ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or _ext_from_kind(kind)
        name += ext
    return data, name


def _assert_safe_path(p: Path) -> Path:
    resolved = p.resolve()
    roots = [r.resolve() for r in TOOL_FILE_ROOTS if r.exists()]
    if not roots or not any(resolved == root or root in resolved.parents for root in roots):
        raise ValueError(f"path outside allowed roots: {p}")
    name = resolved.name.lower()
    if name in _SECRET_NAMES or resolved.suffix.lower() in _SECRET_SUFFIXES:
        raise ValueError(f"access to sensitive file denied: {p}")
    if any(name.startswith(prefix) for prefix in _SECRET_NAME_PREFIXES):
        raise ValueError(f"access to sensitive file denied: {p}")
    if ".git" in resolved.parts:
        raise ValueError("access to .git denied")
    return resolved


def read_path(path: str, *, kind: str) -> tuple[bytes, str]:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    resolved = _assert_safe_path(p)
    if not resolved.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    if resolved.stat().st_size > MAX_BYTES:
        raise ValueError(f"file too large: {resolved.stat().st_size} bytes (limit {MAX_BYTES})")
    return resolved.read_bytes(), resolved.name
