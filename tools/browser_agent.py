"""Browser Agent tool — stateful step-by-step browser control."""

import ipaddress
import json
import logging
import os
import queue
import random
import re
import secrets
import shutil
import socket
import threading
import time
from urllib.parse import urlparse

from config import WEB_BASE_URL
from hf_dataset_store import get_hf_dataset_store
from utils.browser_realism import (
    apply_context_realism,
    build_context_kwargs,
    humanize_page_presence,
    pick_browser_profile,
)

from .registry import BaseTool

logger = logging.getLogger(__name__)

PAGE_TIMEOUT_MS = 60_000
DEFAULT_WAIT_SECONDS = 1.5
MAX_WAIT_SECONDS = 20
DEFAULT_ACTION_TIMEOUT_MS = 10_000
MAX_ACTION_TIMEOUT_MS = 120_000
DEFAULT_WAIT_UNTIL = "domcontentloaded"
ALLOWED_WAIT_UNTIL = {"domcontentloaded", "load", "networkidle", "commit"}
ALLOWED_WAIT_STATES = {"visible", "attached", "hidden", "detached"}

MAX_SESSIONS_PER_USER = 3
MAX_SESSIONS_TOTAL = 30
SESSION_IDLE_TTL_SECONDS = 20 * 60
VIEWER_LINK_TTL_SECONDS = 6 * 60 * 60
VIEWER_REFRESH_HINT_MS = 1200
_VIEWER_TOKEN_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")

# ── Dedicated worker and in-worker session store ──

_work_queue: queue.Queue = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
_sessions: dict[str, dict] = {}
_viewer_lock = threading.Lock()
_viewer_links: dict[str, dict] = {}
_browser_runtime: dict[str, object] = {"engine": "chromium"}
_HF_STATE_PATH = "browser/{user_id}/storage_state.json"


def _clamp_point(x: float, y: float, width: int, height: int) -> tuple[float, float]:
    safe_x = max(1.0, min(float(x), max(1.0, width - 1.0)))
    safe_y = max(1.0, min(float(y), max(1.0, height - 1.0)))
    return safe_x, safe_y


def _humanized_mouse_click(
    page,
    session: dict,
    target_x: float,
    target_y: float,
    viewport_width: int,
    viewport_height: int,
    *,
    button: str = "left",
    click_count: int = 1,
) -> tuple[float, float]:
    """Perform a more human-like click sequence instead of a single instant click."""
    target_x, target_y = _clamp_point(target_x, target_y, viewport_width, viewport_height)

    last_x = session.get("mouse_x")
    last_y = session.get("mouse_y")
    if isinstance(last_x, (int, float)) and isinstance(last_y, (int, float)):
        start_x, start_y = _clamp_point(float(last_x), float(last_y), viewport_width, viewport_height)
    else:
        start_x, start_y = _clamp_point(
            viewport_width * random.uniform(0.22, 0.78),
            viewport_height * random.uniform(0.20, 0.80),
            viewport_width,
            viewport_height,
        )

    # Anchor pointer start, then move in a bent path.
    page.mouse.move(start_x, start_y)
    time.sleep(random.uniform(0.015, 0.060))

    mid_x, mid_y = _clamp_point(
        (start_x + target_x) / 2.0 + random.uniform(-42.0, 42.0),
        (start_y + target_y) / 2.0 + random.uniform(-28.0, 28.0),
        viewport_width,
        viewport_height,
    )
    page.mouse.move(mid_x, mid_y, steps=random.randint(6, 14))
    time.sleep(random.uniform(0.020, 0.090))
    page.mouse.move(target_x, target_y, steps=random.randint(10, 22))

    # Small jitter before click to reduce robotic feel.
    if random.random() < 0.75:
        jx, jy = _clamp_point(
            target_x + random.uniform(-2.2, 2.2),
            target_y + random.uniform(-1.8, 1.8),
            viewport_width,
            viewport_height,
        )
        page.mouse.move(jx, jy, steps=random.randint(2, 5))
        time.sleep(random.uniform(0.008, 0.030))
        page.mouse.move(target_x, target_y, steps=random.randint(2, 4))

    safe_button = str(button or "left").strip().lower()
    if safe_button not in {"left", "right", "middle"}:
        safe_button = "left"
    safe_click_count = max(1, min(int(click_count or 1), 3))

    # Press and release with short variable hold.
    for idx in range(safe_click_count):
        page.mouse.down(button=safe_button)
        time.sleep(random.uniform(0.035, 0.130))
        page.mouse.up(button=safe_button)
        if idx + 1 < safe_click_count:
            time.sleep(random.uniform(0.045, 0.150))

    session["mouse_x"] = target_x
    session["mouse_y"] = target_y
    return target_x, target_y


def _normalize_playwright_key(key: str) -> str:
    raw = "" if key is None else str(key)
    if raw == " ":
        return "Space"
    trimmed = raw.strip()
    if not trimmed:
        return ""
    aliases = {
        "esc": "Escape",
        "escape": "Escape",
        "return": "Enter",
        "spacebar": "Space",
        "space": "Space",
        "del": "Delete",
        "ins": "Insert",
        "left": "ArrowLeft",
        "right": "ArrowRight",
        "up": "ArrowUp",
        "down": "ArrowDown",
        "pageup": "PageUp",
        "pagedown": "PageDown",
        "ctrl+a": "Control+A",
    }
    lower = trimmed.lower()
    if lower in aliases:
        return aliases[lower]
    return trimmed


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

    # Local X11 display like ":99" should map to /tmp/.X11-unix/X99.
    if display.startswith(":"):
        m = re.match(r"^:([0-9]+)", display)
        if m:
            return os.path.exists(f"/tmp/.X11-unix/X{m.group(1)}")

    # For remote display values (host:display), we cannot verify cheaply.
    return True


def _resolve_playwright_headless() -> bool:
    """Resolve headless mode from env and display availability.

    Env:
    - BROWSER_HEADLESS / PLAYWRIGHT_HEADLESS:
      - true/1/on/headless -> force headless
      - false/0/off/headed -> force headed (falls back if no display)
      - auto/default/empty -> headed when display exists, otherwise headless
    """
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
    # auto/default
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


def _load_playwright_sync_api():
    """Load Playwright sync API."""
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except Exception as e:
        raise RuntimeError(
            "browser_agent requires playwright sync API."
        ) from e


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
    global _browser_runtime

    headless = _resolve_playwright_headless()
    launch_kwargs = _build_chromium_launch_kwargs(headless)
    try:
        browser = pw.chromium.launch(**launch_kwargs)
        _browser_runtime = {
            "engine": "chromium",
            "headless": headless,
            "executable": launch_kwargs.get("executable_path") or "bundled",
        }
        logger.info(
            "BrowserAgent worker started with Chromium (headless=%s, executable=%s)",
            headless,
            _browser_runtime.get("executable"),
        )
        return browser
    except Exception as e:
        # Guard against stale/broken DISPLAY in container envs.
        if not headless and _is_display_launch_error(e):
            logger.warning(
                "Headed launch failed due display environment, retrying headless fallback."
            )
            launch_kwargs = _build_chromium_launch_kwargs(True)
            browser = pw.chromium.launch(**launch_kwargs)
            _browser_runtime = {
                "engine": "chromium",
                "headless": True,
                "executable": launch_kwargs.get("executable_path") or "bundled",
            }
            logger.info(
                "BrowserAgent worker started with Chromium (headless=%s, executable=%s, fallback=true)",
                True,
                _browser_runtime.get("executable"),
            )
            return browser
        raise


def _build_viewer_url(token: str) -> str:
    base = (WEB_BASE_URL or "").strip().rstrip("/")
    if not base:
        return f"/browser-view/{token}"
    return f"{base}/browser-view/{token}"


