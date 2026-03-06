"""Playwright Chromium-backed browser tool — screenshot and content extraction.

All Playwright operations run on a dedicated worker thread to avoid
greenlet "Cannot switch to a different thread" errors when called from
different executor threads.
"""

import ipaddress
import logging
import os
import queue
import re
import shutil
import socket
import threading
import time
from urllib.parse import urlparse

from utils import html_to_markdown, strip_style_blocks
from utils.browser_realism import (
    apply_context_realism,
    build_context_kwargs,
    humanize_page_presence,
    pick_browser_profile,
)

from .registry import BaseTool, emit_tool_progress

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_LENGTH = 15000
MAX_CONTENT_LENGTH = 80000
PAGE_TIMEOUT_MS = 60_000
DEFAULT_WAIT = 5
MAX_WAIT = 15
_NAVIGATION_WAIT_UNTILS = ("load", "domcontentloaded", "networkidle")
_NAVIGATION_RETRY_SLEEP_SECONDS = 0.7

# ── Pending screenshot queue (same pattern as TTS) ──

_PENDING_SCREENSHOTS: dict[int, list[dict]] = {}
_PENDING_LOCK = threading.Lock()


def _enqueue_screenshot(user_id: int, job: dict) -> None:
    with _PENDING_LOCK:
        _PENDING_SCREENSHOTS.setdefault(user_id, []).append(job)


def drain_pending_screenshots(user_id: int) -> list[dict]:
    """Drain and return pending screenshot jobs for a user."""
    with _PENDING_LOCK:
        return _PENDING_SCREENSHOTS.pop(user_id, [])


# ── Dedicated Playwright worker thread ──
#
# Playwright's sync API uses greenlets that are pinned to the thread where
# sync_playwright().start() was called.  Since tool.execute() is invoked via
# run_in_executor (thread pool), different calls may land on different threads,
# causing "Cannot switch to a different thread".
#
# Solution: a single long-lived daemon thread owns the Playwright instance.
# Callers submit work via a queue and block until the result is ready.

_work_queue: queue.Queue = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
_worker_runtime: dict[str, object] = {
    "engine": "chromium",
    "headless": None,
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


def _is_display_launch_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "missing x server",
        "$display",
        "ozone_platform_x11",
        "the platform failed to initialize",
    )
    return any(marker in message for marker in markers)


