"""Resolve source descriptors (url / path / generate) into (bytes, filename)."""

from __future__ import annotations

import logging
import mimetypes
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024 * 1024
_DEFAULT_EXT = {"image": ".png", "voice": ".mp3", "video": ".mp4", "document": ".bin"}


def _ext_from_kind(kind: str) -> str:
    return _DEFAULT_EXT.get(kind, ".bin")


def _name_from_url(url: str, kind: str) -> str:
    parsed = urllib.parse.urlparse(url)
    base = Path(parsed.path).name or "download"
    if not Path(base).suffix:
        base += _ext_from_kind(kind)
    return base


def fetch_url(url: str, *, kind: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Telegram-AI-Bot/send_file"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        cl = resp.headers.get("Content-Length")
        if cl and int(cl) > MAX_BYTES:
            raise ValueError(f"file too large: {cl} bytes (limit {MAX_BYTES})")
        data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError(f"file too large: > {MAX_BYTES} bytes")
        ctype = resp.headers.get("Content-Type", "")
    name = _name_from_url(url, kind)
    if "." not in name:
        ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or _ext_from_kind(kind)
        name += ext
    return data, name


def read_path(path: str, *, kind: str) -> tuple[bytes, str]:
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    size = p.stat().st_size
    if size > MAX_BYTES:
        raise ValueError(f"file too large: {size} bytes (limit {MAX_BYTES})")
    return p.read_bytes(), p.name


def generate_image(user_id: int, prompt: str, *, size: str = "1024x1024") -> tuple[bytes, str]:
    """Generate an image via the user's OpenAI-compatible endpoint."""
    from services import get_user_settings

    settings = get_user_settings(user_id)
    api_key = settings.get("api_key")
    base_url = settings.get("base_url")
    if not api_key:
        raise RuntimeError("no api_key configured for image generation")
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
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
