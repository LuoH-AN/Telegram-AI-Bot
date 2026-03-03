"""Crawl4AI tool — crawl webpages and extract LLM-ready markdown."""

import asyncio
import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urlparse

from utils import html_to_markdown, strip_style_blocks
from utils.browser_realism import build_extra_http_headers, pick_browser_profile

from .registry import BaseTool, emit_tool_progress

logger = logging.getLogger(__name__)

DEFAULT_MAX_LENGTH = 15000
MAX_MAX_LENGTH = 120000
DEFAULT_WAIT_UNTIL = "load"
DEFAULT_TIMEOUT_MS = 75_000
DEFAULT_DELAY_SECONDS = 1.4
DEFAULT_WAIT_FOR_TIMEOUT_MS = 20_000
DEFAULT_MAX_ATTEMPTS = 4
_DEFAULT_CACHE_MODE = "bypass"
_CACHE_MODE_MEMBER = "BYPASS"

def _has_usable_display() -> bool:
    """Best-effort check for an actually usable GUI display."""
    wayland = (os.getenv("WAYLAND_DISPLAY") or "").strip()
    if wayland:
        if "/" in wayland:
            return os.path.exists(wayland)
        runtime = (os.getenv("XDG_RUNTIME_DIR") or "").strip()
        if runtime and os.path.exists(os.path.join(runtime, wayland)):
            return True
        return True

    display = (os.getenv("DISPLAY") or "").strip()
    if not display:
        return False
    if display.startswith(":"):
        m = re.match(r"^:([0-9]+)", display)
        if m:
            return os.path.exists(f"/tmp/.X11-unix/X{m.group(1)}")
    return True


def _resolve_playwright_headless() -> bool:
    """Resolve headless mode from env and display availability."""
    raw = (
        os.getenv("BROWSER_HEADLESS")
        or os.getenv("PLAYWRIGHT_HEADLESS")
        or "auto"
    )
    mode = str(raw).strip().lower()
    has_display = _has_usable_display()

    if mode in {"1", "true", "yes", "on", "headless"}:
        return True
    if mode in {"0", "false", "no", "off", "headed"}:
        if has_display:
            return False
        logger.warning(
            "Headed browser requested but no DISPLAY/WAYLAND_DISPLAY found; falling back to headless."
        )
        return True
    return not has_display


