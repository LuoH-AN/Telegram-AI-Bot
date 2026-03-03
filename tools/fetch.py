"""Fetch tool — retrieve content from URLs via Jina Reader."""

import logging
import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests

from .registry import BaseTool, emit_tool_progress

logger = logging.getLogger(__name__)

_JINA_READER_BASE_URL = "https://r.jina.ai/"
_TIMEOUT = 30


class FetchTool(BaseTool):
    """Fetch URL content via Jina Reader."""

    def __init__(self):
        self._jina_api_key = os.getenv("JINA_API_KEY", "").strip()

    @property
    def name(self) -> str:
        return "fetch"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "url_fetch",
                    "description": (
                        "Fetch content from a URL via Jina Reader. "
                        "Returns cleaned text/Markdown content."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to fetch",
                            },
                            "max_length": {
                                "type": "integer",
                                "description": "Maximum characters to return (default 10000)",
                                "default": 10000,
                            },
                        },
                        "required": ["url"],
                    },
                },
            }
        ]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name != "url_fetch":
            return f"Unknown tool: {tool_name}"

        raw_url = (arguments.get("url") or "").strip()
        if not raw_url:
            return "No URL provided."
        try:
            url = self._validate_external_url(raw_url)
        except ValueError as e:
            return f"Fetch rejected: {e}"

        max_length = arguments.get("max_length", 10000)
        try:
            max_length = int(max_length)
        except (TypeError, ValueError):
            max_length = 10000
        max_length = max(200, min(max_length, 50000))

        try:
            emit_tool_progress(
                f"Fetching URL via Jina Reader: {url}",
                tool_name="url_fetch",
            )
            text = self._fetch_via_jina(url)
        except Exception as e:
            logger.exception("url_fetch failed for '%s'", url)
            return f"Fetch failed: {e}"

        if len(text) > max_length:
            text = text[:max_length] + "\n...(truncated)"
        return text

    def _fetch_via_jina(self, url: str) -> str:
        headers = {}
        if self._jina_api_key:
            headers["Authorization"] = f"Bearer {self._jina_api_key}"

        # Jina Reader expects the target URL appended after the base endpoint.
        reader_url = f"{_JINA_READER_BASE_URL}{url}"
        resp = requests.get(reader_url, headers=headers, timeout=_TIMEOUT)

        if resp.status_code >= 400:
            raise RuntimeError(f"Jina Reader HTTP {resp.status_code}")

        text = resp.text.strip()
        if not text:
            raise RuntimeError("Empty response from Jina Reader")
        return text

    @staticmethod
    def _validate_external_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise ValueError("Only http:// or https:// URLs are allowed")

        host = (parsed.hostname or "").strip().lower().rstrip(".")
        if not host:
            raise ValueError("Invalid URL host")

        if host == "localhost" or host.endswith(".local"):
            raise ValueError("Local hosts are not allowed")

        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise ValueError("Host resolution failed")

        addresses = {info[4][0] for info in infos}
        if not addresses:
            raise ValueError("Host resolution returned no addresses")

        for addr in addresses:
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                raise ValueError("Resolved address is invalid")
            if not ip.is_global:
                raise ValueError("Private or local network addresses are not allowed")

        return url

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the url_fetch tool to retrieve content from URLs via Jina Reader.\n"
            "Search results only provide snippets; use url_fetch to read full page content.\n"
        )
