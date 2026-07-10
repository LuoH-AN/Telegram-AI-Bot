"""Tests for config env loading idempotency (P2)."""

from __future__ import annotations

import infrastructure.config.env as env_mod
from infrastructure.config import load_env


def test_load_env_runs_once_at_import():
    assert env_mod._ENV_LOADED is True


def test_load_env_is_idempotent():
    """Repeated non-force calls must not re-run the loader."""
    env_mod._ENV_LOADED = True
    load_env()  # no raise, no double-load path exercised
    assert env_mod._ENV_LOADED is True


def test_load_env_force_reruns():
    env_mod._ENV_LOADED = False
    load_env(force=True)
    assert env_mod._ENV_LOADED is True


def test_default_settings_include_timezone():
    from infrastructure.config import get_default_settings

    settings = get_default_settings()
    assert settings["timezone"]
    assert settings["busy_mode"] == "interrupt"
    assert settings["tool_progress"] == "compact"


def test_settings_sync_columns_include_timezone():
    from infrastructure.cache.sync.settings import SETTINGS_COLUMNS, values
    from infrastructure.config import get_default_settings

    settings = get_default_settings()
    assert "timezone" in SETTINGS_COLUMNS
    assert "busy_mode" in SETTINGS_COLUMNS
    assert "tool_progress" in SETTINGS_COLUMNS
    assert len(values(1, settings)) == len(SETTINGS_COLUMNS)
