"""Tests for the /usage progress bar rendering."""

from __future__ import annotations

import domain.services.platform.view as view


def _mock_view(monkeypatch, *, total: int, limit: int):
    monkeypatch.setattr(view, "get_current_persona_name", lambda uid: "default")
    monkeypatch.setattr(
        view,
        "get_token_usage",
        lambda uid, p: {"prompt_tokens": total // 2, "completion_tokens": total // 2, "total_tokens": total},
    )
    monkeypatch.setattr(view, "get_token_limit", lambda uid, p: limit)
    monkeypatch.setattr(view, "get_remaining_tokens", lambda uid, p: (max(0, limit - total) if limit else None))
    monkeypatch.setattr(view, "get_usage_percentage", lambda uid, p: (min(100.0, total / limit * 100) if limit else None))
    monkeypatch.setattr(view, "get_total_tokens_all_personas", lambda uid: total)


def test_bar_segments_match_percent(monkeypatch):
    assert view._usage_bar(35).count("🟩") == 4
    assert view._usage_bar(35).count("⬜") == 6
    assert view._usage_bar(0).count("🟩") == 0
    assert view._usage_bar(100).count("🟩") == 10


def test_bar_color_thresholds():
    assert "🟢" in view._usage_bar(20)
    assert "🟡" in view._usage_bar(60)
    assert "🔴" in view._usage_bar(90)


def test_build_usage_text_limited(monkeypatch):
    _mock_view(monkeypatch, total=350, limit=1000)
    text = view.build_usage_text(1)
    assert "🟢" in text
    assert "35.0%" in text
    assert "Limit: 1,000 · Remaining: 650" in text
    assert "━ **All Personas** ━━" in text


def test_build_usage_text_red_at_threshold(monkeypatch):
    _mock_view(monkeypatch, total=900, limit=1000)
    assert "🔴" in view.build_usage_text(1)


def test_build_usage_text_unlimited(monkeypatch):
    _mock_view(monkeypatch, total=500, limit=0)
    text = view.build_usage_text(1)
    assert "Unlimited" in text
    assert "🟩" not in text  # no bar when unlimited
