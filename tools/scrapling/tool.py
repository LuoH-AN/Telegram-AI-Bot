"""Scrapling skill tool integration.

Based on upstream repository:
https://github.com/Cedriccmh/claude-code-skill-scrapling
"""

from __future__ import annotations

import json
import logging

from ..core.base import BaseTool
from .constants import DEFAULT_TIMEOUT_SECONDS
from .fetch import fetch_url, normalize_site_key, parse_cookies_argument, parse_html
from .install import install_scrapling
from .runtime import detect_capabilities
from .vault import delete_site, get_site, list_sites, set_site

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {
    "status",
    "install",
    "fetch",
    "parse_html",
    "cookie_list",
    "cookie_get",
    "cookie_set",
    "cookie_delete",
}


class ScraplingTool(BaseTool):
    @property
    def name(self) -> str:
        return "scrapling"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "scrapling",
                    "description": (
                        "Web scraping skill powered by scrapling. "
                        "Supports installation checks, URL fetch/extract, HTML parsing, and cookie-vault management."
                    ),
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(_VALID_ACTIONS),
                    "description": "Action to run",
                },
                "url": {
                    "type": "string",
                    "description": "Target URL for fetch action",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "basic", "stealth", "dynamic"],
                    "description": "Fetcher mode for fetch action (default: auto)",
                },
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector for extraction",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)",
                },
                "html": {
                    "type": "string",
                    "description": "HTML content for parse_html action",
                },
                "base_url": {
                    "type": "string",
                    "description": "Base URL for parse_html action",
                },
                "query": {
                    "type": "string",
                    "description": "Reserved for future compatibility",
                },
                "cookies": {
                    "type": "string",
                    "description": "Cookies JSON (dict or list) for fetch/cookie_set actions",
                },
                "site": {
                    "type": "string",
                    "description": "Site key/domain for cookie vault actions",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes for cookie_set action",
                },
                "with_browser": {
                    "type": "boolean",
                    "description": "For install action, also install browser dependencies",
                },
                "upgrade": {
                    "type": "boolean",
                    "description": "For install action, perform upgrade",
                },
            },
            "required": ["action"],
        }

    def get_instruction(self) -> str:
        return (
            "\nScrapling skill policy:\n"
            "- For website scraping/extraction, prefer `scrapling` tool over generic terminal commands.\n"
            "- Use action='fetch' for URL scraping and action='parse_html' when HTML is already available.\n"
            "- Use cookie vault actions (cookie_set/get/list/delete) to reuse auth cookies safely.\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        del user_id, tool_name
        action = str(arguments.get("action") or "").strip().lower()
        if action not in _VALID_ACTIONS:
            return f"Error: invalid action '{action}'. Allowed: {', '.join(sorted(_VALID_ACTIONS))}"

        try:
            if action == "status":
                return _json(
                    {
                        "ok": True,
                        "capabilities": detect_capabilities(),
                        "cookie_sites": list_sites(),
                    }
                )
            if action == "install":
                with_browser = bool(arguments.get("with_browser"))
                upgrade = bool(arguments.get("upgrade"))
                return _json(
                    install_scrapling(
                        with_fetchers=True,
                        with_browser=with_browser,
                        upgrade=upgrade,
                    )
                )
            if action == "fetch":
                timeout = _as_timeout(arguments.get("timeout"))
                cookies = parse_cookies_argument(arguments.get("cookies"))
                site = normalize_site_key(arguments.get("site"))
                if cookies is None and site:
                    site_entry = get_site(site)
                    if isinstance(site_entry, dict):
                        cookies = site_entry.get("cookies")
                payload = fetch_url(
                    url=str(arguments.get("url") or ""),
                    mode=str(arguments.get("mode") or "auto"),
                    selector=str(arguments.get("selector") or ""),
                    timeout_seconds=timeout,
                    cookies=cookies,
                )
                if site:
                    payload["site"] = site
                return _json(payload)
            if action == "parse_html":
                timeout = _as_timeout(arguments.get("timeout"))
                del timeout  # reserved for parity with fetch action
                return _json(
                    parse_html(
                        html=str(arguments.get("html") or ""),
                        selector=str(arguments.get("selector") or ""),
                        base_url=str(arguments.get("base_url") or arguments.get("url") or ""),
                    )
                )
            if action == "cookie_list":
                return _json({"ok": True, "sites": list_sites()})
            if action == "cookie_get":
                site = normalize_site_key(arguments.get("site"))
                if not site:
                    return "Error: cookie_get requires site"
                return _json({"ok": True, "site": site, "entry": get_site(site)})
            if action == "cookie_set":
                site = normalize_site_key(arguments.get("site"))
                if not site:
                    return "Error: cookie_set requires site"
                cookies = parse_cookies_argument(arguments.get("cookies"))
                if cookies is None:
                    return "Error: cookie_set requires cookies (JSON dict or list)"
                entry = set_site(site, cookies, notes=str(arguments.get("notes") or ""))
                return _json({"ok": True, "site": site, "entry": entry})
            if action == "cookie_delete":
                site = normalize_site_key(arguments.get("site"))
                if not site:
                    return "Error: cookie_delete requires site"
                deleted = delete_site(site)
                return _json({"ok": True, "site": site, "deleted": bool(deleted)})
        except Exception as exc:
            logger.exception("scrapling action failed: %s", action)
            return _json({"ok": False, "action": action, "message": str(exc)})

        return _json({"ok": False, "message": "Unhandled action"})


def _as_timeout(value) -> int:
    try:
        number = int(value)
    except Exception:
        number = DEFAULT_TIMEOUT_SECONDS
    return max(3, min(180, number))


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)

