"""Fetch tool — retrieve content from URLs (direct or Jina Reader)."""

import json
import logging
import os
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
import tls_client
import trafilatura

from .registry import BaseTool

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 5


class FetchTool(BaseTool):
    """Fetch URL content via direct request (default) or Jina Reader API."""

    def __init__(self):
        # Direct fetch: TLS fingerprint impersonation
        self._session = tls_client.Session(
            client_identifier="chrome_124",
            random_tls_extension_order=True,
        )
        self._session.headers.update(
            {
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "zh-CN,zh;q=0.9",
            }
        )
        self._session.timeout_seconds = 30

        # Jina Reader API
        self._jina_key = os.getenv("JINA_API_KEY", "").strip()

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
                        "Fetch content from a URL. "
                        "Use method='jina' for complex/JS-heavy pages (returns clean markdown). "
                        "Default method is faster for simple pages and API endpoints."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to fetch",
                            },
                            "method": {
                                "type": "string",
                                "enum": ["default", "jina"],
                                "default": "default",
                                "description": (
                                    "'default' = direct request + text extraction. "
                                    "'jina' = Jina Reader API, better for JS-heavy or complex pages."
                                ),
                            },
                            "max_length": {
                                "type": "integer",
                                "description": "Maximum characters to return (default 5000)",
                                "default": 5000,
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

        method = (arguments.get("method") or "default").strip().lower()
        max_length = arguments.get("max_length", 5000)
        try:
            max_length = int(max_length)
        except (TypeError, ValueError):
            max_length = 5000
        max_length = max(200, min(max_length, 20000))

        try:
            if method == "jina":
                text = self._fetch_jina(url)
            else:
                text = self._fetch_direct(url)
        except Exception as e:
            logger.exception("url_fetch (%s) failed for '%s'", method, url)
            return f"Fetch failed: {e}"

        if len(text) > max_length:
            text = text[:max_length] + "\n...(truncated)"
        return text

    # --- Direct fetch (tls_client + trafilatura) ---

    def _fetch_direct(self, url: str) -> str:
        current_url = url
        for _ in range(MAX_REDIRECTS + 1):
            resp = self._session.get(current_url, allow_redirects=False)
            if resp.status_code in {301, 302, 303, 307, 308}:
                location = (resp.headers.get("location") or "").strip()
                if not location:
                    raise RuntimeError("Redirect response without location")
                current_url = self._validate_external_url(urljoin(current_url, location))
                continue
            break
        else:
            raise RuntimeError("Too many redirects")

        if resp.status_code >= 400:
            if resp.status_code == 403:
                raise RuntimeError(
                    "HTTP 403 Forbidden (likely blocked by WAF/Cloudflare)"
                )
            raise RuntimeError(f"HTTP {resp.status_code}")

        content_type = resp.headers.get("content-type", "").lower()

        # Detect HTML when content-type is missing
        raw = resp.text.lstrip()[:15].lower()
        if not content_type and (
            raw.startswith("<!doctype html") or raw.startswith("<html")
        ):
            content_type = "text/html"

        if "application/json" in content_type:
            try:
                return json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except Exception:
                return resp.text
        elif "text/html" in content_type:
            extracted = trafilatura.extract(resp.text)
            return extracted if extracted else resp.text
        elif content_type.startswith("text/"):
            return resp.text
        else:
            raise RuntimeError(f"Unsupported content type: {content_type}")

    # --- Jina Reader API ---

    def _fetch_jina(self, url: str) -> str:
        if not self._jina_key:
            raise RuntimeError("JINA_API_KEY not configured")

        resp = requests.post(
            "https://r.jina.ai/",
            headers={
                "Authorization": f"Bearer {self._jina_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Return-Format": "markdown",
                "X-Timeout": "15",
            },
            json={"url": url},
            timeout=20,
        )
        resp.raise_for_status()

        data = resp.json().get("data", {})
        title = data.get("title", "")
        content = data.get("content", "")

        if not content:
            raise RuntimeError("Jina returned empty content")

        if title:
            return f"# {title}\n\n{content}"
        return content

    # --- URL safety helpers ---

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

        # Resolve and ensure all target IPs are public routable addresses.
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
            "\n\nYou have the url_fetch tool to retrieve content from URLs.\n"
            "Use it when you need to read a web page or API endpoint.\n"
            "Use method='jina' for complex/JS-heavy pages (returns clean markdown).\n"
            "Default method is faster for simple pages.\n"
        )
