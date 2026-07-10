"""Resolve source descriptors (url / path / generate) into (bytes, filename)."""

from __future__ import annotations

import ipaddress
import logging
import mimetypes
import socket
import urllib.parse
import urllib.request
from pathlib import Path

from infrastructure.config import TOOL_FILE_ROOTS

logger = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024 * 1024
_DEFAULT_EXT = {"image": ".png", "voice": ".mp3", "video": ".mp4", "document": ".bin"}

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "ip-ranges.amazonaws.com"}
_SECRET_SUFFIXES = (".pem", ".key", ".ppk", ".p12", ".keystore", ".kdbx")
_SECRET_NAMES = {
    ".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "shadow",
    ".npmrc", ".pypirc", ".htpasswd", "credentials", ".netrc", ".git-credentials",
}
_SECRET_NAME_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".env")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ext_from_kind(kind: str) -> str:
    return _DEFAULT_EXT.get(kind, ".bin")


def _name_from_url(url: str, kind: str) -> str:
    base = Path(urllib.parse.urlparse(url).path).name or "download"
    if not Path(base).suffix:
        base += _ext_from_kind(kind)
    return base


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return True
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_reserved or addr.is_multicast or addr.is_unspecified
    )


def _assert_safe_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(f"unsupported scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("url has no host")
    if host in _BLOCKED_HOSTS or host.endswith(".internal") or host.endswith(".local"):
        raise ValueError(f"blocked host: {host}")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve host {host!r}: {exc}") from exc
    for info in infos:
        if _is_private_ip(info[4][0]):
            raise ValueError(f"blocked private/internal address: {host}")


def fetch_url(url: str, *, kind: str) -> tuple[bytes, str]:
    _assert_safe_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Telegram-AI-Bot/send_file"})
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    with opener.open(req, timeout=30) as resp:
        final_url = resp.geturl()
        _assert_safe_url(final_url)
        cl = resp.headers.get("Content-Length")
        if cl and int(cl) > MAX_BYTES:
            raise ValueError(f"file too large: {cl} bytes (limit {MAX_BYTES})")
        data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError(f"file too large: > {MAX_BYTES} bytes")
        ctype = resp.headers.get("Content-Type", "")
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


def generate_image(user_id: int, prompt: str, *, size: str = "1024x1024") -> tuple[bytes, str]:
    """Generate an image via the user's OpenAI-compatible endpoint."""
    from domain.services import get_user_settings
    from openai import OpenAI

    settings = get_user_settings(user_id)
    api_key = settings.get("api_key")
    if not api_key:
        raise RuntimeError("no api_key configured for image generation")
    client = OpenAI(api_key=api_key, base_url=settings.get("base_url"))
    model = settings.get("image_model") or "dall-e-3"
    resp = client.images.generate(model=model, prompt=prompt, size=size, n=1)
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        import base64

        data = base64.b64decode(item.b64_json)
    elif getattr(item, "url", None):
        data, _ = fetch_url(item.url, kind="image")
    else:
        raise RuntimeError("image generation returned no usable payload")
    return data, "generated.png"