def _normalize_viewer_token(token: str) -> str:
    value = str(token or "").strip()
    if not (16 <= len(value) <= 200):
        return ""
    if any(ch not in _VIEWER_TOKEN_CHARS for ch in value):
        return ""
    return value


def _cleanup_expired_viewer_links_locked(now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [
        token
        for token, meta in _viewer_links.items()
        if current - float(meta.get("last_access", current)) > VIEWER_LINK_TTL_SECONDS
    ]
    for token in expired:
        _viewer_links.pop(token, None)


def _create_viewer_link(session_id: str, user_id: int) -> tuple[str, str]:
    with _viewer_lock:
        _cleanup_expired_viewer_links_locked()
        while True:
            token = secrets.token_urlsafe(18)
            if token not in _viewer_links:
                break
        _viewer_links[token] = {
            "session_id": session_id,
            "user_id": int(user_id),
            "created_at": time.time(),
            "last_access": time.time(),
        }
    return token, _build_viewer_url(token)


def _get_or_create_viewer_link(session_id: str, user_id: int) -> tuple[str, str]:
    with _viewer_lock:
        _cleanup_expired_viewer_links_locked()
        newest_token = None
        newest_access = -1.0
        for token, meta in _viewer_links.items():
            if meta.get("session_id") != session_id:
                continue
            if int(meta.get("user_id", -1)) != int(user_id):
                continue
            last_access = float(meta.get("last_access", 0.0))
            if last_access > newest_access:
                newest_token = token
                newest_access = last_access

        if newest_token:
            _viewer_links[newest_token]["last_access"] = time.time()
            return newest_token, _build_viewer_url(newest_token)

    return _create_viewer_link(session_id, user_id)


def _viewer_payload(session_id: str, user_id: int) -> dict:
    viewer_token, viewer_url = _get_or_create_viewer_link(session_id, user_id)
    return {
        "viewer_token": viewer_token,
        "viewer_url": viewer_url,
    }


def _remove_viewer_token(token: str) -> None:
    normalized = _normalize_viewer_token(token)
    if not normalized:
        return
    with _viewer_lock:
        _viewer_links.pop(normalized, None)


def _remove_viewer_links_for_session(session_id: str) -> None:
    with _viewer_lock:
        to_delete = [
            token
            for token, meta in _viewer_links.items()
            if meta.get("session_id") == session_id
        ]
        for token in to_delete:
            _viewer_links.pop(token, None)


def _get_viewer_link(token: str) -> dict | None:
    normalized = _normalize_viewer_token(token)
    if not normalized:
        return None
    with _viewer_lock:
        _cleanup_expired_viewer_links_locked()
        meta = _viewer_links.get(normalized)
        if not meta:
            return None
        meta["last_access"] = time.time()
        result = dict(meta)
    result["token"] = normalized
    return result


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


def _format_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _cleanup_idle_sessions() -> None:
    now = time.time()
    expired = [
        sid
        for sid, session in _sessions.items()
        if now - float(session.get("last_active", now)) > SESSION_IDLE_TTL_SECONDS
    ]
    for sid in expired:
        _close_session_internal(sid)
    with _viewer_lock:
        _cleanup_expired_viewer_links_locked(now)


def _close_session_internal(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    _remove_viewer_links_for_session(session_id)
    if not session:
        return
    context = session.get("context")
    page = session.get("page")
    try:
        if page:
            page.close()
    except Exception:
        pass
    try:
        if context:
            context.close()
    except Exception:
        pass


def _ensure_session_limits_for_user(user_id: int) -> None:
    user_sessions = [
        (sid, session)
        for sid, session in _sessions.items()
        if int(session.get("user_id", -1)) == user_id
    ]
    if len(user_sessions) < MAX_SESSIONS_PER_USER:
        return

    user_sessions.sort(key=lambda item: float(item[1].get("last_active", 0)))
    overflow = len(user_sessions) - MAX_SESSIONS_PER_USER + 1
    for sid, _ in user_sessions[:overflow]:
        _close_session_internal(sid)


def _ensure_total_session_limit() -> None:
    if len(_sessions) < MAX_SESSIONS_TOTAL:
        return
    ordered = sorted(_sessions.items(), key=lambda item: float(item[1].get("last_active", 0)))
    overflow = len(_sessions) - MAX_SESSIONS_TOTAL + 1
    for sid, _ in ordered[:overflow]:
        _close_session_internal(sid)


def _latest_session_id_for_user(user_id: int) -> str | None:
    latest_sid = None
    latest_active = -1.0
    for sid, session in _sessions.items():
        if int(session.get("user_id", -1)) != user_id:
            continue
        last_active = float(session.get("last_active", 0.0))
        if last_active > latest_active:
            latest_sid = sid
            latest_active = last_active
    return latest_sid


def _resolve_session_id_for_user(user_id: int, session_id: str | None) -> str:
    requested = (session_id or "").strip()
    if requested:
        return requested
    latest_sid = _latest_session_id_for_user(user_id)
    if latest_sid:
        return latest_sid
    raise ValueError("No active browser session found. Start one with browser_start_session.")


def _get_session_for_user(session_id: str, user_id: int) -> dict:
    session = _sessions.get(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")
    if int(session.get("user_id", -1)) != user_id:
        raise ValueError("Session does not belong to current user")
    session["last_active"] = time.time()
    return session


def _extract_storage_state(payload) -> dict | None:
    if isinstance(payload, dict) and isinstance(payload.get("storage_state"), dict):
        return payload["storage_state"]
    if isinstance(payload, dict) and isinstance(payload.get("cookies"), list):
        # Backward compatibility for raw Playwright storage_state payloads.
        return payload
    return None


def _load_storage_state_for_user(user_id: int) -> tuple[dict | None, bool]:
    store = get_hf_dataset_store()
    if not store.enabled:
        return None, False
    payload = store.get_json(_HF_STATE_PATH.format(user_id=user_id))
    state = _extract_storage_state(payload)
    if not state:
        return None, False
    return state, True


def _persist_storage_state_for_session(user_id: int, session_id: str, reason: str) -> None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    try:
        session = _get_session_for_user(session_id, user_id)
        context = session.get("context")
        page = session.get("page")
        if context is None:
            return

        state = context.storage_state()
        payload = {
            "version": 1,
            "updated_at": int(time.time()),
            "reason": reason,
            "session_id": session_id,
            "url": page.url if page else "",
            "storage_state": state,
        }
        store.put_json(
            _HF_STATE_PATH.format(user_id=user_id),
            payload,
            commit_message=f"browser storage_state user={user_id}",
        )
    except Exception as e:
        logger.warning(
            "Failed to persist browser storage_state (user=%d session=%s reason=%s): %s",
            user_id,
            session_id,
            reason,
            e,
        )


def _new_context(browser, storage_state: dict | None = None, *, seed_hint: str | None = None):
    profile = pick_browser_profile(seed_hint=seed_hint)
    context = browser.new_context(
        **build_context_kwargs(profile, storage_state=storage_state, viewport_override={"width": 1366, "height": 768}),
    )
    apply_context_realism(context, profile)
    return context


def _snapshot_page(page, *, max_elements: int, max_text_length: int) -> dict:
    data = page.evaluate(
        """
        ([maxElements, maxTextLength]) => {
          const clean = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
          const esc = (v) => {
            if (!v) return '';
            if (window.CSS && CSS.escape) return CSS.escape(v);
            return String(v).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
          };
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          };

          const selector = 'a,button,input,textarea,select,[role="button"],[role="link"],[onclick],[tabindex]';
          const elements = [];
          for (const el of document.querySelectorAll(selector)) {
            if (!isVisible(el)) continue;
            const tag = (el.tagName || '').toLowerCase();
            const id = el.id || '';
            const name = el.getAttribute('name') || '';
            const type = el.getAttribute('type') || '';
            const role = el.getAttribute('role') || '';
            const href = el.getAttribute('href') || '';
            const placeholder = el.getAttribute('placeholder') || '';
            const cls = clean(el.className || '');
            const text = clean(
              el.innerText ||
              el.textContent ||
              el.getAttribute('aria-label') ||
              el.getAttribute('title') ||
              placeholder
            ).slice(0, 160);

            let hint = tag || 'element';
            if (id) hint = `#${esc(id)}`;
            else if (name && ['input', 'textarea', 'select'].includes(tag)) {
              hint = `${tag}[name="${String(name).replace(/"/g, '\\"')}"]`;
            } else if (tag && cls) {
              const topClasses = cls.split(' ').filter(Boolean).slice(0, 2).map(esc).join('.');
              if (topClasses) hint = `${tag}.${topClasses}`;
            }

            elements.push({
              tag,
              id,
              name,
              type,
              role,
              text,
              placeholder,
              href,
              hint,
            });
            if (elements.length >= maxElements) break;
          }

          const bodyText = clean(document.body ? document.body.innerText : '').slice(0, maxTextLength);
          const iframes = [];
          for (const frame of document.querySelectorAll('iframe')) {
            if (!isVisible(frame)) continue;
            const id = frame.id || '';
            const name = frame.getAttribute('name') || '';
            const title = frame.getAttribute('title') || '';
            const src = frame.getAttribute('src') || '';
            const cls = clean(frame.className || '');
            let hint = 'iframe';
            if (id) hint = `iframe#${esc(id)}`;
            else if (name) hint = `iframe[name="${String(name).replace(/"/g, '\\"')}"]`;
            else if (cls) {
              const topClasses = cls.split(' ').filter(Boolean).slice(0, 2).map(esc).join('.');
              if (topClasses) hint = `iframe.${topClasses}`;
            } else if (title) {
              hint = 'iframe[title]';
            }

            iframes.push({
              id,
              name,
              title,
              src,
              hint,
            });
            if (iframes.length >= 20) break;
          }

          return {
            url: location.href,
            title: document.title || '',
            body_text: bodyText,
            elements,
            iframes,
          };
        }
        """,
        [max_elements, max_text_length],
    )

    return {
        "url": str(data.get("url", "")),
        "title": str(data.get("title", "")),
        "body_text": str(data.get("body_text", "")),
        "elements": data.get("elements", []),
        "iframes": data.get("iframes", []),
    }


def _is_cf_challenge(page) -> bool:
    """Return True when current page looks like a Cloudflare challenge page."""
    try:
        title = (page.title() or "").lower()
        cf_titles = ["just a moment", "attention required", "please wait", "请稍候"]
        if any(t in title for t in cf_titles):
            return True

        marker = page.query_selector(
            "#challenge-running, #challenge-stage, .cf-turnstile, "
            "#cf-challenge-running, iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']"
        )
        if marker:
            return True
    except Exception:
        pass
    return False


def _browser_worker() -> None:
    sync_playwright = _load_playwright_sync_api()
    pw = sync_playwright().start()
    browser = _launch_browser_with_fallback(pw)

    while True:
        item = _work_queue.get()
        if item is None:
            break
        func, args, result_q = item
        try:
            _cleanup_idle_sessions()
            result = func(browser, *args)
            result_q.put(("ok", result))
        except Exception as e:
            result_q.put(("error", e))

    for sid in list(_sessions.keys()):
        _close_session_internal(sid)
    browser.close()
    pw.stop()


def _ensure_worker() -> None:
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_browser_worker, daemon=True)
        _worker_thread.start()


def _run_on_worker(func, *args):
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
                    "Browser worker crashed or exited. "
                    "Check Playwright dependencies and display environment."
                )


def prewarm_browser_agent_worker() -> tuple[bool, str]:
    """Start BrowserAgent worker/browser early so session startup is warm."""

    def _noop(browser):
        _ = browser
        return True

    try:
        _run_on_worker(_noop)
        engine = str(_browser_runtime.get("engine") or "chromium")
        headless = _browser_runtime.get("headless")
        executable = str(_browser_runtime.get("executable") or "bundled")
        return True, f"engine={engine} headless={headless} executable={executable}"
    except Exception as e:
        logger.exception("browser_agent prewarm failed: %s", e)
        return False, str(e)


# ── Worker operations ──


def _op_start_session(
    browser,
    user_id: int,
    start_url: str | None,
    wait_seconds: float,
    wait_until: str,
    force_new: bool,
) -> str:
    if not force_new:
        existing_sid = _latest_session_id_for_user(user_id)
        if existing_sid:
            session = _get_session_for_user(existing_sid, user_id)
            page = session["page"]
            if start_url:
                page.goto(start_url, timeout=PAGE_TIMEOUT_MS, wait_until=wait_until)
                humanize_page_presence(page)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
            cf_active = _is_cf_challenge(page)
            cf_message = (
                "Cloudflare challenge detected. Manual click/wait may be required."
                if cf_active else None
            )
            viewer_token, viewer_url = _get_or_create_viewer_link(existing_sid, user_id)
            return _format_json(
                {
                    "ok": True,
                    "action": "browser_start_session",
                    "session_id": existing_sid,
                    "url": page.url,
                    "title": page.title(),
                    "started_with_url": bool(start_url),
                    "reused_existing": True,
                    "viewer_token": viewer_token,
                    "viewer_url": viewer_url,
                    "browser_engine": _browser_runtime.get("engine"),
                    "challenge_active": cf_active,
                    "challenge_message": cf_message,
                    "note": "Reused existing active browser session for this user. Return viewer_url to user immediately.",
                }
            )

    _ensure_total_session_limit()
    _ensure_session_limits_for_user(user_id)

    storage_state, restored_from_hf = _load_storage_state_for_user(user_id)
    session_id = f"bs_{user_id}_{secrets.token_hex(4)}"
    context = _new_context(browser, storage_state=storage_state, seed_hint=session_id)
    page = context.new_page()

    try:
        if start_url:
            page.goto(start_url, timeout=PAGE_TIMEOUT_MS, wait_until=wait_until)
            humanize_page_presence(page)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
        cf_active = _is_cf_challenge(page)
        cf_message = (
            "Cloudflare challenge detected. Manual click/wait may be required."
            if cf_active else None
        )

        _sessions[session_id] = {
            "user_id": user_id,
            "context": context,
            "page": page,
            "engine": _browser_runtime.get("engine"),
            "created_at": time.time(),
            "last_active": time.time(),
        }
        _persist_storage_state_for_session(user_id, session_id, reason="start_session")
        viewer_token, viewer_url = _get_or_create_viewer_link(session_id, user_id)
        payload = {
            "ok": True,
            "action": "browser_start_session",
            "session_id": session_id,
            "url": page.url,
            "title": page.title(),
            "started_with_url": bool(start_url),
            "reused_existing": False,
            "viewer_token": viewer_token,
            "viewer_url": viewer_url,
            "browser_engine": _browser_runtime.get("engine"),
            "restored_storage_state": restored_from_hf,
            "challenge_active": cf_active,
            "challenge_message": cf_message,
            "note": "Always return viewer_url to user. Use browser_get_state to inspect page and next actions.",
        }
        return _format_json(payload)
    except Exception:
        try:
            page.close()
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass
        raise


def _op_list_sessions(browser, user_id: int) -> str:
    _ = browser  # keep signature aligned
    now = time.time()
    items = []
    for sid, session in _sessions.items():
        if int(session.get("user_id", -1)) != user_id:
            continue
        page = session.get("page")
        viewer = _viewer_payload(sid, user_id)
        items.append(
            {
                "session_id": sid,
                "url": page.url if page else "",
                "title": page.title() if page else "",
                "engine": str(session.get("engine") or _browser_runtime.get("engine") or ""),
                "idle_seconds": int(now - float(session.get("last_active", now))),
                "age_seconds": int(now - float(session.get("created_at", now))),
                **viewer,
            }
        )
    payload = {
        "ok": True,
        "action": "browser_list_sessions",
        "count": len(items),
        "sessions": sorted(items, key=lambda x: x["age_seconds"], reverse=True),
    }
    return _format_json(payload)


def _op_get_view_url(browser, user_id: int, session_id: str) -> str:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session.get("page")
    viewer = _viewer_payload(session_id, user_id)
    return _format_json(
        {
            "ok": True,
            "action": "browser_get_view_url",
            "session_id": session_id,
            "url": page.url if page else "",
            "title": page.title() if page else "",
            **viewer,
        }
    )


def _op_close_session(browser, user_id: int, session_id: str) -> str:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    _ = session
    try:
        _persist_storage_state_for_session(user_id, session_id, reason="close_session")
    except Exception as e:
        logger.warning("Failed to persist browser state before close (user=%d session=%s): %s", user_id, session_id, e)
    _close_session_internal(session_id)
    return _format_json(
        {
            "ok": True,
            "action": "browser_close_session",
            "session_id": session_id,
        }
    )


def _op_goto(
    browser,
    user_id: int,
    session_id: str,
    url: str,
    wait_seconds: float,
    wait_until: str,
) -> str:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewer = _viewer_payload(session_id, user_id)
    page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until=wait_until)
    humanize_page_presence(page)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    cf_active = _is_cf_challenge(page)
    cf_message = (
        "Cloudflare challenge detected. Manual click/wait may be required."
        if cf_active else None
    )
    _persist_storage_state_for_session(user_id, session_id, reason="goto")
    return _format_json(
        {
            "ok": True,
            "action": "browser_goto",
            "session_id": session_id,
            "url": page.url,
            "title": page.title(),
            "challenge_active": cf_active,
            "challenge_message": cf_message,
            **viewer,
        }
    )


