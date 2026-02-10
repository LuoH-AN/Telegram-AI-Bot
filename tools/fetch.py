"""Fetch tool — retrieve content from URLs (with TLS fingerprint impersonation)."""

import json
import logging

import tls_client
import trafilatura

from .registry import BaseTool

logger = logging.getLogger(__name__)

URL_FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "url_fetch",
        "description": "Fetch content from a URL. Extracts main text from HTML pages and returns formatted JSON for API responses.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
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

class FetchTool(BaseTool):
    """Tool for fetching content from URLs."""

    @property
    def name(self) -> str:
        return "fetch"

    def __init__(self):
        # 升级配置：
        # 1. client_identifier="chrome_124": 模拟 Chrome 124 的 TLS 握手特征
        # 2. random_tls_extension_order=True: 随机化 TLS 扩展顺序
        self._session = tls_client.Session(
            client_identifier="chrome_124",
            random_tls_extension_order=True
        )

        # 关键头部配置：必须与 TLS 指纹（Chrome 124 on Windows）严格对应
        # Cloudflare 会检查 TLS 指纹和 HTTP 头部的一致性
        headers = {
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9",
        }

        self._session.headers.update(headers)
        # 设置超时
        self._session.timeout_seconds = 30

    def definitions(self) -> list[dict]:
        return [URL_FETCH_TOOL]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        url = arguments.get("url", "").strip()
        if not url:
            return "No URL provided."

        if tool_name != "url_fetch":
            return f"Unknown tool: {tool_name}"

        max_length = arguments.get("max_length", 5000)

        try:
            # 使用加强后的 session 发起请求
            resp = self._session.get(url)
            if resp.status_code >= 400:
                if resp.status_code == 403:
                    return "HTTP 403 Forbidden (Likely blocked by WAF/Cloudflare)"
                return f"HTTP error {resp.status_code}"
        except Exception as e:
            logger.exception("url_fetch failed for '%s'", url)
            return f"Fetch failed: {e}"

        content_type = resp.headers.get("content-type", "").lower()

        # Fallback: detect HTML from content when content-type is missing
        if (not content_type and resp.text.lstrip()[:15].lower().startswith("<!doctype html")) or \
           (not content_type and resp.text.lstrip()[:5].lower().startswith("<html")):
            content_type = "text/html"

        if "application/json" in content_type:
            try:
                text = json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except Exception:
                text = resp.text
        elif "text/html" in content_type:
            # Trafilatura 用于提取主要文本内容
            extracted = trafilatura.extract(resp.text)
            text = extracted if extracted else resp.text
        elif content_type.startswith("text/"):
            text = resp.text
        else:
            return f"Unsupported content type: {content_type}"

        if len(text) > max_length:
            text = text[:max_length] + "\n...(truncated)"

        return text

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the url_fetch tool to retrieve content from URLs.\n"
            "Use it when you need to read the contents of a specific web page or API endpoint.\n"
        )
