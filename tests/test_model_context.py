"""Tests for the model context-window table and resolver."""

from __future__ import annotations

from infrastructure.ai.model_context import (
    MODEL_CONTEXT_LIMITS,
    MODEL_MAX_OUTPUT,
    format_context_window_note,
    get_model_context_limit,
    get_model_max_output,
)


def test_table_populated():
    assert len(MODEL_CONTEXT_LIMITS) >= 1000  # ~1188 models across 81 providers (v2.2.9)


def test_known_models_exact():
    assert get_model_context_limit("gpt-4o") == 128_000
    assert get_model_context_limit("deepseek-v4-pro") == 1_048_576
    assert get_model_context_limit("gpt-5.2") == 400_000
    assert get_model_context_limit("gemini-2.5-pro") == 1_114_112


def test_unknown_returns_none():
    assert get_model_context_limit("totally-fake-model-xyz") is None
    assert get_model_context_limit("") is None
    assert get_model_context_limit(None) is None  # type: ignore[arg-type]


def test_variant_suffix_fallback():
    # dated/variant suffixes strip so older base ids still resolve
    assert get_model_context_limit("claude-opus-4-1") == 200_000  # -> claude-opus-4-1-20250805
    assert get_model_context_limit("gpt-4o-mini-latest") == 128_000


def test_max_output():
    assert get_model_max_output("gpt-4o") == 4096
    assert get_model_max_output("deepseek-v4-pro") == 393_216
    assert get_model_max_output("unknown-model") is None


def test_format_note_known_and_unknown():
    note = format_context_window_note("deepseek-v4-pro")
    assert "1,048,576 context tokens" in note
    assert "393,216 max output" in note
    assert format_context_window_note("unknown-model") == ""


def test_no_negative_or_zero_limits():
    """Data sanity: every recorded limit is a positive int."""
    bad = {k: v for k, v in MODEL_CONTEXT_LIMITS.items() if not isinstance(v, int) or v <= 0}
    assert not bad, bad
    bad_out = {k: v for k, v in MODEL_MAX_OUTPUT.items() if not isinstance(v, int) or v <= 0}
    assert not bad_out, bad_out