def _op_click(
    browser,
    user_id: int,
    session_id: str,
    frame_selector: str,
    selector: str,
    text: str,
    index: int,
    timeout_ms: int,
    wait_seconds: float,
    button: str,
    click_count: int,
    human_like: bool,
    focus_after_click: bool,
) -> str:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewer = _viewer_payload(session_id, user_id)
    click_strategy = "direct"
    focused_editable = False

    target_index = max(index, 0)
    safe_button = str(button or "left").strip().lower()
    if safe_button not in {"left", "right", "middle"}:
        safe_button = "left"
    safe_click_count = max(1, min(int(click_count or 1), 3))
    use_human_like = bool(human_like)

    def _focus_editable(locator) -> bool:
        try:
            return bool(
                locator.evaluate(
                    """
                    (el) => {
                      if (!el) return false;
                      const tag = (el.tagName || '').toLowerCase();
                      const isEditable = (
                        el.isContentEditable === true ||
                        tag === 'textarea' ||
                        (tag === 'input' && String(el.type || '').toLowerCase() !== 'hidden')
                      );
                      if (!isEditable) return false;
                      el.focus();
                      if (typeof el.setSelectionRange === 'function' && typeof el.value === 'string') {
                        const n = el.value.length;
                        el.setSelectionRange(n, n);
                      }
                      return true;
                    }
                    """
                )
            )
        except Exception:
            return False

    def _click_locator(locator) -> tuple[str, bool]:
        # Prefer human-like click when possible (actual mouse trajectory + press/release).
        if use_human_like:
            try:
                locator.wait_for(state="visible", timeout=timeout_ms)
                box = locator.bounding_box()
                viewport = page.viewport_size or {"width": 1366, "height": 768}
                viewport_width = int(viewport.get("width") or 1366)
                viewport_height = int(viewport.get("height") or 768)
                if box and box.get("width", 0) > 1 and box.get("height", 0) > 1:
                    jitter_x = random.uniform(box["width"] * 0.18, box["width"] * 0.82)
                    jitter_y = random.uniform(box["height"] * 0.24, box["height"] * 0.76)
                    target_x = box["x"] + jitter_x
                    target_y = box["y"] + jitter_y
                    _humanized_mouse_click(
                        page,
                        session,
                        target_x,
                        target_y,
                        viewport_width,
                        viewport_height,
                        button=safe_button,
                        click_count=safe_click_count,
                    )
                    return "humanized", _focus_editable(locator) if focus_after_click else False
            except Exception:
                pass
        try:
            locator.click(
                timeout=timeout_ms,
                button=safe_button,
                click_count=safe_click_count,
            )
            return "direct", _focus_editable(locator) if focus_after_click else False
        except Exception as first_exc:
            first_msg = str(first_exc).lower()
            retryable = (
                "intercepts pointer events" in first_msg
                or "timeout" in first_msg
                or "not receiving pointer events" in first_msg
                or "element is outside of the viewport" in first_msg
            )
            if not retryable:
                raise
            try:
                locator.click(
                    timeout=timeout_ms,
                    force=True,
                    button=safe_button,
                    click_count=safe_click_count,
                )
                return "force", _focus_editable(locator) if focus_after_click else False
            except Exception as second_exc:
                if safe_button != "left" or safe_click_count != 1:
                    raise second_exc
                try:
                    locator.evaluate(
                        """
                        (el) => {
                          el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
                          if (typeof el.click === 'function') {
                            el.click();
                            return;
                          }
                          el.dispatchEvent(new MouseEvent('click', {
                            view: window,
                            bubbles: true,
                            cancelable: true
                          }));
                        }
                        """
                    )
                    return "dom", _focus_editable(locator) if focus_after_click else False
                except Exception:
                    raise second_exc

    if frame_selector:
        frame_selector = frame_selector.strip()
        if selector and text:
            locator = page.frame_locator(frame_selector).locator(selector).filter(has_text=text)
            locator = locator.nth(target_index)
            click_strategy, focused_editable = _click_locator(locator)
        elif selector:
            locator = page.frame_locator(frame_selector).locator(selector).nth(target_index)
            click_strategy, focused_editable = _click_locator(locator)
        elif text:
            locator = page.frame_locator(frame_selector).locator(f"text={text}").nth(target_index)
            click_strategy, focused_editable = _click_locator(locator)
        else:
            # Fallback: click iframe center (useful for CF/Turnstile-like widgets).
            frame_el = page.locator(frame_selector).nth(target_index)
            frame_el.wait_for(state="visible", timeout=timeout_ms)
            box = frame_el.bounding_box()
            if not box:
                raise ValueError("Frame is not visible/clickable")
            viewport = page.viewport_size or {"width": 1366, "height": 768}
            _humanized_mouse_click(
                page,
                session,
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2,
                int(viewport.get("width") or 1366),
                int(viewport.get("height") or 768),
                button=safe_button,
                click_count=safe_click_count,
            )
            click_strategy = "frame-center"
    else:
        if selector and text:
            locator = page.locator(selector).filter(has_text=text)
        elif selector:
            locator = page.locator(selector)
        elif text:
            locator = page.get_by_text(text, exact=False)
        else:
            raise ValueError("Provide selector or text for browser_click")

        locator = locator.nth(target_index)
        click_strategy, focused_editable = _click_locator(locator)

    if wait_seconds > 0:
        time.sleep(wait_seconds)
    cf_active = _is_cf_challenge(page)
    cf_message = (
        "Cloudflare challenge detected. Manual click/wait may be required."
        if cf_active else None
    )
    _persist_storage_state_for_session(user_id, session_id, reason="click")

    return _format_json(
        {
            "ok": True,
            "action": "browser_click",
            "session_id": session_id,
            "frame_selector": frame_selector or None,
            "selector": selector or None,
            "text": text or None,
            "index": target_index,
            "click_strategy": click_strategy,
            "button": safe_button,
            "click_count": safe_click_count,
            "human_like": use_human_like,
            "focused_editable": focused_editable,
            "url": page.url,
            "title": page.title(),
            "challenge_active": cf_active,
            "challenge_message": cf_message,
            **viewer,
        }
    )


