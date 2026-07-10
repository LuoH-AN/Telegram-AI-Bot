"""Opt-in network integration check for the requested Chinese query."""

from __future__ import annotations

import os

import pytest


@pytest.mark.live
def test_live_exa_search_for_requested_query():
    if os.getenv("RUN_LIVE_SEARCH_TESTS") != "1":
        pytest.skip("set RUN_LIVE_SEARCH_TESTS=1 to run Exa integration tests")
    from infrastructure.config import load_env

    load_env()
    if not (os.getenv("EXA_API_KEYS") or os.getenv("EXA_API_KEY")):
        pytest.skip("Exa API key is not configured")

    from infrastructure.tools.builtin.search.exa import search_once

    result = search_once(query="落憾", top_k=5, timeout_seconds=30, exact_match=True)
    assert result["ok"] is True
    assert result["returned"] > 0
    assert any("落憾" in f"{item['title']} {item['snippet']} {item['content']}" for item in result["results"])