def _resolve_chromium_executable() -> str | None:
    candidates = [
        (os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or "").strip(),
        (os.getenv("CHROMIUM_PATH") or "").strip(),
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        shutil.which("google-chrome") or "",
        shutil.which("google-chrome-stable") or "",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _build_chromium_launch_kwargs(headless: bool) -> dict[str, object]:
    launch_kwargs: dict[str, object] = {
        "headless": headless,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    executable = _resolve_chromium_executable()
    if executable:
        launch_kwargs["executable_path"] = executable
    return launch_kwargs


def _launch_browser_with_fallback(pw):
    global _worker_runtime

    headless = _resolve_playwright_headless()
    launch_kwargs = _build_chromium_launch_kwargs(headless)
    try:
        browser = pw.chromium.launch(**launch_kwargs)
        _worker_runtime = {
            "engine": "chromium",
            "headless": headless,
            "executable": launch_kwargs.get("executable_path") or "bundled",
        }
        logger.info(
            "Playwright worker thread started with Chromium (headless=%s, executable=%s)",
            headless,
            _worker_runtime.get("executable"),
        )
        return browser
    except Exception as e:
        if not headless and _is_display_launch_error(e):
            logger.warning(
                "Headed Chromium launch failed due display environment, retrying headless fallback."
            )
            launch_kwargs = _build_chromium_launch_kwargs(True)
            browser = pw.chromium.launch(**launch_kwargs)
            _worker_runtime = {
                "engine": "chromium",
                "headless": True,
                "executable": launch_kwargs.get("executable_path") or "bundled",
            }
            logger.info(
                "Playwright worker thread started with Chromium (headless=%s, executable=%s, fallback=true)",
                True,
                _worker_runtime.get("executable"),
            )
            return browser
        raise


def _playwright_worker():
    """Long-lived thread that owns the Playwright browser."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = _launch_browser_with_fallback(pw)

    while True:
        item = _work_queue.get()
        if item is None:  # shutdown sentinel
            break
        func, args, result_q = item
        try:
            result = func(browser, *args)
            result_q.put(("ok", result))
        except Exception as e:
            result_q.put(("error", e))

    browser.close()
    pw.stop()


def _ensure_worker():
    """Start the worker thread if it isn't running yet."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_playwright_worker, daemon=True)
        _worker_thread.start()


def _run_on_worker(func, *args):
    """Submit *func(browser, \\*args)* to the worker thread and wait for the result."""
    _ensure_worker()
    result_q: queue.Queue = queue.Queue()
    _work_queue.put((func, args, result_q))
    while True:
        try:
            status, value = result_q.get(timeout=1.0)
            if status == "error":
                raise value
            return value
        except queue.Empty:
            if _worker_thread is None or not _worker_thread.is_alive():
                raise RuntimeError(
                    "Playwright browser worker crashed or exited. "
                    "Check browser dependencies in the container."
                )


def prewarm_playwright_worker() -> tuple[bool, str]:
    """Start Playwright worker/browser early so first call is warm."""

    def _noop(browser):
        _ = browser
        return True

    try:
        _run_on_worker(_noop)
        engine = str(_worker_runtime.get("engine") or "chromium")
        headless = _worker_runtime.get("headless")
        executable = str(_worker_runtime.get("executable") or "bundled")
        return True, f"engine={engine} headless={headless} executable={executable}"
    except Exception as e:
        logger.exception("playwright prewarm failed: %s", e)
        return False, str(e)


def _open_browser_page(browser, *, seed_hint: str | None = None):
    """Open an isolated context/page for one tool call."""
    profile = pick_browser_profile(seed_hint=seed_hint)
    context = browser.new_context(
        **build_context_kwargs(profile, viewport_override={"width": 1366, "height": 768}),
    )
    apply_context_realism(context, profile)
    page = context.new_page()
    return context, page


def _is_retryable_navigation_error(exc: Exception) -> bool:
    msg = str(exc or "").lower()
    markers = (
        "ns_error_net_interrupt",
        "ns_error_connection",
        "timed out",
        "timeout",
        "connection reset",
        "connection closed",
        "net::err",
    )
    return any(marker in msg for marker in markers)


def _goto_with_retry(page, url: str, timeout_ms: int) -> str:
    last_exc: Exception | None = None
    for attempt, wait_until in enumerate(_NAVIGATION_WAIT_UNTILS, start=1):
        try:
            page.goto(url, timeout=timeout_ms, wait_until=wait_until)
            return wait_until
        except Exception as e:
            last_exc = e
            logger.warning(
                "page.goto failed (attempt=%d/%d, wait_until=%s): %s",
                attempt,
                len(_NAVIGATION_WAIT_UNTILS),
                wait_until,
                e,
            )
            if not _is_retryable_navigation_error(e):
                raise
            try:
                page.goto("about:blank", timeout=12_000, wait_until="domcontentloaded")
            except Exception:
                pass
            if attempt < len(_NAVIGATION_WAIT_UNTILS):
                time.sleep(_NAVIGATION_RETRY_SLEEP_SECONDS)

    if last_exc:
        raise last_exc
    raise RuntimeError("Navigation failed without an exception")


_CF_WAIT_ROUNDS = 4      # number of retry checks after detecting CF
_CF_WAIT_INTERVAL = 3    # seconds between each check


def _is_cf_challenge(page) -> bool:
    """Return True if the page is currently showing a CF challenge."""
    try:
        title = page.title().lower()
        cf_titles = ["just a moment", "attention required", "please wait"]
        if any(t in title for t in cf_titles):
            return True
        cf_el = page.query_selector(
            "#challenge-running, #challenge-stage, .cf-turnstile, #cf-challenge-running"
        )
        if cf_el:
            return True
    except Exception:
        pass
    return False


def _wait_for_cf_pass(page) -> str | None:
    """If the page is a CF challenge, wait for the JS challenge to auto-resolve.

    Returns an error message if CF is still blocking after all retries, or None
    if the challenge resolved (or was never present).
    """
    if not _is_cf_challenge(page):
        return None

    logger.info("Cloudflare challenge detected, waiting for JS challenge to resolve...")
    for i in range(_CF_WAIT_ROUNDS):
        time.sleep(_CF_WAIT_INTERVAL)
        if not _is_cf_challenge(page):
            logger.info("Cloudflare challenge resolved after %ds", (i + 1) * _CF_WAIT_INTERVAL)
            return None

    return (
        "This page is protected by Cloudflare verification. "
        "The JS challenge did not auto-resolve after "
        f"{_CF_WAIT_ROUNDS * _CF_WAIT_INTERVAL}s. "
        "The page cannot be accessed by an automated browser."
    )


def _prepare_page_after_navigation(page, wait_seconds: float) -> str | None:
    """Run anti-bot wait and lightweight human-like warmup before extraction."""
    cf_err = _wait_for_cf_pass(page)
    if cf_err:
        return cf_err

    humanize_page_presence(page)
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    # Re-check after waiting in case challenge appears late.
    return _wait_for_cf_pass(page)


# ── URL safety (reuses fetch.py pattern) ──

def _validate_url(url: str) -> str:
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


# ── Tool definitions ──

PAGE_SCREENSHOT_TOOL = {
    "type": "function",
    "function": {
        "name": "page_screenshot",
        "description": (
            "Take a screenshot of a webpage and send it as an image. "
            "Useful for showing the user what a website looks like."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the webpage to screenshot",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Whether to capture the full scrollable page (default: false, viewport only)",
                    "default": False,
                },
                "wait": {
                    "type": "number",
                    "description": "Extra seconds to wait after page load for JS rendering (default: 2, max: 10)",
                    "default": 2,
                },
            },
            "required": ["url"],
        },
    },
}

