"""Tests for the model context-window table and resolver."""

from __future__ import annotations

from infrastructure.ai.model_context import (
    MODEL_CONTEXT_LIMITS,
    format_context_window_note,
    get_model_context_limit,
)


def test_table_populated():
    assert len(MODEL_CONTEXT_LIMITS) >= 400  # ~461 models across 39 providers


def test_known_models_exact():
    assert get_model_context_limit("gpt-4o") == 128_000
    assert get_model_context_limit("deepseek-chat") == 65_536
    assert get_model_context_limit("deepseek-reasoner") == 65_536
    assert get_model_context_limit("glm-4-plus") == 128_000


def test_unknown_returns_none():
    assert get_model_context_limit("totally-fake-model-xyz") is None
    assert get_model_context_limit("") is None
    assert get_model_context_limit(None) is None  # type: ignore[arg-type]


def test_variant_suffix_fallback():
    # base ids that exist only as -latest / -preview variants resolve via stripping
    assert get_model_context_limit("glm-4") == 128_000
    assert get_model_context_limit("gpt-4o-mini-latest") == 128_000


def test_format_note_known_and_unknown():
    assert "128,000" in format_context_window_note("gpt-4o")
    assert format_context_window_note("unknown-model") == ""


def test_no_negative_or_zero_limits():
    """Data sanity: every recorded limit is a positive int."""
    bad = {k: v for k, v in MODEL_CONTEXT_LIMITS.items() if not isinstance(v, int) or v <= 0}
    assert not bad, bad
