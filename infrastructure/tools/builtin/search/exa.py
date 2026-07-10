"""Exa search client with key rotation, caching, and evidence extraction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os

import requests

from .cache import SEARCH_CACHE
from .content import enrich_results
from .keypool import KEY_POOL, SEARCH_TYPES, default_search_type, exa_endpoint
from .ranking import normalize_and_rank

_CATEGORIES = {"company", "research paper", "news", "personal site", "financial report", "people"}
_TIME_DELTAS = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "year": timedelta(days=365),
}


def status_snapshot() -> dict:
    return {"keys": KEY_POOL.snapshot(), "cache": SEARCH_CACHE.snapshot()}


def _classify(status_code: int) -> str:
    if status_code in (401, 403):
        return "auth"
    if status_code == 429:
        return "rate_limit"
    return "network"


def _csv_values(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").replace(";", ",").split(",") if item.strip()][:100]


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "true" if default else "false").strip().lower()
    return value in {"1", "true", "on", "yes"}


def _published_after(time_range: str) -> str:
    delta = _TIME_DELTAS.get(time_range)
    if delta is None:
        return ""
    boundary = datetime.now(timezone.utc) - delta
    return boundary.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def _cache_key(payload: dict, *, exact_match: bool, content_top_k: int) -> str:
    return json.dumps(
        {**payload, "exact_match": exact_match, "content_top_k": content_top_k},
        ensure_ascii=False,
        sort_keys=True,
    )


def _exact_phrase(query: str) -> str:
    phrase = query.strip()
    quote_pairs = {'"': '"', "'": "'", "“": "”", "‘": "’"}
    if len(phrase) >= 2 and quote_pairs.get(phrase[0]) == phrase[-1]:
        phrase = phrase[1:-1].strip()
    return phrase.casefold()


def _contains_exact(item: dict, phrase: str) -> bool:
    evidence = f"{item.get('title', '')}\n{item.get('snippet', '')}\n{item.get('content', '')}".casefold()
    return bool(phrase and phrase in evidence)


def search_once(
    *,
    query: str,
    top_k: int,
    timeout_seconds: int,
    category: str = "",
    time_range: str = "",
    include_domains: str = "",
    exclude_domains: str = "",
    search_type: str = "auto",
    exact_match: bool = False,
    user_location: str = "",
    include_content: bool = True,
    content_top_k: int = 3,
) -> dict:
    key_status = KEY_POOL.snapshot()
    if not key_status["configured"]:
        return {"ok": False, "query": query, "message": "No Exa API keys configured (set EXA_API_KEYS)."}

    top_k = max(1, min(20, int(top_k)))
    timeout = max(3, min(120, int(timeout_seconds)))
    mode = default_search_type() if search_type == "auto" else search_type
    if mode not in SEARCH_TYPES:
        mode = default_search_type()
    category = category.strip().lower()
    if category not in _CATEGORIES:
        category = ""
    if time_range not in {"", *_TIME_DELTAS}:
        time_range = ""
    content_top_k = max(0, min(5, int(content_top_k))) if include_content else 0
    content_limit = max(250, min(2000, 8000 // max(1, top_k)))

    payload: dict = {
        "query": query,
        "numResults": top_k,
        "type": mode,
        "moderation": _bool_env("EXA_MODERATION", False),
    }
    if include_content:
        payload["contents"] = {"highlights": True}
    if category:
        payload["category"] = category
    included = _csv_values(include_domains)
    excluded = _csv_values(exclude_domains)
    if included:
        payload["includeDomains"] = included
    if excluded and category not in {"company", "people"}:
        payload["excludeDomains"] = excluded
    published_after = _published_after(time_range)
    if published_after and category not in {"company", "people"}:
        payload["startPublishedDate"] = published_after
    location = user_location.strip().upper()
    if len(location) == 2 and location.isalpha():
        payload["userLocation"] = location

    cache_key = _cache_key(payload, exact_match=exact_match, content_top_k=content_top_k)
    cached = SEARCH_CACHE.get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    attempts: list[str] = []
    last_error = "all keys exhausted"
    for _ in range(max(1, key_status["configured"])):
        key = KEY_POOL.acquire()
        if key is None:
            break
        attempts.append(key[:6])
        try:
            response = requests.post(
                exa_endpoint(),
                json=payload,
                headers={"x-api-key": key, "Content-Type": "application/json"},
                timeout=timeout,
            )
        except Exception as exc:
            KEY_POOL.report_failure(key, "network", str(exc))
            last_error = f"network: {exc}"
            continue
        if response.status_code >= 400:
            kind = _classify(response.status_code)
            preview = (response.text or "")[:300]
            KEY_POOL.report_failure(key, kind, f"HTTP {response.status_code} {preview}")
            last_error = f"HTTP {response.status_code}: {preview}"
            if kind in {"rate_limit", "auth"}:
                continue
            break
        try:
            raw = response.json()
        except Exception as exc:
            KEY_POOL.report_failure(key, "network", f"bad json: {exc}")
            last_error = f"bad json: {exc}"
            continue

        KEY_POOL.report_success(key)
        raw_results = raw.get("results") if isinstance(raw, dict) else []
        normalized = normalize_and_rank(
            raw_results if isinstance(raw_results, list) else [],
            query=query,
            top_k=top_k,
            content_limit=content_limit,
        )
        if exact_match:
            phrase = _exact_phrase(query)
            normalized = [item for item in normalized if _contains_exact(item, phrase)]
            for index, item in enumerate(normalized, 1):
                item["source_id"] = index
                item["citation"] = f"[{index}]"
        if include_content and content_top_k:
            enrich_results(
                normalized,
                top_n=content_top_k,
                timeout=min(12, timeout),
                content_limit=content_limit,
            )
        result = {
            "ok": True,
            "backend": "exa",
            "query": query,
            "search_type": mode,
            "category": category,
            "count": len(raw_results) if isinstance(raw_results, list) else 0,
            "returned": len(normalized),
            "cached": False,
            "results": normalized,
            "request_id": raw.get("requestId") if isinstance(raw, dict) else None,
            "cost_dollars": raw.get("costDollars") if isinstance(raw, dict) else None,
        }
        SEARCH_CACHE.set(cache_key, result)
        return result
    return {"ok": False, "query": query, "message": f"Exa request failed after {len(attempts)} key(s): {last_error}"}