PAGE_CONTENT_TOOL = {
    "type": "function",
    "function": {
        "name": "page_content",
        "description": (
            "Extract text content from a webpage using a real browser. "
            "Better than url_fetch for JS-heavy pages that need rendering."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the webpage to extract content from",
                },
                "wait": {
                    "type": "number",
                    "description": "Extra seconds to wait after page load for JS rendering (default: 2, max: 10)",
                    "default": 2,
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 15000)",
                    "default": 15000,
                },
            },
            "required": ["url"],
        },
    },
}


class PlaywrightTool(BaseTool):
    """Browser-based webpage screenshot and content extraction tool."""

    @property
    def name(self) -> str:
        return "playwright"

    def definitions(self) -> list[dict]:
        return [PAGE_SCREENSHOT_TOOL, PAGE_CONTENT_TOOL]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name == "page_screenshot":
            return self._screenshot(user_id, arguments)
        if tool_name == "page_content":
            return self._content(arguments)
        return f"Unknown playwright tool: {tool_name}"

    def _screenshot(self, user_id: int, arguments: dict) -> str:
        raw_url = (arguments.get("url") or "").strip()
        if not raw_url:
            return "No URL provided."
        try:
            url = _validate_url(raw_url)
        except ValueError as e:
            return f"URL rejected: {e}"

        full_page = bool(arguments.get("full_page", False))
        wait = min(max(float(arguments.get("wait", DEFAULT_WAIT)), 0), MAX_WAIT)
        emit_tool_progress(
            f"Opening browser for screenshot: {url}",
            tool_name="page_screenshot",
            stage="navigate",
        )

        def _do(browser, _url, _full_page, _wait):
            context, page = _open_browser_page(browser, seed_hint=_url)
            try:
                used_wait = _goto_with_retry(page, _url, PAGE_TIMEOUT_MS)
                cf_err = _prepare_page_after_navigation(page, _wait)
                if cf_err:
                    return ("cf_blocked", cf_err)
                return ("ok", page.screenshot(full_page=_full_page, type="png"), used_wait)
            finally:
                try:
                    page.close()
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass

        try:
            result = _run_on_worker(_do, url, full_page, wait)
        except Exception as e:
            logger.exception("page_screenshot failed for '%s'", url)
            return f"Screenshot failed: {e}"

        status = result[0]
        if status == "cf_blocked":
            return result[1]

        # Truncate URL for caption
        caption = url if len(url) <= 200 else url[:200] + "..."
        image = result[1]
        used_wait = result[2]
        _enqueue_screenshot(user_id, {
            "image": image,
            "filename": "screenshot.png",
            "caption": f"📸 {caption}",
        })

        engine = str(_worker_runtime.get("engine") or "chromium")
        headless = _worker_runtime.get("headless")
        return (
            f"Screenshot captured and queued for delivery. "
            f"URL: {url}, full_page={full_page}, browser_engine={engine}, headless={headless}, wait_until={used_wait}"
        )

    def _content(self, arguments: dict) -> str:
        raw_url = (arguments.get("url") or "").strip()
        if not raw_url:
            return "No URL provided."
        try:
            url = _validate_url(raw_url)
        except ValueError as e:
            return f"URL rejected: {e}"

        wait = min(max(float(arguments.get("wait", DEFAULT_WAIT)), 0), MAX_WAIT)
        max_length = arguments.get("max_length", DEFAULT_CONTENT_LENGTH)
        try:
            max_length = int(max_length)
        except (TypeError, ValueError):
            max_length = DEFAULT_CONTENT_LENGTH
        max_length = max(200, min(max_length, MAX_CONTENT_LENGTH))
        emit_tool_progress(
            f"Opening browser for content extraction: {url}",
            tool_name="page_content",
            stage="navigate",
        )

        def _do(browser, _url, _wait):
            context, page = _open_browser_page(browser, seed_hint=_url)
            try:
                used_wait = _goto_with_retry(page, _url, PAGE_TIMEOUT_MS)
                cf_err = _prepare_page_after_navigation(page, _wait)
                if cf_err:
                    return ("cf_blocked", cf_err)
                # Remove non-content nodes so CSS/JS text doesn't leak into markdown.
                try:
                    page.evaluate(
                        """
                        () => {
                          document.querySelectorAll('style,script,noscript').forEach((el) => el.remove());
                        }
                        """
                    )
                except Exception:
                    logger.debug("Failed to prune style/script tags for %s", _url, exc_info=True)
                # Get HTML content and convert to Markdown (preserves links)
                html = page.content()
                return ("ok", html, _url, used_wait)
            finally:
                try:
                    page.close()
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass

        try:
            result = _run_on_worker(_do, url, wait)
        except Exception as e:
            logger.exception("page_content failed for '%s'", url)
            return f"Content extraction failed: {e}"

        if result[0] == "cf_blocked":
            return result[1]

        _, html, page_url, used_wait = result

        if not html or not html.strip():
            return "Page returned empty content."

        # Convert HTML to Markdown (preserves links, images, tables, etc.)
        text = html_to_markdown(html, base_url=page_url)
        text = strip_style_blocks(text)

        if not text or not text.strip():
            return "Page returned empty content."

        text = text.strip()
        if len(text) > max_length:
            text = text[:max_length] + "\n...(truncated)"

        logger.info("page_content navigation wait_until=%s for url=%s", used_wait, url)
        return text

    def get_instruction(self) -> str:
        return (
            "\n\nYou have browser tools (page_screenshot, page_content) powered by Playwright Chromium.\n"
            "- Use page_screenshot to capture a webpage screenshot and send it as an image.\n"
            "- Use page_content to extract text from JS-heavy pages that need browser rendering.\n"
            "- These tools launch a real browser, so they handle JavaScript-rendered content.\n"
            "- Runtime prefers a local Chromium executable when available.\n"
        )
