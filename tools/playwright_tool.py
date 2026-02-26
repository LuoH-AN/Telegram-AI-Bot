"""Playwright tool — take webpage screenshots and extract page content.

All Playwright operations run on a dedicated worker thread to avoid
greenlet "Cannot switch to a different thread" errors when called from
different executor threads.
"""

import ipaddress
import logging
import queue
import socket
import threading
import time
from urllib.parse import urlparse

from utils import html_to_markdown

from .registry import BaseTool

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_LENGTH = 15000
MAX_CONTENT_LENGTH = 80000
PAGE_TIMEOUT_MS = 60_000
DEFAULT_WAIT = 5
MAX_WAIT = 15

# Realistic Chrome UA to reduce bot detection
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Comprehensive stealth JS to hide automation signals (injected via addInitScript)
_STEALTH_JS = """
// Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete navigator.__proto__.webdriver;

// Realistic languages
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});

// Fake plugins (headless has none by default)
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const p = {
      0: {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: {name: 'Chrome PDF Plugin'}},
      length: 1,
      item: i => p[i],
      namedItem: n => p[0],
      refresh: () => {},
    };
    return p;
  }
});

// Chrome runtime object
window.chrome = {
  app: {isInstalled: false, InstallState: {DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'}, RunningState: {CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'}},
  runtime: {OnInstalledReason: {CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update'}, PlatformArch: {ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64'}, PlatformOs: {ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win'}, RequestUpdateCheckStatus: {NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available'}, connect: function(){}, sendMessage: function(){}},
  loadTimes: function(){return {}},
  csi: function(){return {}},
};

// Permissions API — make 'notifications' return 'denied' like a real browser
const origQuery = window.Permissions?.prototype?.query;
if (origQuery) {
  window.Permissions.prototype.query = function(params) {
    return params?.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : origQuery.call(this, params);
  };
}

// Prevent iframe detection of window.length mismatch
Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
  get: function() { return window; }
});

// WebGL vendor/renderer — return realistic values
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
  if (param === 37445) return 'Google Inc. (NVIDIA)';
  if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
  return getParameter.call(this, param);
};
const getParameter2 = WebGL2RenderingContext?.prototype?.getParameter;
if (getParameter2) {
  WebGL2RenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Google Inc. (NVIDIA)';
    if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
    return getParameter2.call(this, param);
  };
}

// Connection type
Object.defineProperty(navigator, 'connection', {
  get: () => ({effectiveType: '4g', rtt: 50, downlink: 10, saveData: false})
});

// Hardware concurrency & device memory
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
"""

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


def _playwright_worker():
    """Long-lived thread that owns the Playwright browser."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=False,
        args=[
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--font-render-hinting=none",
            "--lang=zh-CN",
            "--disable-dev-shm-usage",
        ],
    )
    logger.info("Playwright worker thread started, Chromium launched")

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
    status, value = result_q.get()  # blocks until worker finishes
    if status == "error":
        raise value
    return value


def _new_stealth_context(browser):
    """Create a browser context with stealth settings to reduce bot detection."""
    from playwright_stealth import Stealth

    stealth = Stealth()
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        user_agent=_USER_AGENT,
    )
    context.add_init_script(_STEALTH_JS)
    stealth.apply_stealth_sync(context)
    return context


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

        def _do(browser, _url, _full_page, _wait):
            context = _new_stealth_context(browser)
            page = context.new_page()
            try:
                page.goto(_url, timeout=PAGE_TIMEOUT_MS, wait_until="networkidle")
                if _wait > 0:
                    time.sleep(_wait)
                cf_err = _wait_for_cf_pass(page)
                if cf_err:
                    return ("cf_blocked", cf_err)
                return ("ok", page.screenshot(full_page=_full_page, type="png"))
            finally:
                page.close()
                context.close()

        try:
            status, result = _run_on_worker(_do, url, full_page, wait)
        except Exception as e:
            logger.exception("page_screenshot failed for '%s'", url)
            return f"Screenshot failed: {e}"

        if status == "cf_blocked":
            return result

        # Truncate URL for caption
        caption = url if len(url) <= 200 else url[:200] + "..."
        _enqueue_screenshot(user_id, {
            "image": result,
            "filename": "screenshot.png",
            "caption": f"📸 {caption}",
        })

        return f"Screenshot captured and queued for delivery. URL: {url}, full_page={full_page}"

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

        def _do(browser, _url, _wait):
            context = _new_stealth_context(browser)
            page = context.new_page()
            try:
                # Use networkidle for better JS rendering on SPA sites
                page.goto(_url, timeout=PAGE_TIMEOUT_MS, wait_until="networkidle")
                if _wait > 0:
                    time.sleep(_wait)
                cf_err = _wait_for_cf_pass(page)
                if cf_err:
                    return ("cf_blocked", cf_err)
                # Get HTML content and convert to Markdown (preserves links)
                html = page.content()
                return ("ok", html, _url)
            finally:
                page.close()
                context.close()

        try:
            result = _run_on_worker(_do, url, wait)
        except Exception as e:
            logger.exception("page_content failed for '%s'", url)
            return f"Content extraction failed: {e}"

        if result[0] == "cf_blocked":
            return result[1]

        _, html, page_url = result

        if not html or not html.strip():
            return "Page returned empty content."

        # Convert HTML to Markdown (preserves links, images, tables, etc.)
        text = html_to_markdown(html, base_url=page_url)

        if not text or not text.strip():
            return "Page returned empty content."

        text = text.strip()
        if len(text) > max_length:
            text = text[:max_length] + "\n...(truncated)"

        return text

    def get_instruction(self) -> str:
        return (
            "\n\nYou have browser tools (page_screenshot, page_content) powered by Playwright.\n"
            "- Use page_screenshot to capture a webpage screenshot and send it as an image.\n"
            "- Use page_content to extract text from JS-heavy pages that need browser rendering.\n"
            "- These tools launch a real browser, so they handle JavaScript-rendered content.\n"
        )
