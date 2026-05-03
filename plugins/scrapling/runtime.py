"""Runtime capability detection for scrapling integration."""

from __future__ import annotations

import importlib


def detect_capabilities() -> dict:
    parser_ok = _module_exists("scrapling.parser")
    fetcher_ok = _module_exists("scrapling.fetchers")
    requests_ok = _module_exists("requests")
    trafilatura_ok = _module_exists("trafilatura")

    fetchers: list[str] = []
    if fetcher_ok:
        try:
            fetchers_mod = importlib.import_module("scrapling.fetchers")
            for name in ("Fetcher", "StealthyFetcher", "DynamicFetcher", "FetcherSession"):
                if hasattr(fetchers_mod, name):
                    fetchers.append(name)
        except Exception:
            pass

    version = None
    try:
        scrapling_mod = importlib.import_module("scrapling")
        version = str(getattr(scrapling_mod, "__version__", "") or "").strip() or None
    except Exception:
        version = None

    return {
        "scrapling_installed": bool(parser_ok or fetcher_ok),
        "scrapling_version": version,
        "parser_available": parser_ok,
        "fetcher_available": fetcher_ok,
        "fetchers": fetchers,
        "requests_available": requests_ok,
        "trafilatura_available": trafilatura_ok,
    }


def _module_exists(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False

