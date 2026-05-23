"""Tavily search client with key-pool rotation."""

from __future__ import annotations

import requests

from .constants import DEFAULT_SEARCH_DEPTH, TAVILY_ENDPOINT
from .keys import KEY_POOL


def _classify(status_code: int) -> str:
    if status_code in (401, 403):
        return "auth"
    if status_code == 429:
        return "rate_limit"
    return "network"


def _normalize(raw: dict, top_k: int) -> list[dict]:
    results = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(results, list):
        return []
    out = []
    for item in results[:top_k]:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("content") or "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        out.append({
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "snippet": snippet,
            "engine": "tavily",
            "score": item.get("score"),
        })
    return out


def search_once(*, query: str, top_k: int, timeout_seconds: int) -> dict:
    if not KEY_POOL.has_keys():
        return {"ok": False, "query": query, "message": "No Tavily API keys configured (set TAVILY_API_KEYS)."}

    timeout = max(3, min(120, int(timeout_seconds)))
    attempts: list[str] = []
    last_error = "all keys exhausted"

    for _ in range(max(1, KEY_POOL.snapshot()["configured"])):
        key = KEY_POOL.acquire()
        if key is None:
            break
        attempts.append(key[:6])
        try:
            resp = requests.post(
                TAVILY_ENDPOINT,
                json={
                    "query": query,
                    "max_results": top_k,
                    "search_depth": DEFAULT_SEARCH_DEPTH,
                },
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=timeout,
            )
        except Exception as exc:
            KEY_POOL.report_failure(key, "network", str(exc))
            last_error = f"network: {exc}"
            continue

        if resp.status_code >= 400:
            kind = _classify(resp.status_code)
            body_preview = (resp.text or "")[:200]
            KEY_POOL.report_failure(key, kind, f"HTTP {resp.status_code} {body_preview}")
            last_error = f"HTTP {resp.status_code}: {body_preview}"
            if kind == "rate_limit" or kind == "auth":
                continue
            break

        try:
            raw = resp.json()
        except Exception as exc:
            KEY_POOL.report_failure(key, "network", f"bad json: {exc}")
            last_error = f"bad json: {exc}"
            continue

        KEY_POOL.report_success(key)
        normalized = _normalize(raw, top_k)
        return {
            "ok": True,
            "query": query,
            "count": len(raw.get("results") or []) if isinstance(raw, dict) else 0,
            "returned": len(normalized),
            "results": normalized,
            "answer": raw.get("answer") if isinstance(raw, dict) else None,
        }

    return {"ok": False, "query": query, "message": f"Tavily request failed after {len(attempts)} key(s): {last_error}"}
