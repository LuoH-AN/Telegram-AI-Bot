"""Tests for compact number formatting (k/M/B)."""

from __future__ import annotations

from shared.utils.format import format_count, format_tokens


def test_small_numbers_unchanged():
    assert format_count(0) == "0"
    assert format_count(42) == "42"
    assert format_count(999) == "999"


def test_thousands():
    assert format_count(1000) == "1K"
    assert format_count(128000) == "128K"
    assert format_count(4096) == "4.1K"
    assert format_count(65536) == "65.5K"
    assert format_count(695618) == "695.6K"


def test_millions():
    assert format_count(1_000_000) == "1M"
    assert format_count(1_315_672) == "1.3M"
    assert format_count(1_114_112) == "1.1M"


def test_billions():
    assert format_count(2_500_000_000) == "2.5B"


def test_negative():
    assert format_count(-32000) == "-32K"


def test_tokens_unit():
    assert format_tokens(128000) == "128K tokens"
    assert format_tokens(0) == "0 tokens"
