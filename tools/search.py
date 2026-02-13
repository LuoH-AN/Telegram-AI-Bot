"""Search tool — web search via Browserless scraper and Ollama search API."""

import base64
import logging
import os
import re
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

from .registry import BaseTool

logger = logging.getLogger(__name__)

# Browserless fetches Bing search HTML and parses results
_BL_BASE_URL = "https://production-sfo.browserless.io"
_BL_SEARCH_TEMPLATE = "https://www.bing.com/search?q={query}"

# Ollama native search API
_OLLAMA_BASE_URL = "https://ollama.com"

_TIMEOUT = 30
_DEFAULT_MAX = 5


class SearchTool(BaseTool):
    """Web search via Browserless (Bing scraping) and Ollama (native API)."""

    def __init__(self):
        self._bl_token = os.getenv("BROWSERLESS_API_TOKEN", "").strip()
        self._ollama_key = os.getenv("OLLAMA_API_KEY", "").strip()

    @property
    def name(self) -> str:
        return "search"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": (
                        "Search the web for current information. "
                        "Returns titles, URLs and snippets."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            },
                            "provider": {
                                "type": "string",
                                "enum": ["browserless", "ollama", "all"],
                                "default": "all",
                                "description": "Provider to use. 'all' uses both.",
                            },
                            "max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                                "default": 5,
                                "description": "Max results to return (1-10)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name != "web_search":
            return f"Unknown tool: {tool_name}"

        query = (arguments.get("query") or "").strip()
        if not query:
            return "No query provided."

        # Parse provider — accept both "provider" (string) and "providers" (list)
        raw = arguments.get("provider") or arguments.get("providers") or "all"
        if isinstance(raw, list):
            raw = ",".join(str(v) for v in raw)
        provider = raw.strip().lower()

        if provider in ("all", "both", "auto"):
            targets = ["browserless", "ollama"]
        elif provider in ("browserless", "ollama"):
            targets = [provider]
        else:
            return f"Unknown provider: {provider}. Use 'browserless', 'ollama', or 'all'."

        max_results = _DEFAULT_MAX
        if arguments.get("max_results") is not None:
            try:
                max_results = max(1, min(10, int(arguments["max_results"])))
            except (TypeError, ValueError):
                pass

        # Call each provider, collect results and errors
        all_results, errors = [], []
        dispatch = {
            "browserless": self._browserless_search,
            "ollama": self._ollama_search,
        }
        for p in targets:
            try:
                all_results.extend(dispatch[p](query, max_results))
            except Exception as e:
                logger.exception("%s search failed for '%s'", p, query)
                errors.append(f"{p}: {e}")

        # Deduplicate by URL
        seen, merged = set(), []
        for r in all_results:
            key = r["url"].lower()
            if key not in seen:
                seen.add(key)
                merged.append(r)
                if len(merged) >= max_results:
                    break

        if not merged:
            msg = "No results found."
            if errors:
                msg += "\n" + "\n".join(f"- {e}" for e in errors)
            return msg

        lines = [
            f"{i}. [{r['provider']}] {r['title']}\n"
            f"   {r['url']}\n"
            f"   {r['snippet']}"
            for i, r in enumerate(merged, 1)
        ]
        if errors:
            lines.append("Warnings: " + "; ".join(errors))
        return "\n\n".join(lines)

    # --- Browserless: fetch Bing HTML and parse results ---

    def _browserless_search(self, query: str, max_results: int) -> list[dict]:
        if not self._bl_token:
            raise RuntimeError("BROWSERLESS_API_TOKEN not configured")

        search_url = _BL_SEARCH_TEMPLATE.replace("{query}", quote_plus(query))
        resp = requests.post(
            f"{_BL_BASE_URL}/content",
            params={"token": self._bl_token},
            json={
                "url": search_url,
                "gotoOptions": {
                    "timeout": 25000,
                    "waitUntil": "domcontentloaded",
                },
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        html = resp.text

        # Split by <li class="b_algo" ...> blocks
        blocks = re.split(r'<li\s+class="b_algo"[^>]*>', html)[1:]

        results = []
        for block in blocks:
            # Isolate this block (cut at next <li)
            end = block.find("<li ")
            if end > 0:
                block = block[:end]

            # Extract first <a href="...">title</a>
            m = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not m:
                continue

            raw_href = unescape(m.group(1))
            title_html = m.group(2)
            title = self._strip_tags(title_html)
            if not title:
                continue

            # Resolve Bing redirect URL
            href = self._resolve_bing_href(raw_href)
            if not href:
                continue

            # Extract snippet from first <p> tag
            snippet = ""
            sm = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
            if sm:
                snippet = self._strip_tags(sm.group(1))

            results.append({
                "provider": "browserless",
                "title": title,
                "url": href,
                "snippet": snippet,
            })
            if len(results) >= max_results:
                break

        return results

    # --- Ollama: native search API ---

    def _ollama_search(self, query: str, max_results: int) -> list[dict]:
        if not self._ollama_key:
            raise RuntimeError("OLLAMA_API_KEY not configured")

        resp = requests.post(
            f"{_OLLAMA_BASE_URL}/api/web_search",
            headers={
                "Authorization": f"Bearer {self._ollama_key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "max_results": max_results},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        results = []
        for item in resp.json().get("results", []):
            if not isinstance(item, dict):
                continue
            url = (item.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            results.append(
                {
                    "provider": "ollama",
                    "title": self._clean(item.get("title")) or url,
                    "url": url,
                    "snippet": self._clean(item.get("content")),
                }
            )
            if len(results) >= max_results:
                break
        return results

    # --- Helpers ---

    @staticmethod
    def _clean(text) -> str:
        return " ".join(str(text or "").split())

    @staticmethod
    def _strip_tags(html_str: str) -> str:
        """Remove HTML tags, decode entities, and collapse whitespace."""
        text = re.sub(r"<[^>]+>", "", html_str)
        text = unescape(text)
        return " ".join(text.split())

    @staticmethod
    def _resolve_bing_href(raw_href: str) -> str:
        """Unwrap Bing's /ck/a redirect to get the real URL."""
        qs = parse_qs(urlparse(raw_href).query)
        # Bing encodes the target URL as base64 in the 'u' parameter
        u_val = qs.get("u", [""])[0]
        if u_val.startswith("a1"):
            try:
                # Bing base64: strip 'a1' prefix, add padding, decode
                b64 = u_val[2:]
                b64 += "=" * (-len(b64) % 4)
                return base64.urlsafe_b64decode(b64).decode("utf-8", errors="replace")
            except Exception:
                pass

        # Fallback: check for plain URL params
        for key in ("url", "target"):
            val = qs.get(key, [""])[0]
            if val.startswith(("http://", "https://")):
                return unquote(val)

        # If it's already a direct URL (not a redirect)
        if raw_href.startswith(("http://", "https://")) and "/ck/a" not in raw_href:
            return raw_href

        return ""

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the web_search tool to find information from the internet.\n"
            "Use it when the user asks about current events or needs up-to-date information.\n"
            "Set provider to 'browserless', 'ollama', or 'all' (default: both).\n"
            "Search results only contain brief snippets. If you need the full content of a page, "
            "use the url_fetch tool with the URL from the search results.\n"
        )
