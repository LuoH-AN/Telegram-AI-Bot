"""Fetch and parse operations for scrapling integration."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from .constants import ALLOWED_MODES, DEFAULT_TIMEOUT_SECONDS, MAX_OUTPUT_CHARS
from .runtime import detect_capabilities


def fetch_url(
    *,
    url: str,
    mode: str = "auto",
    selector: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    cookies=None,
    user_agent: str = "",
) -> dict:
    clean_url = str(url or "").strip()
    if not clean_url:
        return {"ok": False, "message": "url is required"}
    clean_mode = str(mode or "auto").strip().lower()
    if clean_mode not in ALLOWED_MODES:
        clean_mode = "auto"
    caps = detect_capabilities()

    if caps.get("fetcher_available"):
        result = _fetch_with_scrapling(
            url=clean_url,
            mode=clean_mode,
            selector=selector,
            timeout_seconds=timeout_seconds,
            cookies=cookies,
        )
        if result.get("ok"):
            return result
        if clean_mode == "auto":
            # If auto failed in basic attempt, try stealth once.
            retry = _fetch_with_scrapling(
                url=clean_url,
                mode="stealth",
                selector=selector,
                timeout_seconds=max(timeout_seconds, 45),
                cookies=cookies,
            )
            if retry.get("ok"):
                retry["fallback_from"] = result.get("mode_used") or "basic"
                return retry

    return _fetch_with_requests(
        url=clean_url,
        selector=selector,
        timeout_seconds=timeout_seconds,
        user_agent=user_agent,
    )


def parse_html(*, html: str, selector: str = "", base_url: str = "") -> dict:
    text = str(html or "")
    if not text:
        return {"ok": False, "message": "html is required"}
    selector_text = str(selector or "").strip()
    caps = detect_capabilities()
    if caps.get("parser_available"):
        try:
            from scrapling.parser import Selector
        except Exception as exc:
            return {"ok": False, "message": f"failed to import scrapling parser: {exc}"}
        try:
            page = Selector(text, url=base_url or "https://localhost")
            output = _extract_payload(page=page, selector=selector_text)
            output.update(
                {
                    "ok": True,
                    "mode_used": "selector",
                    "base_url": base_url or None,
                    "html_length": len(text),
                }
            )
            return output
        except Exception as exc:
            return {"ok": False, "message": f"selector parse failed: {exc}"}

    return {
        "ok": False,
        "message": "scrapling parser unavailable. Run action=install first.",
    }


def parse_cookies_argument(cookies):
    if cookies is None:
        return None
    if isinstance(cookies, (dict, list)):
        return cookies
    raw = str(cookies).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def normalize_site_key(site: str) -> str:
    raw = str(site or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.netloc.lower()
    return raw


def _fetch_with_scrapling(*, url: str, mode: str, selector: str, timeout_seconds: int, cookies) -> dict:
    mode_used = mode if mode != "auto" else "basic"
    selector_text = str(selector or "").strip()
    try:
        from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher
    except Exception as exc:
        return {"ok": False, "message": f"failed to import scrapling fetchers: {exc}", "mode_used": mode_used}

    try:
        if mode_used == "basic":
            page = Fetcher.get(url, impersonate="chrome", timeout=max(3, min(180, int(timeout_seconds))), cookies=_cookies_as_dict(cookies))
        elif mode_used == "stealth":
            page = StealthyFetcher.fetch(
                url,
                headless=True,
                solve_cloudflare=True,
                cookies=_cookies_as_browser_list(cookies),
                timeout=max(60000, min(300000, int(timeout_seconds) * 1000)),
                network_idle=True,
            )
        else:
            page = DynamicFetcher.fetch(
                url,
                headless=True,
                cookies=_cookies_as_browser_list(cookies),
                timeout=max(30000, min(300000, int(timeout_seconds) * 1000)),
                network_idle=True,
                disable_resources=True,
            )
    except Exception as exc:
        return {"ok": False, "message": f"scrapling fetch failed: {exc}", "mode_used": mode_used}

    payload = _extract_payload(page=page, selector=selector_text)
    payload.update(
        {
            "ok": True,
            "url": str(getattr(page, "url", "") or url),
            "status": int(getattr(page, "status", 0) or 0),
            "mode_used": mode_used,
        }
    )
    if _looks_like_challenge(payload.get("text_excerpt", "")) and mode_used == "basic":
        payload["warning"] = "possible anti-bot challenge detected; try mode=stealth"
    return payload


def _fetch_with_requests(*, url: str, selector: str, timeout_seconds: int, user_agent: str) -> dict:
    try:
        import requests
    except Exception as exc:
        return {"ok": False, "message": f"requests unavailable: {exc}"}

    headers = {
        "User-Agent": user_agent.strip() or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    warning = None
    try:
        resp = requests.get(url, timeout=max(3, min(180, int(timeout_seconds))), headers=headers)
    except requests.exceptions.SSLError:
        # Some runtime images miss CA bundles; retry once with verify disabled.
        try:
            resp = requests.get(
                url,
                timeout=max(3, min(180, int(timeout_seconds))),
                headers=headers,
                verify=False,
            )
            warning = "TLS certificate verification failed; used insecure retry (verify=false)."
        except Exception as exc:
            return {"ok": False, "message": f"http request failed: {exc}"}
    except Exception as exc:
        return {"ok": False, "message": f"http request failed: {exc}"}

    html = resp.text or ""
    text_out = ""
    try:
        import trafilatura

        extracted = trafilatura.extract(html, include_links=True, include_tables=False)
        text_out = str(extracted or "").strip()
    except Exception:
        text_out = ""
    if not text_out:
        text_out = _naive_text(html)

    payload = {
        "ok": True,
        "url": str(resp.url or url),
        "status": int(resp.status_code),
        "mode_used": "requests_fallback",
        "title": _extract_title(html),
        "selector": str(selector or "").strip() or None,
        "selected": [],
        "text_excerpt": _trim(text_out, MAX_OUTPUT_CHARS),
        "links": _extract_links(html, max_links=20),
    }
    if selector:
        payload["warning"] = "selector extraction requires scrapling parser; using fallback text extraction."
    if warning:
        payload["warning"] = warning if "warning" not in payload else f"{payload['warning']} {warning}"
    return payload


def _extract_payload(*, page, selector: str) -> dict:
    title = ""
    try:
        title = str((page.css("title::text").get() or "")).strip()
    except Exception:
        title = ""

    selected: list[str] = []
    if selector:
        try:
            selected = [str(item).strip() for item in (page.css(selector).getall() or []) if str(item).strip()]
        except Exception:
            selected = []

    text_out = ""
    try:
        text_out = str(page.get_all_text(strip=True) or "").strip()
    except Exception:
        try:
            text_out = str(getattr(page, "text", "") or "").strip()
        except Exception:
            text_out = ""

    links = []
    try:
        links = [str(v).strip() for v in (page.css("a::attr(href)").getall() or []) if str(v).strip()][:20]
    except Exception:
        links = []

    return {
        "title": title or None,
        "selector": selector or None,
        "selected": selected[:80],
        "text_excerpt": _trim(text_out, MAX_OUTPUT_CHARS),
        "links": links,
    }


def _cookies_as_dict(cookies):
    if isinstance(cookies, dict):
        return {str(k): str(v) for k, v in cookies.items()}
    if isinstance(cookies, list):
        result = {}
        for item in cookies:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            result[name] = str(item.get("value") or "")
        return result or None
    return None


def _cookies_as_browser_list(cookies):
    if isinstance(cookies, list):
        rows = []
        for item in cookies:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            value = str(item.get("value") or "")
            domain = str(item.get("domain") or "").strip()
            path = str(item.get("path") or "/").strip() or "/"
            if not name:
                continue
            row = {"name": name, "value": value}
            if domain:
                row["domain"] = domain
                row["path"] = path
            rows.append(row)
        return rows or None
    if isinstance(cookies, dict):
        return [{"name": str(k), "value": str(v)} for k, v in cookies.items()]
    return None


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def _extract_links(html: str, *, max_links: int) -> list[str]:
    links = re.findall(r"""href=['"]([^'"]+)['"]""", html or "", flags=re.IGNORECASE)
    cleaned = []
    for item in links:
        value = str(item).strip()
        if not value:
            continue
        cleaned.append(value)
        if len(cleaned) >= max_links:
            break
    return cleaned


def _naive_text(html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _looks_like_challenge(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in ("just a moment", "checking your browser", "cloudflare"))


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
