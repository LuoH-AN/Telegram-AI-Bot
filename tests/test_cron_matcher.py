"""Tests for cron expression field matching."""

from __future__ import annotations

import pytest
from datetime import datetime

from domain.services.cron.matcher import _field_matches, _cron_matches

DT = datetime(2026, 7, 9, 14, 30)  # minute=30, hour=14, day=9, month=7, weekday=Thu=4


def _minute(expr, value, lo=0, hi=59):
    return _field_matches(expr, value, lo, hi)


def test_star_matches():
    assert _minute("*", 30)


def test_exact_value():
    assert _minute("30", 30)
    assert not _minute("31", 30)


def test_star_with_step():
    assert _minute("*/15", 30)
    assert _minute("*/15", 0)
    assert not _minute("*/15", 7)


def test_single_value_with_step():
    """5/2 means starting at 5 every 2: 5,7,9,..."""
    assert _minute("5/2", 5)
    assert _minute("5/2", 7)
    assert _minute("5/2", 59)
    assert not _minute("5/2", 6)
    assert not _minute("5/2", 4)


def test_range_clamped_to_hi():
    """5-99 on a minute field must clamp the end to 59, not match values >59."""
    assert _minute("5-99", 30)
    assert _minute("5-99", 59)
    # a value above the real ceiling never matches because value itself is >hi
    assert not _field_matches("5-99", 70, 0, 59)


def test_range_with_step():
    assert _minute("0-30/10", 0)
    assert _minute("0-30/10", 10)
    assert _minute("0-30/10", 30)
    assert not _minute("0-30/10", 5)


def test_comma_list():
    assert _minute("0,15,30,45", 30)
    assert not _minute("0,15,30,45", 7)


def test_out_of_range_value_never_matches():
    assert not _field_matches("5", 70, 0, 59)


def test_full_cron_matches():
    assert _cron_matches("30 14 9 7 *", DT)
    assert not _cron_matches("31 14 9 7 *", DT)


def test_full_cron_weekday():
    # DT is Thursday. isoweekday=4 -> %7 = 4
    assert _cron_matches("30 14 * * 4", DT)
    assert not _cron_matches("30 14 * * 1", DT)


def test_bad_expression_does_not_match():
    assert not _cron_matches("not a cron", DT)
    assert not _cron_matches("* * * *", DT)
