"""Base HTTP client mixin for WeChat protocol."""

from __future__ import annotations

import json
import secrets
from urllib.parse import urljoin

from .constants import ILINK_APP_CLIENT_VERSION, ILINK_APP_ID


class ClientBaseMixin:
    def _random_wechat_uin(self) -> str:
        value = secrets.randbelow(2**32)
        return self._b64encode(str(value).encode("utf-8"))

    @staticmethod
    def _b64encode(payload: bytes) -> str:
        import base64
        return base64.b64encode(payload).decode("utf-8")

    def _common_headers(self) -> dict[str, str]:
        return {"iLink-App-Id": ILINK_APP_ID, "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION}

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        body: dict | None = None,
        token: str | None = None,
        timeout: float = 15,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
    ):
        url = endpoint if endpoint.startswith(("http://", "https://")) else urljoin((base_url or self.base_url).rstrip("/") + "/", endpoint.lstrip("/"))
        headers = self._common_headers()
        if method.upper() == "POST":
            headers["AuthorizationType"] = "ilink_bot_token"
            headers["X-WECHAT-UIN"] = self._random_wechat_uin()
            if token:
                headers["Authorization"] = f"Bearer {token.strip()}"
        if extra_headers:
            headers.update(extra_headers)
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type or "application/octet-stream"
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            data = None
        response = self._session.request(method=method.upper(), url=url, headers=headers, data=data, timeout=timeout)
        response.raise_for_status()
        return response