def _op_type(
    browser,
    user_id: int,
    session_id: str,
    selector: str,
    text: str,
    clear: bool,
    press_enter: bool,
    timeout_ms: int,
    delay_ms: int,
    click_first: bool,
    human_like: bool,
    wait_seconds: float,
) -> str:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewer = _viewer_payload(session_id, user_id)

    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=timeout_ms)
    if click_first:
        try:
            locator.click(timeout=timeout_ms)
        except Exception:
            locator.focus(timeout=timeout_ms)
    else:
        locator.focus(timeout=timeout_ms)

    if clear:
        cleared = False
        try:
            locator.press("Control+A", timeout=timeout_ms)
            locator.press("Backspace", timeout=timeout_ms)
            cleared = True
        except Exception:
            pass
        if not cleared:
            locator.fill("", timeout=timeout_ms)

    effective_delay = max(0, int(delay_ms))
    type_mode = "fill"
    if human_like and effective_delay <= 0:
        effective_delay = random.randint(28, 76)

    if effective_delay > 0:
        page.keyboard.type(text, delay=effective_delay)
        type_mode = "keyboard"
    else:
        locator.fill(text, timeout=timeout_ms)
        type_mode = "fill"

    if press_enter:
        page.keyboard.press("Enter")
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    _persist_storage_state_for_session(user_id, session_id, reason="type")

    return _format_json(
        {
            "ok": True,
            "action": "browser_type",
            "session_id": session_id,
            "selector": selector,
            "typed_chars": len(text),
            "pressed_enter": press_enter,
            "click_first": bool(click_first),
            "human_like": bool(human_like),
            "type_mode": type_mode,
            "delay_ms": effective_delay,
            "url": page.url,
            "title": page.title(),
            **viewer,
        }
    )


