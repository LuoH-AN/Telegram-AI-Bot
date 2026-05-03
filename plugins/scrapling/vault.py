"""Cookie vault helpers for scrapling tool."""

from __future__ import annotations

import json
import time

from .constants import COOKIE_VAULT_FILE, RUNTIME_DIR


def list_sites() -> list[str]:
    data = _load_vault()
    return sorted(data.keys())


def get_site(site: str) -> dict | None:
    key = _site_key(site)
    if not key:
        return None
    data = _load_vault()
    item = data.get(key)
    return item if isinstance(item, dict) else None


def set_site(site: str, cookies, *, notes: str = "") -> dict:
    key = _site_key(site)
    if not key:
        raise ValueError("site is required")
    normalized = _normalize_cookies(cookies)
    data = _load_vault()
    data[key] = {
        "site": key,
        "updated_at": int(time.time()),
        "notes": str(notes or "").strip(),
        "cookies": normalized,
    }
    _save_vault(data)
    return data[key]


def delete_site(site: str) -> bool:
    key = _site_key(site)
    if not key:
        return False
    data = _load_vault()
    if key not in data:
        return False
    data.pop(key, None)
    _save_vault(data)
    return True


def _site_key(site: str) -> str:
    return str(site or "").strip().lower()


def _normalize_cookies(cookies):
    if isinstance(cookies, dict):
        return [{"name": str(k), "value": str(v)} for k, v in cookies.items()]
    if not isinstance(cookies, list):
        raise ValueError("cookies must be dict or list")
    normalized = []
    for item in cookies:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name:
            continue
        row = {"name": name, "value": value}
        for key in ("domain", "path", "expires", "httpOnly", "secure", "sameSite"):
            if key in item:
                row[key] = item[key]
        normalized.append(row)
    if not normalized:
        raise ValueError("no valid cookies")
    return normalized


def _load_vault() -> dict:
    if not COOKIE_VAULT_FILE.exists():
        return {}
    try:
        raw = json.loads(COOKIE_VAULT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_vault(data: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_VAULT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

