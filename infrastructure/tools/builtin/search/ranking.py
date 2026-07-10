"""Normalization, deduplication, and lightweight relevance ranking."""

from __future__ import annotations

import re
import urllib.parse

_TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}


def _clean_text(value, limit: int) -> str:
    text = str(value or "").replace("\x00", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def _canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    query = []
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in _TRACKING_PARAMS:
            continue
        query.append((key, value))
    query.sort()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(query), ""))


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = {item for item in re.findall(r"[a-z0-9_]{2,}", lowered)}
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    terms.update(chinese[index:index + 2] for index in range(max(0, len(chinese) - 1)))
    return terms


def _relevance(query: str, item: dict) -> float:
    provider = max(0.0, min(1.0, float(item.get("_provider_score", 0.0))))
    query_terms = _terms(query)
    haystack = _terms(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('content', '')[:1000]}")
    lexical = len(query_terms & haystack) / len(query_terms) if query_terms else 0.0
    return round(provider * 0.8 + lexical * 0.2, 6)


def _joined_highlights(raw: dict) -> str:
    highlights = raw.get("highlights")
    if not isinstance(highlights, list):
        return ""
    return "\n".join(str(value).strip() for value in highlights if str(value).strip())


def normalize_and_rank(raw_results: list, *, query: str, top_k: int, content_limit: int) -> list[dict]:
    deduplicated: dict[str, dict] = {}
    total = max(1, len(raw_results))
    for position, raw in enumerate(raw_results, 1):
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        title = _clean_text(raw.get("title"), 300)
        if not url or not title:
            continue
        canonical = _canonical_url(url)
        if not canonical.startswith(("http://", "https://")):
            continue
        highlights = _joined_highlights(raw)
        text = _clean_text(raw.get("text"), content_limit)
        summary = _clean_text(raw.get("summary"), 800)
        snippet = _clean_text(highlights or summary or text, 500)
        content = text or _clean_text(highlights, content_limit)
        content_source = "exa_text" if text else ("exa_highlights" if content else "")
        provider_score = raw.get("score")
        try:
            normalized_provider_score = max(0.0, min(1.0, float(provider_score)))
        except (TypeError, ValueError):
            normalized_provider_score = 1.0 - ((position - 1) / total)
        parsed = urllib.parse.urlsplit(canonical)
        item = {
            "title": title,
            "url": canonical,
            "domain": parsed.hostname or "",
            "snippet": snippet,
            "content": content,
            "content_source": content_source,
            "published_date": _clean_text(raw.get("publishedDate") or raw.get("published_date"), 80),
            "author": _clean_text(raw.get("author"), 300),
            "engine": "exa",
            "provider_rank": position,
            "score": provider_score,
            "_provider_score": normalized_provider_score,
        }
        item["relevance_score"] = _relevance(query, item)
        previous = deduplicated.get(canonical)
        if previous is None or item["relevance_score"] > previous["relevance_score"]:
            deduplicated[canonical] = item

    ranked = sorted(deduplicated.values(), key=lambda item: item["relevance_score"], reverse=True)
    selected: list[dict] = []
    deferred: list[dict] = []
    domains: dict[str, int] = {}
    for item in ranked:
        domain = item["domain"]
        if domains.get(domain, 0) >= 2:
            deferred.append(item)
            continue
        selected.append(item)
        domains[domain] = domains.get(domain, 0) + 1
        if len(selected) >= top_k:
            break
    if len(selected) < top_k:
        selected.extend(deferred[:top_k - len(selected)])
    for index, item in enumerate(selected, 1):
        item.pop("_provider_score", None)
        item["source_id"] = index
        item["citation"] = f"[{index}]"
    return selected