def _op_press(
    browser,
    user_id: int,
    session_id: str,
    key: str,
    timeout_ms: int,
) -> str:
    _ = browser
    _ = timeout_ms
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewer = _viewer_payload(session_id, user_id)
    normalized_key = _normalize_playwright_key(key)
    page.keyboard.press(normalized_key)
    _persist_storage_state_for_session(user_id, session_id, reason="press")
    return _format_json(
        {
            "ok": True,
            "action": "browser_press",
            "session_id": session_id,
            "key": normalized_key,
            "url": page.url,
            "title": page.title(),
            **viewer,
        }
    )


def _op_wait_for(
    browser,
    user_id: int,
    session_id: str,
    selector: str,
    state: str,
    timeout_ms: int,
    wait_ms: int,
) -> str:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewer = _viewer_payload(session_id, user_id)

    if selector:
        page.locator(selector).first.wait_for(state=state, timeout=timeout_ms)
    if wait_ms > 0:
        time.sleep(min(wait_ms, 120_000) / 1000.0)
    _persist_storage_state_for_session(user_id, session_id, reason="wait_for")

    return _format_json(
        {
            "ok": True,
            "action": "browser_wait_for",
            "session_id": session_id,
            "selector": selector or None,
            "state": state if selector else None,
            "wait_ms": wait_ms,
            "url": page.url,
            "title": page.title(),
            **viewer,
        }
    )


def _op_get_state(
    browser,
    user_id: int,
    session_id: str,
    max_elements: int,
    max_text_length: int,
) -> str:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewer = _viewer_payload(session_id, user_id)
    snapshot = _snapshot_page(page, max_elements=max_elements, max_text_length=max_text_length)
    cf_active = _is_cf_challenge(page)
    payload = {
        "ok": True,
        "action": "browser_get_state",
        "session_id": session_id,
        "url": snapshot["url"],
        "title": snapshot["title"],
        "body_text": snapshot["body_text"],
        "elements": snapshot["elements"],
        "iframes": snapshot["iframes"],
        "challenge_active": cf_active,
        "challenge_hint": "Cloudflare/Turnstile verification may require waiting or iframe center-click."
        if cf_active else None,
        **viewer,
    }
    return _format_json(payload)


def _op_get_live_view_state(browser, user_id: int, session_id: str) -> dict:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewport = page.viewport_size or {"width": 1366, "height": 768}
    return {
        "ok": True,
        "session_id": session_id,
        "url": page.url,
        "title": page.title(),
        "viewport": {
            "width": int(viewport.get("width") or 1366),
            "height": int(viewport.get("height") or 768),
        },
        "challenge_active": _is_cf_challenge(page),
        "captured_at": int(time.time()),
    }


def _op_get_live_view_frame(
    browser,
    user_id: int,
    session_id: str,
    quality: int = 72,
) -> dict:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    safe_quality = max(30, min(int(quality), 90))
    image = page.screenshot(
        type="jpeg",
        quality=safe_quality,
        animations="disabled",
    )
    return {
        "ok": True,
        "session_id": session_id,
        "url": page.url,
        "title": page.title(),
        "captured_at": int(time.time()),
        "image": image,
    }


def _op_live_view_click(
    browser,
    user_id: int,
    session_id: str,
    x: float | None,
    y: float | None,
    rx: float | None,
    ry: float | None,
    wait_ms: int,
    button: str,
    click_count: int,
) -> dict:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]
    viewport = page.viewport_size or {"width": 1366, "height": 768}
    viewport_width = int(viewport.get("width") or 1366)
    viewport_height = int(viewport.get("height") or 768)

    mode = "absolute"
    if rx is not None and ry is not None:
        safe_rx = max(0.0, min(float(rx), 1.0))
        safe_ry = max(0.0, min(float(ry), 1.0))
        safe_x = max(1.0, min(safe_rx * viewport_width, max(1.0, viewport_width - 1.0)))
        safe_y = max(1.0, min(safe_ry * viewport_height, max(1.0, viewport_height - 1.0)))
        mode = "ratio"
    else:
        safe_x = max(1.0, min(float(x or 1.0), max(1.0, viewport_width - 1.0)))
        safe_y = max(1.0, min(float(y or 1.0), max(1.0, viewport_height - 1.0)))
    safe_button = str(button or "left").strip().lower()
    if safe_button not in {"left", "right", "middle"}:
        safe_button = "left"
    safe_click_count = max(1, min(int(click_count or 1), 3))
    safe_x, safe_y = _humanized_mouse_click(
        page,
        session,
        safe_x,
        safe_y,
        viewport_width,
        viewport_height,
        button=safe_button,
        click_count=safe_click_count,
    )

    if wait_ms > 0:
        time.sleep(min(max(wait_ms, 0), 120_000) / 1000.0)

    cf_active = _is_cf_challenge(page)
    cf_message = (
        "Cloudflare challenge detected. Manual click/wait may be required."
        if cf_active else None
    )
    _persist_storage_state_for_session(user_id, session_id, reason="viewer_click")
    return {
        "ok": True,
        "action": "browser_view_click",
        "input_mode": mode,
        "stealth_click": True,
        "session_id": session_id,
        "button": safe_button,
        "click_count": safe_click_count,
        "x": round(safe_x, 2),
        "y": round(safe_y, 2),
        "viewport": {
            "width": viewport_width,
            "height": viewport_height,
        },
        "url": page.url,
        "title": page.title(),
        "challenge_active": cf_active,
        "challenge_message": cf_message,
        "captured_at": int(time.time()),
    }


