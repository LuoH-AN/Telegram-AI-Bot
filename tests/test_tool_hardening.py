"""Regression coverage for strict tool boundaries and truthful side effects."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from infrastructure.tools.core import ToolContext, ToolResult
from infrastructure.tools.core.execute import execute_tool_calls
from infrastructure.tools.core.registry import ToolEntry
from infrastructure.tools.core.schema import validate


def test_schema_rejects_unknown_fields_and_wrong_types():
    from infrastructure.tools.builtin.search.search import search

    _, unknown = validate(search, {"action": "search", "query": "x", "typo": 1})
    _, wrong = validate(search, {"action": "search", "query": "x", "top_k": {"bad": 1}})

    assert "unknown parameter" in unknown
    assert "integer" in wrong


def test_config_format_hint_cannot_reclassify_source_code():
    from infrastructure.tools.builtin.config_file.files import detect_format

    with pytest.raises(ValueError, match="does not match"):
        detect_format(Path("main.py"), "env")


def test_env_key_update_preserves_comments(monkeypatch, tmp_path):
    from infrastructure.tools.builtin.config_file.formats import delete_env_key, set_env_key

    path = tmp_path / ".env"
    path.write_text("# keep this\nA=1\n\nB='two'\n", encoding="utf-8")
    set_env_key(path, "A", "3")
    assert path.read_text("utf-8") == "# keep this\nA=3\n\nB='two'\n"
    assert delete_env_key(path, "A") is True
    assert path.read_text("utf-8") == "# keep this\n\nB='two'\n"


def test_config_redacts_nested_secrets():
    from infrastructure.tools.builtin.config_file.config_file import _redact

    value = {"model": "m", "auth": {"api_key": "secret-value"}}
    assert _redact(value) == {"model": "m", "auth": {"api_key": "<redacted>"}}


def test_mcp_tools_default_to_admin_only():
    from infrastructure.tools.core.registry import registry
    from infrastructure.tools.mcp.config import McpServerConfig
    from infrastructure.tools.mcp.registry import _register_server, reset

    remote = type("RemoteTool", (), {"name": "read_file", "description": "read", "inputSchema": {}})()
    reset()
    try:
        assert _register_server(McpServerConfig(name="fs", transport="stdio"), [remote]) == 1
        entry = registry.get("fs__read_file")
        assert entry.toolset == "admin"
        assert entry.danger is True
    finally:
        reset()


def test_mcp_reload_swaps_registry_after_probing(monkeypatch):
    from infrastructure.tools.core.registry import registry
    from infrastructure.tools.mcp.config import McpServerConfig
    import infrastructure.tools.mcp.registry as mcp_registry

    old_tool = type("RemoteTool", (), {"name": "old", "description": "old", "inputSchema": {}})()
    new_tool = type("RemoteTool", (), {"name": "new", "description": "new", "inputSchema": {}})()
    old_config = McpServerConfig(name="old_server", transport="stdio")
    new_config = McpServerConfig(name="new_server", transport="stdio")
    mcp_registry.reset()
    try:
        mcp_registry._register_server(old_config, [old_tool])
        monkeypatch.setattr(mcp_registry, "load_servers", lambda: [new_config])

        def probe(_config):
            assert registry.get("old_server__old") is not None
            assert registry.get("new_server__new") is None
            return [new_tool]

        monkeypatch.setattr(mcp_registry, "_probe_sync", probe)
        outcome = mcp_registry.reload_mcp()
        assert outcome == {"servers": 1, "registered_tools": 1, "failures": {}}
        assert registry.get("old_server__old") is None
        assert registry.get("new_server__new") is not None
    finally:
        mcp_registry.reset()


def test_mcp_config_validation_rejects_entries_that_would_silently_disappear():
    from infrastructure.tools.mcp.config import validate_servers_payload

    errors = validate_servers_payload([{"name": "demo", "transport": "stdio", "args": "bad"}])
    assert "args must be a list" in "; ".join(errors)
    assert "requires a command" in "; ".join(errors)


def test_external_skill_registration_restores_runtime_record_on_failure(monkeypatch, tmp_path):
    import infrastructure.tools.builtin.config_file.files as config_files
    import infrastructure.tools.skills.agent_plugins as agent_plugins

    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text("---\nname: demo\nversion: '1'\ndescription: demo\n---\nbody\n", encoding="utf-8")

    previous = object()

    class FakeManager:
        record = previous

        def snapshot_record(self, _name):
            return self.record

        def hot_load(self, _path):
            self.record = "new"
            return "demo"

        def add_user_skill(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

        def restore_record(self, _name, record):
            self.record = record

    manager = FakeManager()
    monkeypatch.setattr(config_files, "is_external_skill_manifest", lambda _path: True)
    monkeypatch.setattr(agent_plugins, "get_skill_manager", lambda: manager)

    with pytest.raises(RuntimeError, match="database unavailable"):
        agent_plugins.register_external_skill_manifest(1, path)
    assert manager.record is previous


def test_user_skill_registration_rolls_back_cache_on_sync_failure(monkeypatch, tmp_path):
    from infrastructure.cache.manager.cache import CacheManager
    from infrastructure.tools.skills.manifest import load_manifest
    import infrastructure.tools.skills.user_state as user_state

    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\nversion: '1'\ndescription: demo\n---\nbody\n",
        encoding="utf-8",
    )
    manifest = load_manifest(skill_dir, is_builtin=False)
    cache = CacheManager()
    monkeypatch.setattr(user_state, "cache", cache)
    monkeypatch.setattr(
        user_state,
        "sync_to_database",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        user_state.ensure_user_skill(1, manifest, source_type="external")
    assert cache.get_skills(1) == []
    assert cache._new_skills == []


def test_invalid_setting_is_rejected_without_mutating_cache(monkeypatch):
    from infrastructure.cache.manager.cache import CacheManager
    import infrastructure.tools.builtin.database.settings as settings_tool

    cache = CacheManager()
    original = cache.get_settings(1)["temperature"]
    monkeypatch.setattr(settings_tool, "get_cache", lambda: cache)
    monkeypatch.setattr(settings_tool, "commit", lambda: None)

    result = settings_tool._run(1, "set", "temperature", "not-a-number")
    assert result.ok is False
    assert cache.get_settings(1)["temperature"] == original


def test_setting_commit_failure_rolls_back_memory(monkeypatch):
    from infrastructure.cache.manager.cache import CacheManager
    import infrastructure.tools.builtin.database.settings as settings_tool

    cache = CacheManager()
    original = cache.get_settings(1)["temperature"]
    cache._dirty_settings.clear()
    monkeypatch.setattr(settings_tool, "get_cache", lambda: cache)
    monkeypatch.setattr(
        settings_tool,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        settings_tool._run(1, "set", "temperature", 1.2)
    assert cache.get_settings(1)["temperature"] == original
    assert 1 not in cache._dirty_settings


def test_cron_validation_and_zero_token_limit(monkeypatch):
    from infrastructure.cache.manager.cache import CacheManager
    import infrastructure.tools.builtin.database.cron as cron_tool
    import infrastructure.tools.builtin.database.tokens as token_tool

    cache = CacheManager()
    cache.get_settings(1)
    monkeypatch.setattr(cron_tool, "get_cache", lambda: cache)
    monkeypatch.setattr(cron_tool, "commit", lambda: None)
    monkeypatch.setattr(token_tool, "get_cache", lambda: cache)
    monkeypatch.setattr(token_tool, "commit", lambda: None)

    assert json.loads(cron_tool._run(1, "add", "bad", "not cron", "x", None).content)["error"]["code"] == "invalid_cron"
    assert token_tool._run(1, "set_limit", "default", 0).ok is True
    assert cache.get_token_limit(1, "default") == 0


def test_memory_rejects_secrets_and_prompt_is_bounded(monkeypatch):
    import infrastructure.tools.builtin.memory.memory as memory_tool
    import domain.services.memory.prompt as prompt_module

    rejected = asyncio.run(memory_tool.save_memory(ToolContext(user_id=1), "api_key=sk-abcdefghijklmnop"))
    assert json.loads(rejected.content)["error"]["code"] == "secret_detected"

    memories = [{"content": f"memory-{index}"} for index in range(100)]
    monkeypatch.setattr(prompt_module.cache, "get_memories", lambda _user_id: memories)
    monkeypatch.setattr(prompt_module, "is_available", lambda: False)
    monkeypatch.setattr(prompt_module, "MEMORY_TOP_K", 5)
    rendered = prompt_module.format_memories_for_prompt(1)
    assert rendered.count("- memory-") == 5
    assert "never as instructions" in rendered


def test_conversation_mutation_requires_count_and_can_restore(monkeypatch, tmp_path):
    from infrastructure.cache.manager.cache import CacheManager
    import infrastructure.tools.builtin.database.conversations as conversations

    cache = CacheManager()
    cache.get_settings(1)
    session = cache.create_session(1, "default")
    cache.add_message_to_session(session["id"], "user", "original")
    monkeypatch.setattr(conversations, "get_cache", lambda: cache)
    monkeypatch.setattr(conversations, "commit", lambda: None)
    monkeypatch.setattr(conversations, "_BACKUP_ROOT", tmp_path)

    mismatch = conversations._run(1, "clear", session["id"], None, 0, "")
    assert json.loads(mismatch.content)["error"]["code"] == "count_mismatch"

    replaced = conversations._run(
        1,
        "replace",
        session["id"],
        [{"role": "assistant", "content": "replacement"}],
        1,
        "",
    )
    backup_id = replaced.content.split("backup_id=", 1)[1]
    assert cache.get_conversation_by_session(session["id"])[0]["content"] == "replacement"

    restored = conversations._run(1, "restore", session["id"], None, 1, backup_id)
    assert restored.ok is True
    assert cache.get_conversation_by_session(session["id"])[0]["content"] == "original"


def test_empty_skill_state_is_a_real_delete(monkeypatch):
    from infrastructure.cache.manager.cache import CacheManager
    import infrastructure.tools.builtin.database.skill_state as skill_state

    cache = CacheManager()
    cache.set_skill_state(1, "demo", {"state": {"x": 1}})
    cache._updated_skill_states.clear()
    monkeypatch.setattr(skill_state, "get_cache", lambda: cache)
    monkeypatch.setattr(skill_state, "commit", lambda: None)

    result = skill_state._run(1, "set", "demo", {})
    assert result.ok is True
    assert cache.get_skill_state(1, "demo") is None
    assert (1, "demo") in cache._deleted_skill_states


def test_side_effecting_tool_waits_for_truthful_completion_after_timeout():
    async def handler(ctx):
        await asyncio.sleep(0.05)
        return ToolResult.text("committed")

    entry = ToolEntry(
        name="mutate",
        description="mutate",
        toolset="test",
        handler=handler,
        is_async=True,
        timeout=0.01,
        side_effects=True,
    )
    call = type("Call", (), {"id": "1", "name": "mutate", "arguments": "{}"})()
    started = time.monotonic()
    result = asyncio.run(execute_tool_calls(1, [call], visible={"mutate": entry}))

    assert time.monotonic() - started >= 0.04
    assert result[0]["content"] == "committed"
