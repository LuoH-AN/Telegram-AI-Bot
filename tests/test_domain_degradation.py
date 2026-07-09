"""Tests that domain helper degradation is graceful AND observable (P3)."""

from __future__ import annotations

import logging

import pytest

import domain.services.persona as persona_mod
import domain.services.platform.app as platform_app
import domain.services.status as status_mod


@pytest.fixture()
def capwarn(caplog):
    caplog.set_level(logging.WARNING, logger="domain.services.persona")
    caplog.set_level(logging.WARNING, logger="domain.services.platform.app")
    caplog.set_level(logging.WARNING, logger="domain.services.status")
    return caplog


def test_skill_instructions_degrades_to_empty_and_logs(capwarn, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("infra down")

    monkeypatch.setattr("infrastructure.tools.get_tool_instructions", _boom, raising=False)
    # ensure the import inside _get_skill_instructions resolves to our bomb
    import sys

    fake = type("M", (), {"get_tool_instructions": staticmethod(_boom)})
    monkeypatch.setitem(sys.modules, "infrastructure.tools", fake)
    result = persona_mod._get_skill_instructions(1)
    assert result == ""
    assert any("tool instructions unavailable" in r.getMessage() for r in capwarn.records)


def test_fetch_models_degrades_and_logs(capwarn, monkeypatch):
    monkeypatch.setattr(platform_app, "get_ai_client", lambda uid: (_ for _ in ()).throw(RuntimeError("no key")))
    assert platform_app.fetch_models_for_user(1) == []
    assert any("failed to list models" in r.getMessage() for r in capwarn.records)


def test_plugin_names_degrades_and_logs(capwarn, monkeypatch):
    def _boom():
        raise RuntimeError("skills broken")

    monkeypatch.setattr(
        "infrastructure.tools.skills.manager.get_skill_manager", _boom, raising=False
    )
    assert status_mod._plugin_names() == []
    assert any("skill manager unavailable" in r.getMessage() for r in capwarn.records)