def _op_live_view_input(
    browser,
    user_id: int,
    session_id: str,
    text: str,
    key: str,
    clear: bool,
    press_enter: bool,
    wait_ms: int,
    delay_ms: int,
) -> dict:
    _ = browser
    session = _get_session_for_user(session_id, user_id)
    page = session["page"]

    typed_text = str(text or "")
    normalized_key = _normalize_playwright_key(key)
    safe_wait_ms = max(0, min(int(wait_ms or 0), 120_000))
    safe_delay_ms = max(0, min(int(delay_ms or 0), 260))
    input_mode = "none"

    if clear:
        try:
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
        except Exception:
            pass

    if typed_text:
        if safe_delay_ms > 0:
            page.keyboard.type(typed_text, delay=safe_delay_ms)
            input_mode = "keyboard"
        else:
            page.keyboard.insert_text(typed_text)
            input_mode = "insert_text"

    if normalized_key:
        page.keyboard.press(normalized_key)
        input_mode = "key" if input_mode == "none" else f"{input_mode}+key"

    if press_enter:
        page.keyboard.press("Enter")
        input_mode = "enter" if input_mode == "none" else f"{input_mode}+enter"

    if safe_wait_ms > 0:
        time.sleep(safe_wait_ms / 1000.0)

    cf_active = _is_cf_challenge(page)
    cf_message = (
        "Cloudflare challenge detected. Manual click/wait may be required."
        if cf_active else None
    )
    _persist_storage_state_for_session(user_id, session_id, reason="viewer_input")
    return {
        "ok": True,
        "action": "browser_view_input",
        "session_id": session_id,
        "typed_chars": len(typed_text),
        "key": normalized_key or None,
        "clear": bool(clear),
        "pressed_enter": bool(press_enter),
        "input_mode": input_mode,
        "delay_ms": safe_delay_ms,
        "url": page.url,
        "title": page.title(),
        "challenge_active": cf_active,
        "challenge_message": cf_message,
        "captured_at": int(time.time()),
    }


def get_browser_view_state_by_token(token: str) -> dict | None:
    """Resolve viewer token and return live page metadata."""
    meta = _get_viewer_link(token)
    if not meta:
        return None
    try:
        state = _run_on_worker(
            _op_get_live_view_state,
            int(meta["user_id"]),
            str(meta["session_id"]),
        )
    except Exception:
        _remove_viewer_token(str(meta.get("token", "")))
        return None
    state["viewer_url"] = _build_viewer_url(str(meta["token"]))
    state["refresh_ms"] = VIEWER_REFRESH_HINT_MS
    return state


def get_browser_view_frame_by_token(token: str, *, quality: int = 72) -> dict | None:
    """Resolve viewer token and capture a live viewport frame."""
    meta = _get_viewer_link(token)
    if not meta:
        return None
    try:
        safe_quality = max(30, min(int(quality), 90))
        return _run_on_worker(
            _op_get_live_view_frame,
            int(meta["user_id"]),
            str(meta["session_id"]),
            safe_quality,
        )
    except Exception:
        _remove_viewer_token(str(meta.get("token", "")))
        return None


def click_browser_view_by_token(
    token: str,
    *,
    x: float | None = None,
    y: float | None = None,
    rx: float | None = None,
    ry: float | None = None,
    wait_ms: int = 1200,
    button: str = "left",
    click_count: int = 1,
) -> dict | None:
    """Resolve viewer token and dispatch a click into the live browser session."""
    meta = _get_viewer_link(token)
    if not meta:
        return None

    safe_wait_ms = max(0, min(int(wait_ms), 120_000))
    safe_button = str(button or "left").strip().lower()
    if safe_button not in {"left", "right", "middle"}:
        safe_button = "left"
    safe_click_count = max(1, min(int(click_count or 1), 3))
    try:
        safe_x = None if x is None else float(x)
        safe_y = None if y is None else float(y)
        safe_rx = None if rx is None else float(rx)
        safe_ry = None if ry is None else float(ry)
        return _run_on_worker(
            _op_live_view_click,
            int(meta["user_id"]),
            str(meta["session_id"]),
            safe_x,
            safe_y,
            safe_rx,
            safe_ry,
            safe_wait_ms,
            safe_button,
            safe_click_count,
        )
    except Exception:
        _remove_viewer_token(str(meta.get("token", "")))
        return None


def input_browser_view_by_token(
    token: str,
    *,
    text: str = "",
    key: str = "",
    clear: bool = False,
    press_enter: bool = False,
    wait_ms: int = 0,
    delay_ms: int = 0,
) -> dict | None:
    """Resolve viewer token and dispatch keyboard input into the live browser session."""
    meta = _get_viewer_link(token)
    if not meta:
        return None
    try:
        safe_wait_ms = max(0, min(int(wait_ms), 120_000))
        safe_delay_ms = max(0, min(int(delay_ms), 260))
        return _run_on_worker(
            _op_live_view_input,
            int(meta["user_id"]),
            str(meta["session_id"]),
            str(text or ""),
            str(key or ""),
            bool(clear),
            bool(press_enter),
            safe_wait_ms,
            safe_delay_ms,
        )
    except Exception:
        _remove_viewer_token(str(meta.get("token", "")))
        return None


# ── Tool definitions ──

BROWSER_START_SESSION_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_start_session",
        "description": (
            "Start or reuse a persistent browser session for step-by-step web operations. "
            "By default reuses latest active session for the user; set force_new=true to always create one. "
            "Returns session_id and a viewer_url for live read-only viewing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_url": {
                    "type": "string",
                    "description": "Optional URL to open immediately.",
                },
                "wait": {
                    "type": "number",
                    "default": DEFAULT_WAIT_SECONDS,
                    "description": "Extra seconds to wait after initial navigation.",
                },
                "wait_until": {
                    "type": "string",
                    "enum": ["domcontentloaded", "load", "networkidle", "commit"],
                    "default": DEFAULT_WAIT_UNTIL,
                    "description": "Navigation completion event.",
                },
                "force_new": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, always create a brand-new session instead of reusing existing one.",
                },
            },
        },
    },
}

BROWSER_LIST_SESSIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_list_sessions",
        "description": "List active browser sessions for the current user.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

BROWSER_GET_VIEW_URL_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_get_view_url",
        "description": (
            "Get viewer_url for an existing browser session. "
            "If session_id is omitted, uses latest active session for current user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. If omitted, uses the latest active session for current user.",
                }
            },
            "required": [],
        },
    },
}

BROWSER_CLOSE_SESSION_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_close_session",
        "description": "Close a browser session and free resources.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID returned by browser_start_session.",
                }
            },
            "required": ["session_id"],
        },
    },
}

BROWSER_GOTO_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_goto",
        "description": "Navigate the existing browser session to a URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. If omitted, uses the latest active session for current user.",
                },
                "url": {
                    "type": "string",
                    "description": "Target URL (http/https).",
                },
                "wait": {
                    "type": "number",
                    "default": DEFAULT_WAIT_SECONDS,
                    "description": "Extra seconds to wait after navigation.",
                },
                "wait_until": {
                    "type": "string",
                    "enum": ["domcontentloaded", "load", "networkidle", "commit"],
                    "default": DEFAULT_WAIT_UNTIL,
                    "description": "Navigation completion event.",
                },
            },
            "required": ["url"],
        },
    },
}

BROWSER_CLICK_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_click",
        "description": (
            "Click an element in the current page. "
            "Prefer selector; text matching is also supported."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. If omitted, uses the latest active session for current user.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector to locate the target element.",
                },
                "frame_selector": {
                    "type": "string",
                    "description": (
                        "Optional iframe CSS selector. "
                        "If set, click is executed inside that iframe. "
                        "If selector/text are empty, click iframe center."
                    ),
                },
                "text": {
                    "type": "string",
                    "description": "Optional text lookup for click target.",
                },
                "index": {
                    "type": "integer",
                    "default": 0,
                    "description": "Nth matched element to click (0-based).",
                },
                "timeout_ms": {
                    "type": "integer",
                    "default": DEFAULT_ACTION_TIMEOUT_MS,
                    "description": "Action timeout in milliseconds.",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "default": "left",
                    "description": "Mouse button to click.",
                },
                "click_count": {
                    "type": "integer",
                    "default": 1,
                    "description": "Number of clicks (1=single, 2=double).",
                },
                "human_like": {
                    "type": "boolean",
                    "default": True,
                    "description": "Use human-like mouse movement and click timing.",
                },
                "focus_after_click": {
                    "type": "boolean",
                    "default": True,
                    "description": "After click, focus editable target when possible.",
                },
                "wait": {
                    "type": "number",
                    "default": DEFAULT_WAIT_SECONDS,
                    "description": "Extra seconds to wait after click.",
                },
            },
            "required": [],
        },
    },
}

