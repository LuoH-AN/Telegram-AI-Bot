"""Search request adapter for search service HTTP API."""

from __future__ import annotations

import requests


def search_once(*, query: str, port: int, timeout_seconds: int, top_k: int) -> dict:
    url = f"http://127.0.0.1:{port}/search"
    try:
        resp = requests.get(url, params={"q": query}, timeout=max(3, min(120, timeout_seconds)))
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        return {"ok": False, "query": query, "message": f"Search request failed: {exc}"}

    results = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(results, list):
        return {"ok": False, "query": query, "message": "Search response format invalid."}

    normalized = []
    for item in results[:top_k]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url_value = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        engine = str(item.get("engine") or "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        normalized.append(
            {
                "title": title,
                "url": url_value,
                "snippet": snippet,
                "engine": engine,
            }
        )
    return {"ok": True, "query": query, "count": len(results), "returned": len(normalized), "results": normalized}

