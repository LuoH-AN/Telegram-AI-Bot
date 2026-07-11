"""Regression tests for authorization and tenant-isolation boundaries."""

from __future__ import annotations

import asyncio
import json

from infrastructure.cache.manager.cache import CacheManager


def _tool_names(tools: list[dict]) -> set[str]:
    return {item["function"]["name"] for item in tools}


def test_admin_toolset_is_hidden_from_regular_users(monkeypatch):
    import infrastructure.tools as tool_api

    monkeypatch.delenv("ENABLED_TOOLS", raising=False)
    monkeypatch.setattr(tool_api, "is_admin", lambda user_id: user_id == 1)

    regular = _tool_names(tool_api.get_all_tools(user_id=2))
    admin = _tool_names(tool_api.get_all_tools(user_id=1))

    assert "config_file" not in regular
    assert "user_settings" not in regular
    assert "user_conversations" not in regular
    assert "terminal" not in regular
    assert "config_file" in admin
    assert "user_conversations" in admin
    assert "terminal" in admin


def test_enabled_tools_filter_matches_name_skill_or_toolset(monkeypatch):
    import infrastructure.tools as tool_api

    monkeypatch.delenv("ENABLED_TOOLS", raising=False)
    monkeypatch.setattr(tool_api, "is_admin", lambda _user_id: False)

    assert _tool_names(tool_api.get_all_tools("search", user_id=2)) == {"search"}
    assert _tool_names(tool_api.get_all_tools("memory", user_id=2)) == {
        "save_memory",
        "list_memories",
        "manage_memory",
    }


def test_session_tools_reject_cross_user_ids(monkeypatch):
    import infrastructure.tools.builtin.database.conversations as conversations
    import infrastructure.tools.builtin.database.sessions as sessions

    cache = CacheManager()
    cache.get_settings(1001)
    cache.get_settings(2002)
    victim = cache.create_session(2002, "default")
    cache.set_current_session_id(2002, "default", victim["id"])
    cache.add_message_to_session(victim["id"], "user", "victim-private-message")

    monkeypatch.setattr(conversations, "get_cache", lambda: cache)
    monkeypatch.setattr(sessions, "get_cache", lambda: cache)
    monkeypatch.setattr(sessions, "commit", lambda: (_ for _ in ()).throw(AssertionError("must not commit")))

    session_result = sessions._run(1001, "get", "", victim["id"], "")
    conversation_result = conversations._run(1001, "get", victim["id"], None, -1, "")

    assert session_result.ok is False
    assert conversation_result.ok is False
    assert "victim-private-message" not in conversation_result.content
    assert json.loads(conversation_result.content)["error"]["code"] == "not_found"
    delete_result = sessions._run(1001, "delete", "", victim["id"], "")
    assert delete_result.ok is False
    assert cache.get_session_by_id(victim["id"])["user_id"] == 2002


def test_user_settings_tool_redacts_credentials(monkeypatch):
    import infrastructure.tools.builtin.database.settings as settings_tool

    cache = CacheManager()
    cache.get_settings(1).update({
        "api_key": "sk-secret",
        "api_presets": {"main": {"api_key": "preset-secret", "model": "m"}},
    })
    monkeypatch.setattr(settings_tool, "get_cache", lambda: cache)

    result = settings_tool._run(1, "get", "", None)
    assert "sk-secret" not in result.content
    assert "preset-secret" not in result.content
    assert "<redacted>" in result.content


def test_system_commands_are_marked_admin_only():
    from adapters.telegram.commands import get_command

    assert get_command("update").admin_only is True
    assert get_command("restart").admin_only is True


def test_skill_install_requires_admin(monkeypatch):
    import infrastructure.tools.skills.commands as commands

    monkeypatch.setattr(commands, "is_admin", lambda _user_id: False)
    result = asyncio.run(commands.handle_skill_install(123, "owner/repo"))
    assert "restricted" in result.lower()