class Crawl4AITool(BaseTool):
    """Tool for crawling modern webpages with Crawl4AI."""

    @property
    def name(self) -> str:
        return "crawl4ai"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "crawl4ai_fetch",
                    "description": (
                        "Fetch and render a webpage using Crawl4AI. "
                        "Returns markdown-like content that is suitable for LLM use."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "Target page URL (http/https).",
                            },
                            "max_length": {
                                "type": "integer",
                                "default": DEFAULT_MAX_LENGTH,
                                "description": "Maximum characters to return.",
                            },
                            "focus_selector": {
                                "type": "string",
                                "description": "Optional CSS selector for focusing extraction (e.g. article main body).",
                            },
                        },
                        "required": ["url"],
                    },
                },
            }
        ]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name != "crawl4ai_fetch":
            return f"Unknown tool: {tool_name}"

        raw_url = (arguments.get("url") or "").strip()
        if not raw_url:
            return "No URL provided."

        try:
            url = self._validate_external_url(raw_url)
        except ValueError as e:
            return f"URL rejected: {e}"

        max_length = self._int_arg(arguments.get("max_length"), DEFAULT_MAX_LENGTH, 200, MAX_MAX_LENGTH)
        css_selector = (
            (arguments.get("focus_selector") or arguments.get("css_selector") or "")
            .strip()
            or None
        )
        ignored_keys = [k for k in arguments.keys() if k not in {"url", "max_length", "focus_selector", "css_selector"}]
        if ignored_keys:
            preview = ", ".join(sorted(ignored_keys)[:6])
            if len(ignored_keys) > 6:
                preview += ", ..."
            logger.debug("crawl4ai_fetch ignored advanced args: %s", preview)

        # Keep AI-facing parameters intentionally minimal.
        # All advanced crawl strategy knobs are fixed here to stable defaults.
        retry_antibot = True
        max_attempts = DEFAULT_MAX_ATTEMPTS
        browser_profile = pick_browser_profile(seed_hint=url)
        profile_locale = str(browser_profile.get("locale") or "en-US")
        profile_timezone = str(browser_profile.get("timezone_id") or "America/Los_Angeles")
        profile_user_agent = str(browser_profile.get("user_agent") or "").strip() or None
        profile_headers = build_extra_http_headers(browser_profile)

        base_crawl_kwargs = {
            "url": url,
            "timeout_ms": DEFAULT_TIMEOUT_MS,
            "delay_seconds": DEFAULT_DELAY_SECONDS,
            "cache_mode": _DEFAULT_CACHE_MODE,
            "css_selector": css_selector,
            "wait_for": None,
            "wait_for_timeout_ms": None,
            "wait_until": DEFAULT_WAIT_UNTIL,
            "session_id": None,
            "locale": profile_locale,
            "timezone_id": profile_timezone,
            "user_agent": profile_user_agent,
            "user_agent_mode": None,
            "headers": profile_headers,
            "cookies": None,
            "proxy_config": None,
            "js_code": None,
            "js_only": False,
            "target_elements": None,
            "excluded_selector": None,
            "excluded_tags": None,
            "wait_for_images": True,
            "only_text": False,
            "enable_stealth": True,
            "use_undetected": False,
            "magic": True,
            "simulate_user": True,
            "override_navigator": True,
            "remove_overlay_elements": True,
            "process_iframes": True,
            "scan_full_page": False,
            "max_scroll_steps": None,
        }

        attempt_chain = self._build_attempt_chain(
            base_crawl_kwargs,
            retry_antibot=retry_antibot,
            max_attempts=max_attempts,
        )
        text = ""
        attempt_errors: list[str] = []

        for idx, attempt in enumerate(attempt_chain, start=1):
            profile_name = attempt.get("name", f"attempt_{idx}")
            attempt_kwargs = attempt["kwargs"]
            try:
                emit_tool_progress(
                    f"Crawl attempt {idx}/{len(attempt_chain)} profile={profile_name}",
                    tool_name="crawl4ai_fetch",
                    stage="attempt",
                    attempt=idx,
                    total_attempts=len(attempt_chain),
                    profile=profile_name,
                )
                logger.info(
                    "crawl4ai_fetch attempt %d/%d for '%s' using profile=%s",
                    idx,
                    len(attempt_chain),
                    url,
                    profile_name,
                )
                candidate = asyncio.run(self._crawl_url(**attempt_kwargs))
                candidate = strip_style_blocks(candidate or "").strip()
                if candidate:
                    text = candidate
                    break
                attempt_errors.append(f"{profile_name}: empty content")
            except Exception as e:
                summary = self._summarize_error(e)
                logger.warning(
                    "crawl4ai_fetch attempt %d/%d failed for '%s' profile=%s: %s",
                    idx,
                    len(attempt_chain),
                    url,
                    profile_name,
                    summary,
                )
                attempt_errors.append(f"{profile_name}: {summary}")
                if not retry_antibot:
                    break

        if not text:
            if attempt_errors:
                last = attempt_errors[-1]
                return f"Crawl failed after {len(attempt_chain)} attempt(s): {last}"
            return "Crawl returned empty content."

        if len(text) > max_length:
            text = text[:max_length] + "\n...(truncated)"
        return text

    async def _crawl_url(
        self,
        *,
        url: str,
        timeout_ms: int,
        delay_seconds: float,
        cache_mode: str,
        css_selector: str | None,
        wait_for: str | None,
        wait_for_timeout_ms: int | None,
        wait_until: str,
        session_id: str | None,
        locale: str | None,
        timezone_id: str | None,
        user_agent: str | None,
        user_agent_mode: str | None,
        headers: dict | None,
        cookies: list[dict] | None,
        proxy_config: dict | None,
        js_code: str | list[str] | None,
        js_only: bool,
        target_elements: list[str] | None,
        excluded_selector: str | None,
        excluded_tags: list[str] | None,
        wait_for_images: bool,
        only_text: bool,
        enable_stealth: bool,
        use_undetected: bool,
        magic: bool,
        simulate_user: bool,
        override_navigator: bool,
        remove_overlay_elements: bool,
        process_iframes: bool,
        scan_full_page: bool,
        max_scroll_steps: int | None,
    ) -> str:
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
            from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
        except Exception as e:
            raise RuntimeError(
                "crawl4ai is unavailable. Please install crawl4ai and run crawl4ai-setup."
            ) from e

        browser_enable_stealth = bool(enable_stealth and not use_undetected)
        headless = _resolve_playwright_headless()
        _ = cache_mode  # cache strategy is intentionally fixed by tool defaults
        cache_mode_value = getattr(CacheMode, _CACHE_MODE_MEMBER)
        browser_config = BrowserConfig(
            browser_type="chromium",
            headless=headless,
            enable_stealth=browser_enable_stealth,
            user_agent=user_agent or BrowserConfig().user_agent,
            user_agent_mode=user_agent_mode or "",
            headers=headers,
            cookies=cookies,
            proxy_config=proxy_config,
            verbose=False,
        )
        logger.info(
            "crawl4ai browser config resolved (headless=%s, undetected=%s, stealth=%s)",
            headless,
            bool(use_undetected),
            browser_enable_stealth,
        )
        run_config = CrawlerRunConfig(
            cache_mode=cache_mode_value,
            css_selector=css_selector,
            target_elements=target_elements,
            excluded_selector=excluded_selector,
            excluded_tags=excluded_tags,
            wait_for=wait_for,
            wait_for_timeout=wait_for_timeout_ms,
            wait_until=wait_until,
            page_timeout=timeout_ms,
            delay_before_return_html=delay_seconds,
            session_id=session_id,
            locale=locale,
            timezone_id=timezone_id,
            proxy_config=proxy_config,
            js_code=js_code,
            js_only=js_only,
            wait_for_images=wait_for_images,
            only_text=only_text,
            magic=magic,
            simulate_user=simulate_user,
            override_navigator=override_navigator,
            remove_overlay_elements=remove_overlay_elements,
            process_iframes=process_iframes,
            scan_full_page=scan_full_page,
            max_scroll_steps=max_scroll_steps,
            verbose=False,
        )

        if use_undetected:
            try:
                from crawl4ai.browser_adapter import UndetectedAdapter
            except Exception as e:
                raise RuntimeError(
                    "use_undetected=true requires crawl4ai UndetectedAdapter support."
                ) from e
            strategy = AsyncPlaywrightCrawlerStrategy(
                browser_config=browser_config,
                browser_adapter=UndetectedAdapter(),
            )
            crawler = AsyncWebCrawler(crawler_strategy=strategy, config=browser_config)
        else:
            crawler = AsyncWebCrawler(config=browser_config)

        async with crawler:
            result = await crawler.arun(url=url, config=run_config)

        if not getattr(result, "success", False):
            error_message = (getattr(result, "error_message", "") or "").strip()
            raise RuntimeError(error_message or "crawl4ai returned success=False")

        markdown = getattr(result, "markdown", None)
        if markdown:
            # StringCompatibleMarkdown can be cast directly to string.
            text = str(markdown).strip()
            if text:
                return text

            fit_markdown = getattr(markdown, "fit_markdown", None)
            if fit_markdown:
                fit_text = str(fit_markdown).strip()
                if fit_text:
                    return fit_text

            raw_markdown = getattr(markdown, "raw_markdown", None)
            if raw_markdown:
                raw_text = str(raw_markdown).strip()
                if raw_text:
                    return raw_text

        cleaned_html = (getattr(result, "cleaned_html", "") or "").strip()
        if cleaned_html:
            return html_to_markdown(cleaned_html, base_url=url).strip()

        html = (getattr(result, "html", "") or "").strip()
        if html:
            return html_to_markdown(html, base_url=url).strip()

        return ""

    @staticmethod
    def _int_arg(value, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _build_attempt_chain(
        crawl_kwargs: dict,
        *,
        retry_antibot: bool,
        max_attempts: int,
    ) -> list[dict]:
        base = dict(crawl_kwargs)
        chain = [{"name": "standard", "kwargs": base}]

        if not retry_antibot:
            return chain

        aggressive = dict(base)
        aggressive["wait_until"] = "load"
        aggressive["wait_for"] = base.get("wait_for") or "css:body"
        aggressive["wait_for_timeout_ms"] = base.get("wait_for_timeout_ms") or DEFAULT_WAIT_FOR_TIMEOUT_MS
        aggressive["delay_seconds"] = max(float(base.get("delay_seconds", DEFAULT_DELAY_SECONDS)), 1.6)
        aggressive["enable_stealth"] = True
        aggressive["simulate_user"] = True
        aggressive["override_navigator"] = True
        aggressive["magic"] = True
        aggressive["remove_overlay_elements"] = True
        aggressive["process_iframes"] = True
        chain.append({"name": "antibot", "kwargs": aggressive})

        undetected = dict(aggressive)
        undetected["use_undetected"] = True
        undetected["enable_stealth"] = False
        chain.append({"name": "undetected", "kwargs": undetected})

        safe = Crawl4AITool._build_safe_retry_kwargs(base)
        chain.append({"name": "safe", "kwargs": safe})

        return chain[: max(1, max_attempts)]

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

    @staticmethod
    def _summarize_error(error: Exception) -> str:
        text = str(error or "").strip()
        if not text:
            return error.__class__.__name__

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            if "error while loading shared libraries:" in line:
                return (
                    f"{line}. Install missing browser deps and rerun "
                    "crawl4ai-setup / playwright install --with-deps."
                )

        first = lines[0] if lines else text
        if len(first) > 350:
            return first[:350] + "..."
        return first

    @staticmethod
    def _build_safe_retry_kwargs(crawl_kwargs: dict) -> dict:
        retry = dict(crawl_kwargs)
        retry["wait_until"] = DEFAULT_WAIT_UNTIL
        retry["wait_for"] = None
        retry["wait_for_timeout_ms"] = None
        retry["delay_seconds"] = min(
            float(crawl_kwargs.get("delay_seconds", DEFAULT_DELAY_SECONDS)),
            DEFAULT_DELAY_SECONDS,
        )
        retry["scan_full_page"] = False
        retry["max_scroll_steps"] = None
        retry["process_iframes"] = False
        retry["remove_overlay_elements"] = False
        retry["magic"] = False
        retry["simulate_user"] = False
        retry["override_navigator"] = False
        retry["use_undetected"] = False
        return retry

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the crawl4ai_fetch tool for browser-based crawling.\n"
            "- Keep calls simple: only pass url (and optional max_length / focus_selector).\n"
            "- Anti-bot retries, wait strategy, stealth, and browser settings are internally fixed.\n"
            "- Use focus_selector only when the user asks for a specific page section.\n"
        )
