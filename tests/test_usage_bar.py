"""Tests for the /usage context-window bar rendering."""

from __future__ import annotations

import domain.services.platform.view as view


def _mock_view(monkeypatch, *, model: str, last_prompt: int, total: int = 0, limit: int = 0):
    monkeypatch.setattr(view, "get_current_persona_name", lambda uid: "default")
    monkeypatch.setattr(
        view,
        "get_token_usage",
        lambda uid, p: {"prompt_tokens": total // 2, "completion_tokens": total // 2, "total_tokens": total},
    )
    monkeypatch.setattr(view, "get_last_turn_prompt", lambda uid, p: last_prompt)
    monkeypatch.setattr(view, "get_token_limit", lambda uid, p: limit)
    monkeypatch.setattr(view, "get_total_tokens_all_personas", lambda uid: total)
    monkeypatch.setattr(view, "get_user_settings", lambda uid: {"model": model})


def test_bar_segments_match_percent():
    assert view._usage_bar(35).count("🟩") == 4
    assert view._usage_bar(35).count("⬜") == 6
    assert view._usage_bar(0).count("🟩") == 0
    assert view._usage_bar(100).count("🟩") == 10


def test_bar_color_thresholds():
    assert "🟢" in view._usage_bar(20)
    assert "🟡" in view._usage_bar(60)
    assert "🔴" in view._usage_bar(90)


def test_context_bar_uses_last_turn_vs_model_window(monkeypatch):
    # gpt-4o = 128k window; last turn 32k -> 25%
    _mock_view(monkeypatch, model="gpt-4o", last_prompt=32000)
    text = view.build_usage_text(1)
    assert "25.0%" in text
    assert "of context" in text
    assert "Last turn: 32,000 / 128,000" in text
    assert "model `gpt-4o`" in text


def test_manual_limit_caps_ceiling_when_tighter(monkeypatch):
    # gpt-4o = 128k but manual limit 50k wins; last turn 32k -> 64%
    _mock_view(monkeypatch, model="gpt-4o", last_prompt=32000, limit=50000)
    text = view.build_usage_text(1)
    assert "64.0%" in text
    assert "32,000 / 50,000" in text
    assert "model `gpt-4o`" not in text  # manual limit won, so no model label


def test_red_when_near_full(monkeypatch):
    _mock_view(monkeypatch, model="gpt-4o", last_prompt=115000)  # ~90% of 128k
    assert "🔴" in view.build_usage_text(1)


def test_no_turn_recorded_shows_ceiling_only(monkeypatch):
    _mock_view(monkeypatch, model="gpt-4o", last_prompt=0)
    text = view.build_usage_text(1)
    assert "Context window: 128,000" in text
    assert "🟩" not in text  # no bar without a turn


def test_unknown_model_no_limit_shows_unlimited(monkeypatch):
    _mock_view(monkeypatch, model="totally-unknown-xyz", last_prompt=8000)
    text = view.build_usage_text(1)
    assert "No limit known" in text
    assert "🟩" not in text
