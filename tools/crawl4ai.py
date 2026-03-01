"""Crawl4AI tool — crawl webpages and extract LLM-ready markdown."""

import asyncio
import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urlparse

try:
    from fake_useragent import UserAgent
except Exception:
    UserAgent = None

from utils import html_to_markdown, strip_style_blocks

from .registry import BaseTool

logger = logging.getLogger(__name__)

DEFAULT_MAX_LENGTH = 15000
MAX_MAX_LENGTH = 120000
DEFAULT_WAIT_UNTIL = "load"
ALLOWED_WAIT_UNTIL = {"domcontentloaded", "load", "networkidle", "commit"}
DEFAULT_TIMEOUT_MS = 75_000
MAX_TIMEOUT_MS = 240_000
DEFAULT_DELAY_SECONDS = 1.2
MAX_DELAY_SECONDS = 8.0
DEFAULT_WAIT_FOR_TIMEOUT_MS = 20_000
DEFAULT_MAX_ATTEMPTS = 4
MAX_MAX_ATTEMPTS = 6

_CACHE_MODE_NAMES = {
    "enabled": "ENABLED",
    "disabled": "DISABLED",
    "read_only": "READ_ONLY",
    "write_only": "WRITE_ONLY",
    "bypass": "BYPASS",
}


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
                            "cache_mode": {
                                "type": "string",
                                "enum": ["enabled", "disabled", "read_only", "write_only", "bypass"],
                                "default": "bypass",
                                "description": "Cache strategy for Crawl4AI.",
                            },
                            "timeout_ms": {
                                "type": "integer",
                                "default": DEFAULT_TIMEOUT_MS,
                                "description": "Page timeout in milliseconds.",
                            },
                            "delay_seconds": {
                                "type": "number",
                                "default": DEFAULT_DELAY_SECONDS,
                                "description": "Delay before returning final HTML (seconds).",
                            },
                            "magic": {
                                "type": "boolean",
                                "default": True,
                                "description": "Enable Crawl4AI magic behavior for difficult pages.",
                            },
                            "enable_stealth": {
                                "type": "boolean",
                                "default": True,
                                "description": "Apply stealth evasions.",
                            },
                            "simulate_user": {
                                "type": "boolean",
                                "default": True,
                                "description": "Simulate user-like interactions for anti-bot pages.",
                            },
                            "override_navigator": {
                                "type": "boolean",
                                "default": True,
                                "description": "Override navigator fields for anti-bot pages.",
                            },
                            "use_undetected": {
                                "type": "boolean",
                                "default": False,
                                "description": "Use Crawl4AI undetected adapter for stronger anti-bot evasion.",
                            },
                            "retry_antibot": {
                                "type": "boolean",
                                "default": True,
                                "description": "Automatically retry with stronger anti-bot profiles on failure.",
                            },
                            "max_attempts": {
                                "type": "integer",
                                "default": DEFAULT_MAX_ATTEMPTS,
                                "description": "Maximum crawl attempts when retry_antibot=true.",
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Optional session ID for stateful multi-step crawling.",
                            },
                            "wait_for": {
                                "type": "string",
                                "description": (
                                    "Optional wait condition for dynamic content. "
                                    "For example: 'css:.article' or a JS condition."
                                ),
                            },
                            "wait_for_timeout_ms": {
                                "type": "integer",
                                "default": DEFAULT_WAIT_FOR_TIMEOUT_MS,
                                "description": "Timeout for wait_for condition in milliseconds.",
                            },
                            "wait_until": {
                                "type": "string",
                                "enum": ["domcontentloaded", "load", "networkidle", "commit"],
                                "default": DEFAULT_WAIT_UNTIL,
                                "description": "Playwright wait state before extraction.",
                            },
                            "locale": {
                                "type": "string",
                                "default": "zh-CN",
                                "description": "Browser locale, e.g. zh-CN or en-US.",
                            },
                            "timezone_id": {
                                "type": "string",
                                "default": "Asia/Shanghai",
                                "description": "Browser timezone, e.g. Asia/Shanghai or America/New_York.",
                            },
                            "user_agent": {
                                "type": "string",
                                "description": "Optional explicit User-Agent string.",
                            },
                            "user_agent_mode": {
                                "type": "string",
                                "description": "Optional Crawl4AI user-agent generation mode.",
                            },
                            "headers": {
                                "type": "object",
                                "description": "Optional request headers object.",
                            },
                            "cookies": {
                                "type": "array",
                                "description": "Optional cookies array (name/value/domain/path/url...).",
                            },
                            "proxy_config": {
                                "type": "object",
                                "description": (
                                    "Optional proxy configuration. "
                                    "Example: {\"server\":\"http://host:port\",\"username\":\"u\",\"password\":\"p\"}."
                                ),
                            },
                            "js_code": {
                                "type": "string",
                                "description": (
                                    "Optional JavaScript executed before extraction. "
                                    "For multiple snippets, concatenate them in one string."
                                ),
                            },
                            "js_only": {
                                "type": "boolean",
                                "default": False,
                                "description": "Treat request as JS-only update (stateful session flows).",
                            },
                            "css_selector": {
                                "type": "string",
                                "description": "Optional CSS selector to focus extraction.",
                            },
                            "target_elements": {
                                "type": "string",
                                "description": "Optional comma-separated CSS selectors for targeted extraction.",
                            },
                            "excluded_selector": {
                                "type": "string",
                                "description": "Optional CSS selector to exclude from extraction.",
                            },
                            "excluded_tags": {
                                "type": "string",
                                "description": "Optional comma-separated HTML tags to exclude from extraction.",
                            },
                            "wait_for_images": {
                                "type": "boolean",
                                "default": False,
                                "description": "Wait for images before extraction.",
                            },
                            "only_text": {
                                "type": "boolean",
                                "default": False,
                                "description": "Extract text-focused content only.",
                            },
                            "remove_overlay_elements": {
                                "type": "boolean",
                                "default": True,
                                "description": "Try to remove overlays/popups before extraction.",
                            },
                            "process_iframes": {
                                "type": "boolean",
                                "default": True,
                                "description": "Process iframe content when possible.",
                            },
                            "scan_full_page": {
                                "type": "boolean",
                                "default": False,
                                "description": "Scroll full page to load more lazy content.",
                            },
                            "max_scroll_steps": {
                                "type": "integer",
                                "description": "Optional max scroll steps when scan_full_page=true.",
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
        timeout_ms = self._int_arg(arguments.get("timeout_ms"), DEFAULT_TIMEOUT_MS, 1_000, MAX_TIMEOUT_MS)
        delay_seconds = self._float_arg(
            arguments.get("delay_seconds"),
            DEFAULT_DELAY_SECONDS,
            0.0,
            MAX_DELAY_SECONDS,
        )
        wait_for = (arguments.get("wait_for") or "").strip() or None
        wait_for_timeout_ms = self._optional_int_arg(arguments.get("wait_for_timeout_ms"), 1_000, MAX_TIMEOUT_MS)
        if wait_for and wait_for_timeout_ms is None:
            wait_for_timeout_ms = DEFAULT_WAIT_FOR_TIMEOUT_MS
        wait_until = str(arguments.get("wait_until") or DEFAULT_WAIT_UNTIL).strip().lower()
        if wait_until not in ALLOWED_WAIT_UNTIL:
            wait_until = DEFAULT_WAIT_UNTIL
        cache_mode = str(arguments.get("cache_mode") or "bypass").strip().lower()
        if cache_mode not in _CACHE_MODE_NAMES:
            allowed = ", ".join(sorted(_CACHE_MODE_NAMES.keys()))
            return f"Invalid cache_mode: {cache_mode}. Allowed: {allowed}."

        session_id = (arguments.get("session_id") or "").strip() or None
        locale = (arguments.get("locale") or "zh-CN").strip() or None
        timezone_id = (arguments.get("timezone_id") or "Asia/Shanghai").strip() or None
        user_agent = (arguments.get("user_agent") or "").strip() or self._get_random_user_agent()
        user_agent_mode = (arguments.get("user_agent_mode") or "").strip() or None
        headers = self._headers_arg(arguments.get("headers"))
        cookies = self._cookies_arg(arguments.get("cookies"))
        proxy_config = self._proxy_config_arg(arguments.get("proxy_config"))
        js_code = self._js_code_arg(arguments.get("js_code"))
        js_only = self._bool_arg(arguments.get("js_only"), False)
        css_selector = (arguments.get("css_selector") or "").strip() or None
        target_elements = self._string_list_arg(arguments.get("target_elements"))
        excluded_selector = (arguments.get("excluded_selector") or "").strip() or None
        excluded_tags = self._string_list_arg(arguments.get("excluded_tags"))
        wait_for_images = self._bool_arg(arguments.get("wait_for_images"), False)
        only_text = self._bool_arg(arguments.get("only_text"), False)
        magic = self._bool_arg(arguments.get("magic"), True)
        enable_stealth = self._bool_arg(arguments.get("enable_stealth"), True)
        simulate_user = self._bool_arg(arguments.get("simulate_user"), True)
        override_navigator = self._bool_arg(arguments.get("override_navigator"), True)
        remove_overlay_elements = self._bool_arg(arguments.get("remove_overlay_elements"), True)
        process_iframes = self._bool_arg(arguments.get("process_iframes"), True)
        scan_full_page = self._bool_arg(arguments.get("scan_full_page"), False)
        max_scroll_steps = self._optional_int_arg(arguments.get("max_scroll_steps"), 1, 300)
        use_undetected = self._bool_arg(arguments.get("use_undetected"), False)
        retry_antibot = self._bool_arg(arguments.get("retry_antibot"), True)
        max_attempts = self._int_arg(arguments.get("max_attempts"), DEFAULT_MAX_ATTEMPTS, 1, MAX_MAX_ATTEMPTS)

        base_crawl_kwargs = {
            "url": url,
            "timeout_ms": timeout_ms,
            "delay_seconds": delay_seconds,
            "cache_mode": cache_mode,
            "css_selector": css_selector,
            "wait_for": wait_for,
            "wait_for_timeout_ms": wait_for_timeout_ms,
            "wait_until": wait_until,
            "session_id": session_id,
            "locale": locale,
            "timezone_id": timezone_id,
            "user_agent": user_agent,
            "user_agent_mode": user_agent_mode,
            "headers": headers,
            "cookies": cookies,
            "proxy_config": proxy_config,
            "js_code": js_code,
            "js_only": js_only,
            "target_elements": target_elements,
            "excluded_selector": excluded_selector,
            "excluded_tags": excluded_tags,
            "wait_for_images": wait_for_images,
            "only_text": only_text,
            "enable_stealth": enable_stealth,
            "use_undetected": use_undetected,
            "magic": magic,
            "simulate_user": simulate_user,
            "override_navigator": override_navigator,
            "remove_overlay_elements": remove_overlay_elements,
            "process_iframes": process_iframes,
            "scan_full_page": scan_full_page,
            "max_scroll_steps": max_scroll_steps,
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
        cache_mode_value = getattr(CacheMode, _CACHE_MODE_NAMES[cache_mode])
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
    def _get_random_user_agent() -> str | None:
        """获取随机的真实浏览器User-Agent。"""
        try:
            if UserAgent is not None:
                ua = UserAgent()
                return ua.random
        except Exception:
            pass
        # 备用：返回常见的Chrome User-Agent
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    @staticmethod
    def _float_arg(value, default: float, minimum: float, maximum: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _optional_int_arg(value, minimum: int, maximum: int) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _bool_arg(value, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default

    @staticmethod
    def _string_list_arg(value) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            items = [v.strip() for v in value.split(",")]
        elif isinstance(value, list):
            items = [str(v).strip() for v in value]
        else:
            return None
        items = [v for v in items if v]
        if not items:
            return None
        return items[:50]

    @staticmethod
    def _headers_arg(value) -> dict | None:
        if not isinstance(value, dict):
            return None
        out = {}
        for k, v in value.items():
            key = str(k).strip()
            val = str(v).strip()
            if not key:
                continue
            out[key] = val
            if len(out) >= 100:
                break
        return out or None

    @staticmethod
    def _cookies_arg(value) -> list[dict] | None:
        if not isinstance(value, list):
            return None
        out: list[dict] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            cookie = {}
            for key in ("name", "value", "domain", "path", "url", "expires", "httpOnly", "secure", "sameSite"):
                if key in item:
                    cookie[key] = item[key]
            if cookie:
                out.append(cookie)
            if len(out) >= 100:
                break
        return out or None

    @staticmethod
    def _proxy_config_arg(value) -> dict | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            return None
        server = str(value.get("server") or "").strip()
        if not server:
            return None
        out = {"server": server}
        username = str(value.get("username") or "").strip()
        password = str(value.get("password") or "").strip()
        if username:
            out["username"] = username
        if password:
            out["password"] = password
        return out

    @staticmethod
    def _js_code_arg(value) -> str | list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    out.append(text)
                if len(out) >= 20:
                    break
            return out or None
        return None

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
            "\n\nYou have the crawl4ai_fetch tool for rich browser-based crawling.\n"
            "- Use it for JS-heavy pages or when url_fetch snippets are insufficient.\n"
            "- Prefer cache_mode='bypass' for fresh content unless the user wants cached results.\n"
            "- Default to wait_until='load' for higher success on protected pages.\n"
            "- Use css_selector to focus extraction and reduce noise.\n"
            "- First try defaults, then tune wait/session/proxy/js fields only when needed.\n"
        )
