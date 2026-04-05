"""Media download mixin."""

from __future__ import annotations

import uuid
from pathlib import Path

import requests

from .crypto import aes_ecb_decrypt, parse_aes_key_base64
from .mime_types import get_mime_from_filename


class ClientMediaDownloadMixin:
    def download_media_to_path(self, item: dict, dest_dir: str | Path) -> dict:
        dest_root = Path(dest_dir)
        dest_root.mkdir(parents=True, exist_ok=True)
        item_type = int(item.get("type") or 0)
        if item_type == 2:
            return self._download_image_item(item, dest_root)
        if item_type == 4:
            return self._download_file_item(item, dest_root)
        if item_type == 5:
            return self._download_video_item(item, dest_root)
        if item_type == 3:
            return self._download_voice_item(item, dest_root)
        raise ValueError(f"unsupported wechat media item type: {item_type}")

    def _download_image_item(self, item: dict, dest_root: Path) -> dict:
        image_item = item.get("image_item") or {}
        media = image_item.get("media") or {}
        content = self._download_media_bytes(media)
        if image_item.get("aeskey"):
            content = aes_ecb_decrypt(content, bytes.fromhex(str(image_item["aeskey"])))
        elif media.get("aes_key"):
            content = aes_ecb_decrypt(content, parse_aes_key_base64(str(media["aes_key"])))
        filename = f"{uuid.uuid4().hex}.jpg"
        path = dest_root / filename
        path.write_bytes(content)
        return {"path": str(path), "filename": filename, "media_type": "image/jpeg"}

    def _download_file_item(self, item: dict, dest_root: Path) -> dict:
        file_item = item.get("file_item") or {}
        media = file_item.get("media") or {}
        content = self._download_media_bytes(media)
        if media.get("aes_key"):
            content = aes_ecb_decrypt(content, parse_aes_key_base64(str(media["aes_key"])))
        filename = str(file_item.get("file_name") or f"{uuid.uuid4().hex}.bin")
        path = dest_root / filename
        path.write_bytes(content)
        return {"path": str(path), "filename": filename, "media_type": get_mime_from_filename(filename)}

    def _download_video_item(self, item: dict, dest_root: Path) -> dict:
        media = (item.get("video_item") or {}).get("media") or {}
        content = self._download_media_bytes(media)
        if media.get("aes_key"):
            content = aes_ecb_decrypt(content, parse_aes_key_base64(str(media["aes_key"])))
        filename = f"{uuid.uuid4().hex}.mp4"
        path = dest_root / filename
        path.write_bytes(content)
        return {"path": str(path), "filename": filename, "media_type": "video/mp4"}

    def _download_voice_item(self, item: dict, dest_root: Path) -> dict:
        media = (item.get("voice_item") or {}).get("media") or {}
        content = self._download_media_bytes(media)
        if media.get("aes_key"):
            content = aes_ecb_decrypt(content, parse_aes_key_base64(str(media["aes_key"])))
        filename = f"{uuid.uuid4().hex}.silk"
        path = dest_root / filename
        path.write_bytes(content)
        return {"path": str(path), "filename": filename, "media_type": "audio/silk"}

    def _download_media_bytes(self, media: dict) -> bytes:
        full_url = (media.get("full_url") or "").strip()
        encrypted = (media.get("encrypt_query_param") or "").strip()
        if not full_url and not encrypted:
            raise ValueError("wechat media item missing media url")
        url = full_url or f"{self.cdn_base_url}/download?encrypted_query_param={requests.utils.quote(encrypted, safe='')}"
        return self._request("GET", url, timeout=30).content