BROWSER_TYPE_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_type",
        "description": "Type text into an input element.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. If omitted, uses the latest active session for current user.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for input element.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to input.",
                },
                "clear": {
                    "type": "boolean",
                    "default": True,
                    "description": "Clear existing content before typing.",
                },
                "click_first": {
                    "type": "boolean",
                    "default": True,
                    "description": "Click/focus target input before typing.",
                },
                "human_like": {
                    "type": "boolean",
                    "default": True,
                    "description": "Prefer keyboard typing (with delay) instead of direct fill.",
                },
                "press_enter": {
                    "type": "boolean",
                    "default": False,
                    "description": "Press Enter after typing.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "default": DEFAULT_ACTION_TIMEOUT_MS,
                    "description": "Action timeout in milliseconds.",
                },
                "delay_ms": {
                    "type": "integer",
                    "default": 0,
                    "description": "Per-character typing delay; 0 means use fill().",
                },
                "wait": {
                    "type": "number",
                    "default": DEFAULT_WAIT_SECONDS,
                    "description": "Extra seconds to wait after typing.",
                },
            },
            "required": ["selector", "text"],
        },
    },
}

BROWSER_PRESS_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_press",
        "description": "Press a keyboard key in the current page (e.g., Enter, Tab, Escape).",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. If omitted, uses the latest active session for current user.",
                },
                "key": {
                    "type": "string",
                    "description": "Playwright key name.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "default": DEFAULT_ACTION_TIMEOUT_MS,
                    "description": "Action timeout in milliseconds.",
                },
            },
            "required": ["key"],
        },
    },
}

BROWSER_WAIT_FOR_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_wait_for",
        "description": (
            "Wait for page conditions. "
            "Use selector+state for element wait, or wait_ms for a simple delay."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. If omitted, uses the latest active session for current user.",
                },
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to wait for.",
                },
                "state": {
                    "type": "string",
                    "enum": ["visible", "attached", "hidden", "detached"],
                    "default": "visible",
                    "description": "Desired selector state.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "default": DEFAULT_ACTION_TIMEOUT_MS,
                    "description": "Wait timeout in milliseconds for selector mode.",
                },
                "wait_ms": {
                    "type": "integer",
                    "default": 0,
                    "description": "Optional fixed sleep in milliseconds.",
                },
            },
            "required": [],
        },
    },
}

BROWSER_GET_STATE_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_get_state",
        "description": "Get page snapshot: URL/title/visible text, interactive elements, and visible iframes.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. If omitted, uses the latest active session for current user.",
                },
                "max_elements": {
                    "type": "integer",
                    "default": 40,
                    "description": "Maximum interactive elements to return.",
                },
                "max_text_length": {
                    "type": "integer",
                    "default": 3000,
                    "description": "Maximum body_text characters to return.",
                },
            },
            "required": [],
        },
    },
}


