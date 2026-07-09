"""Tests for message splitting."""

from __future__ import annotations

from shared.utils.format.split import split_message


def test_short_message_returns_single_chunk():
    assert split_message("hello", 100) == ["hello"]


def test_paragraph_boundary_preferred():
    text = "para1\n\npara2"
    assert split_message(text, 100) == [text]


def test_splits_at_paragraph_when_over_limit():
    a = "a" * 30
    b = "b" * 30
    chunks = split_message(f"{a}\n\n{b}", max_length=40)
    assert len(chunks) == 2
    assert chunks == [a, b]
    for c in chunks:
        assert len(c) <= 40


def test_hard_splits_overlong_line():
    line = "x" * 25
    chunks = split_message(line, max_length=10)
    assert chunks == ["x" * 10, "x" * 10, "x" * 5]
    for c in chunks:
        assert len(c) <= 10


def test_line_level_boundary():
    line1 = "y" * 30
    line2 = "z" * 30
    chunks = split_message(f"{line1}\n{line2}", max_length=40)
    assert len(chunks) == 2
    for c in chunks:
        assert len(c) <= 40


def test_empty_string():
    assert split_message("", 100) == [""]
