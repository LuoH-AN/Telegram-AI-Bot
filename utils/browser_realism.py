"""Shared browser realism helpers for Playwright-based tools."""

from __future__ import annotations

import hashlib
import json
import random
import time
from urllib.parse import urlparse

_DEFAULT_VIEWPORT = {"width": 1366, "height": 768}

_DESKTOP_PROFILES: tuple[dict[str, object], ...] = (
    {
        "name": "win10_chrome",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
        "language": "en-US",
        "languages": ["en-US", "en", "zh-CN", "zh"],
        "viewport": {"width": 1366, "height": 768},
        "device_scale_factor": 1,
        "color_scheme": "light",
    },
    {
        "name": "win11_chrome",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "language": "en-US",
        "languages": ["en-US", "en", "zh-CN", "zh"],
        "viewport": {"width": 1536, "height": 864},
        "device_scale_factor": 1,
        "color_scheme": "light",
    },
    {
        "name": "mac_chrome",
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),
        "platform": "MacIntel",
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
        "language": "en-US",
        "languages": ["en-US", "en", "zh-CN", "zh"],
        "viewport": {"width": 1440, "height": 900},
        "device_scale_factor": 2,
        "color_scheme": "light",
    },
)


def _seed_from_hint(seed_hint: str | None) -> int | None:
    hint = str(seed_hint or "").strip().lower()
    if not hint:
        return None

    if hint.startswith(("http://", "https://")):
        parsed = urlparse(hint)
        hint = (parsed.hostname or hint).strip().lower()

    digest = hashlib.sha256(hint.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def pick_browser_profile(seed_hint: str | None = None) -> dict[str, object]:
    """Pick a realistic desktop browser profile.

    If seed_hint is provided, profile selection is deterministic for stability.
    """
    seed = _seed_from_hint(seed_hint)
    if seed is None:
        selected = _DESKTOP_PROFILES[0]
    else:
        selected = random.Random(seed).choice(_DESKTOP_PROFILES)

    profile: dict[str, object] = {}
    for key, value in selected.items():
        if isinstance(value, dict):
            profile[key] = dict(value)
        elif isinstance(value, list):
            profile[key] = list(value)
        else:
            profile[key] = value
    return profile


def build_accept_language(profile: dict[str, object]) -> str:
    languages = profile.get("languages")
    if not isinstance(languages, list) or not languages:
        return "en-US,en;q=0.9"

    cleaned = [str(item).strip() for item in languages if str(item).strip()]
    if not cleaned:
        return "en-US,en;q=0.9"

    header_parts: list[str] = [cleaned[0]]
    q = 0.9
    for lang in cleaned[1:5]:
        header_parts.append(f"{lang};q={q:.1f}")
        q = max(0.5, q - 0.1)
    return ",".join(header_parts)


def build_extra_http_headers(profile: dict[str, object]) -> dict[str, str]:
    return {
        "Accept-Language": build_accept_language(profile),
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    }


def build_context_kwargs(
    profile: dict[str, object],
    *,
    storage_state: dict | None = None,
    viewport_override: dict[str, int] | None = None,
) -> dict[str, object]:
    viewport_data = profile.get("viewport")
    viewport = dict(_DEFAULT_VIEWPORT)
    if isinstance(viewport_data, dict):
        viewport["width"] = int(viewport_data.get("width") or viewport["width"])
        viewport["height"] = int(viewport_data.get("height") or viewport["height"])
    if viewport_override:
        viewport["width"] = int(viewport_override.get("width") or viewport["width"])
        viewport["height"] = int(viewport_override.get("height") or viewport["height"])

    kwargs: dict[str, object] = {
        "viewport": {"width": max(800, viewport["width"]), "height": max(600, viewport["height"])},
        "screen": {"width": max(800, viewport["width"]), "height": max(600, viewport["height"])},
        "device_scale_factor": float(profile.get("device_scale_factor") or 1),
        "is_mobile": False,
        "has_touch": False,
        "java_script_enabled": True,
        "locale": str(profile.get("locale") or "en-US"),
        "timezone_id": str(profile.get("timezone_id") or "America/Los_Angeles"),
        "color_scheme": str(profile.get("color_scheme") or "light"),
        "reduced_motion": "no-preference",
        "extra_http_headers": build_extra_http_headers(profile),
    }

    user_agent = str(profile.get("user_agent") or "").strip()
    if user_agent:
        kwargs["user_agent"] = user_agent

    if storage_state:
        kwargs["storage_state"] = storage_state

    return kwargs


def build_stealth_init_script(profile: dict[str, object]) -> str:
    platform = json.dumps(str(profile.get("platform") or "Win32"))
    language = json.dumps(str(profile.get("language") or "en-US"))
    languages = json.dumps(profile.get("languages") or ["en-US", "en"])

    return f"""
(() => {{
  const override = (obj, prop, value) => {{
    try {{
      Object.defineProperty(obj, prop, {{
        get: () => value,
        configurable: true
      }});
    }} catch (_err) {{
      // no-op
    }}
  }};

  override(Navigator.prototype, 'webdriver', undefined);
  override(Navigator.prototype, 'platform', {platform});
  override(Navigator.prototype, 'language', {language});
  override(Navigator.prototype, 'languages', {languages});
  override(Navigator.prototype, 'maxTouchPoints', 0);
  override(Navigator.prototype, 'hardwareConcurrency', 8);
  override(Navigator.prototype, 'deviceMemory', 8);

  const fakePlugins = [
    {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
    {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
    {{ name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }}
  ];
  override(Navigator.prototype, 'plugins', fakePlugins);
  override(Navigator.prototype, 'mimeTypes', [
    {{ type: 'application/pdf', suffixes: 'pdf', description: '' }},
    {{ type: 'text/pdf', suffixes: 'pdf', description: '' }},
  ]);

  try {{
    if (!window.chrome) {{
      window.chrome = {{ runtime: {{}}, app: {{ isInstalled: false }}, webstore: {{}} }};
    }} else if (!window.chrome.runtime) {{
      window.chrome.runtime = {{}};
    }}
  }} catch (_err) {{
    // no-op
  }}

  try {{
    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {{
      window.navigator.permissions.query = (params) =>
        params && params.name === 'notifications'
          ? Promise.resolve({{ state: Notification.permission }})
          : originalQuery(params);
    }}
  }} catch (_err) {{
    // no-op
  }}
}})();
"""


def apply_context_realism(context, profile: dict[str, object]) -> None:
    headers = build_extra_http_headers(profile)
    try:
        context.set_extra_http_headers(headers)
    except Exception:
        pass

    try:
        context.add_init_script(build_stealth_init_script(profile))
    except Exception:
        pass


def humanize_page_presence(page) -> None:
    """Perform lightweight user-like interactions after navigation."""
    try:
        viewport = page.viewport_size or _DEFAULT_VIEWPORT
        width = int(viewport.get("width") or _DEFAULT_VIEWPORT["width"])
        height = int(viewport.get("height") or _DEFAULT_VIEWPORT["height"])
        width = max(800, width)
        height = max(600, height)

        start_x = int(width * random.uniform(0.20, 0.38))
        start_y = int(height * random.uniform(0.18, 0.36))
        end_x = int(width * random.uniform(0.62, 0.84))
        end_y = int(height * random.uniform(0.42, 0.70))

        page.mouse.move(start_x, start_y)
        page.mouse.move(end_x, end_y, steps=random.randint(9, 18))
        time.sleep(random.uniform(0.04, 0.14))
    except Exception:
        pass

    try:
        page.evaluate(
            """
            () => {
              const root = document.scrollingElement || document.documentElement || document.body;
              if (!root) return;
              const maxY = Math.max(0, (root.scrollHeight || 0) - window.innerHeight);
              if (maxY <= 0) return;
              const down = Math.min(360, Math.max(120, Math.round(maxY * 0.18)));
              window.scrollBy({ top: down, left: 0, behavior: 'instant' });
            }
            """
        )
        time.sleep(random.uniform(0.07, 0.20))
        page.evaluate(
            """
            () => {
              window.scrollBy({ top: -120, left: 0, behavior: 'instant' });
            }
            """
        )
    except Exception:
        pass