class BrowserAgentTool(BaseTool):
    @property
    def name(self) -> str:
        return "browser_agent"

    def definitions(self) -> list[dict]:
        return [
            BROWSER_START_SESSION_TOOL,
            BROWSER_LIST_SESSIONS_TOOL,
            BROWSER_GET_VIEW_URL_TOOL,
            BROWSER_CLOSE_SESSION_TOOL,
            BROWSER_GOTO_TOOL,
            BROWSER_CLICK_TOOL,
            BROWSER_TYPE_TOOL,
            BROWSER_PRESS_TOOL,
            BROWSER_WAIT_FOR_TOOL,
            BROWSER_GET_STATE_TOOL,
        ]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name == "browser_start_session":
            return self._start_session(user_id, arguments)
        if tool_name == "browser_list_sessions":
            return self._list_sessions(user_id)
        if tool_name == "browser_get_view_url":
            return self._get_view_url(user_id, arguments)
        if tool_name == "browser_close_session":
            return self._close_session(user_id, arguments)
        if tool_name == "browser_goto":
            return self._goto(user_id, arguments)
        if tool_name == "browser_click":
            return self._click(user_id, arguments)
        if tool_name == "browser_type":
            return self._type(user_id, arguments)
        if tool_name == "browser_press":
            return self._press(user_id, arguments)
        if tool_name == "browser_wait_for":
            return self._wait_for(user_id, arguments)
        if tool_name == "browser_get_state":
            return self._get_state(user_id, arguments)
        return f"Unknown browser agent tool: {tool_name}"

    @staticmethod
    def _int_arg(value, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _float_arg(value, default: float, minimum: float, maximum: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
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

    def _start_session(self, user_id: int, arguments: dict) -> str:
        start_url = (arguments.get("start_url") or "").strip()
        force_new = self._bool_arg(arguments.get("force_new"), False)
        wait_seconds = self._float_arg(
            arguments.get("wait"),
            DEFAULT_WAIT_SECONDS,
            0,
            MAX_WAIT_SECONDS,
        )
        wait_until = str(arguments.get("wait_until") or DEFAULT_WAIT_UNTIL).strip().lower()
        if wait_until not in ALLOWED_WAIT_UNTIL:
            wait_until = DEFAULT_WAIT_UNTIL

        if start_url:
            try:
                start_url = _validate_url(start_url)
            except ValueError as e:
                return f"URL rejected: {e}"
        else:
            start_url = None

        try:
            return _run_on_worker(
                _op_start_session,
                user_id,
                start_url,
                wait_seconds,
                wait_until,
                force_new,
            )
        except Exception as e:
            logger.exception("browser_start_session failed for user=%d", user_id)
            return f"browser_start_session failed: {e}"

    def _list_sessions(self, user_id: int) -> str:
        try:
            return _run_on_worker(_op_list_sessions, user_id)
        except Exception as e:
            logger.exception("browser_list_sessions failed for user=%d", user_id)
            return f"browser_list_sessions failed: {e}"

    def _get_view_url(self, user_id: int, arguments: dict) -> str:
        requested_session_id = (arguments.get("session_id") or "").strip()
        try:
            session_id = _resolve_session_id_for_user(user_id, requested_session_id)
        except ValueError as e:
            return str(e)
        try:
            return _run_on_worker(_op_get_view_url, user_id, session_id)
        except Exception as e:
            logger.exception("browser_get_view_url failed for user=%d session=%s", user_id, session_id)
            return f"browser_get_view_url failed: {e}"

    def _close_session(self, user_id: int, arguments: dict) -> str:
        session_id = (arguments.get("session_id") or "").strip()
        if not session_id:
            return "No session_id provided."
        try:
            return _run_on_worker(_op_close_session, user_id, session_id)
        except Exception as e:
            logger.exception("browser_close_session failed for user=%d session=%s", user_id, session_id)
            return f"browser_close_session failed: {e}"

    def _goto(self, user_id: int, arguments: dict) -> str:
        requested_session_id = (arguments.get("session_id") or "").strip()
        raw_url = (arguments.get("url") or "").strip()
        if not raw_url:
            return "No URL provided."
        try:
            session_id = _resolve_session_id_for_user(user_id, requested_session_id)
        except ValueError as e:
            return str(e)

        try:
            url = _validate_url(raw_url)
        except ValueError as e:
            return f"URL rejected: {e}"

        wait_seconds = self._float_arg(
            arguments.get("wait"),
            DEFAULT_WAIT_SECONDS,
            0,
            MAX_WAIT_SECONDS,
        )
        wait_until = str(arguments.get("wait_until") or DEFAULT_WAIT_UNTIL).strip().lower()
        if wait_until not in ALLOWED_WAIT_UNTIL:
            wait_until = DEFAULT_WAIT_UNTIL

        try:
            return _run_on_worker(_op_goto, user_id, session_id, url, wait_seconds, wait_until)
        except Exception as e:
            logger.exception("browser_goto failed for user=%d session=%s url=%s", user_id, session_id, url)
            return f"browser_goto failed: {e}"

    def _click(self, user_id: int, arguments: dict) -> str:
        requested_session_id = (arguments.get("session_id") or "").strip()
        frame_selector = (arguments.get("frame_selector") or "").strip()
        selector = (arguments.get("selector") or "").strip()
        text = (arguments.get("text") or "").strip()
        if not frame_selector and not selector and not text:
            return "Provide selector or text. For iframe center-click, set frame_selector."
        try:
            session_id = _resolve_session_id_for_user(user_id, requested_session_id)
        except ValueError as e:
            return str(e)

        index = self._int_arg(arguments.get("index"), 0, 0, 100)
        timeout_ms = self._int_arg(
            arguments.get("timeout_ms"),
            DEFAULT_ACTION_TIMEOUT_MS,
            1000,
            MAX_ACTION_TIMEOUT_MS,
        )
        button = str(arguments.get("button") or "left").strip().lower()
        if button not in {"left", "right", "middle"}:
            button = "left"
        click_count = self._int_arg(arguments.get("click_count"), 1, 1, 3)
        human_like = self._bool_arg(arguments.get("human_like"), True)
        focus_after_click = self._bool_arg(arguments.get("focus_after_click"), True)
        wait_seconds = self._float_arg(arguments.get("wait"), DEFAULT_WAIT_SECONDS, 0, MAX_WAIT_SECONDS)
        try:
            return _run_on_worker(
                _op_click,
                user_id,
                session_id,
                frame_selector,
                selector,
                text,
                index,
                timeout_ms,
                wait_seconds,
                button,
                click_count,
                human_like,
                focus_after_click,
            )
        except Exception as e:
            logger.exception("browser_click failed for user=%d session=%s", user_id, session_id)
            return f"browser_click failed: {e}"

    def _type(self, user_id: int, arguments: dict) -> str:
        requested_session_id = (arguments.get("session_id") or "").strip()
        selector = (arguments.get("selector") or "").strip()
        text = str(arguments.get("text") or "")
        if not selector:
            return "No selector provided."
        try:
            session_id = _resolve_session_id_for_user(user_id, requested_session_id)
        except ValueError as e:
            return str(e)

        clear = self._bool_arg(arguments.get("clear"), True)
        click_first = self._bool_arg(arguments.get("click_first"), True)
        human_like = self._bool_arg(arguments.get("human_like"), True)
        press_enter = self._bool_arg(arguments.get("press_enter"), False)
        timeout_ms = self._int_arg(
            arguments.get("timeout_ms"),
            DEFAULT_ACTION_TIMEOUT_MS,
            1000,
            MAX_ACTION_TIMEOUT_MS,
        )
        delay_ms = self._int_arg(arguments.get("delay_ms"), 0, 0, 1000)
        wait_seconds = self._float_arg(arguments.get("wait"), DEFAULT_WAIT_SECONDS, 0, MAX_WAIT_SECONDS)
        try:
            return _run_on_worker(
                _op_type,
                user_id,
                session_id,
                selector,
                text,
                clear,
                press_enter,
                timeout_ms,
                delay_ms,
                click_first,
                human_like,
                wait_seconds,
            )
        except Exception as e:
            logger.exception("browser_type failed for user=%d session=%s", user_id, session_id)
            return f"browser_type failed: {e}"

    def _press(self, user_id: int, arguments: dict) -> str:
        requested_session_id = (arguments.get("session_id") or "").strip()
        key = (arguments.get("key") or "").strip()
        if not key:
            return "No key provided."
        try:
            session_id = _resolve_session_id_for_user(user_id, requested_session_id)
        except ValueError as e:
            return str(e)

        timeout_ms = self._int_arg(
            arguments.get("timeout_ms"),
            DEFAULT_ACTION_TIMEOUT_MS,
            1000,
            MAX_ACTION_TIMEOUT_MS,
        )
        try:
            return _run_on_worker(_op_press, user_id, session_id, key, timeout_ms)
        except Exception as e:
            logger.exception("browser_press failed for user=%d session=%s", user_id, session_id)
            return f"browser_press failed: {e}"

    def _wait_for(self, user_id: int, arguments: dict) -> str:
        requested_session_id = (arguments.get("session_id") or "").strip()
        selector = (arguments.get("selector") or "").strip()
        try:
            session_id = _resolve_session_id_for_user(user_id, requested_session_id)
        except ValueError as e:
            return str(e)

        state = str(arguments.get("state") or "visible").strip().lower()
        if state not in ALLOWED_WAIT_STATES:
            state = "visible"

        timeout_ms = self._int_arg(
            arguments.get("timeout_ms"),
            DEFAULT_ACTION_TIMEOUT_MS,
            1000,
            MAX_ACTION_TIMEOUT_MS,
        )
        wait_ms = self._int_arg(arguments.get("wait_ms"), 0, 0, 120_000)

        if not selector and wait_ms <= 0:
            return "Provide selector or wait_ms."

        try:
            return _run_on_worker(
                _op_wait_for,
                user_id,
                session_id,
                selector,
                state,
                timeout_ms,
                wait_ms,
            )
        except Exception as e:
            logger.exception("browser_wait_for failed for user=%d session=%s", user_id, session_id)
            return f"browser_wait_for failed: {e}"

    def _get_state(self, user_id: int, arguments: dict) -> str:
        requested_session_id = (arguments.get("session_id") or "").strip()
        try:
            session_id = _resolve_session_id_for_user(user_id, requested_session_id)
        except ValueError as e:
            return str(e)

        max_elements = self._int_arg(arguments.get("max_elements"), 40, 5, 120)
        max_text_length = self._int_arg(arguments.get("max_text_length"), 3000, 300, 10_000)
        try:
            return _run_on_worker(
                _op_get_state,
                user_id,
                session_id,
                max_elements,
                max_text_length,
            )
        except Exception as e:
            logger.exception("browser_get_state failed for user=%d session=%s", user_id, session_id)
            return f"browser_get_state failed: {e}"

    def get_instruction(self) -> str:
        return (
            "\n\nYou have stateful browser_agent tools for step-by-step web automation.\n"
            "- Start with browser_start_session; it reuses an active session by default.\n"
            "- After a session starts, prefer continuing directly; session_id can be omitted and latest active session is auto-used.\n"
            "- With HF_DATASET_USERNAME/HF_DATASET_TOKEN/HF_DATASET_NAME set, login state is restored via storage_state.\n"
            "- Always return viewer_url to the user whenever browser_start_session/browser_get_view_url returns it.\n"
            "- If user asks to watch current browser, call browser_get_view_url (do not start a new session unless user asked for force_new).\n"
            "- Set force_new=true only when you explicitly need a new isolated session.\n"
            "- browser_start_session returns viewer_url so users can watch live browser actions.\n"
            "- Use browser_goto / browser_click / browser_type / browser_press / browser_wait_for in sequence.\n"
            "- For forms, prefer browser_click on input then browser_type with click_first=true and human_like=true.\n"
            "- Call browser_get_state after important actions to inspect current page state.\n"
            "- Runtime uses Playwright Chromium (prefers local executable path when available).\n"
            "- Cloudflare challenge is only detected, not auto-passed; use viewer control click or manual waits.\n"
            "- Prefer selector-based actions; use text-based click only when selector is unavailable.\n"
            "- Close sessions with browser_close_session when task is done.\n"
        )
