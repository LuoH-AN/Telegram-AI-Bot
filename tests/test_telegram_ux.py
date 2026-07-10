"""Tests for the button-driven Telegram UX and localized helpers."""

from __future__ import annotations

import asyncio
import importlib
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from adapters.telegram.commands.settings.model import _build_model_keyboard
from adapters.telegram.ux.errors import error_panel
from adapters.telegram.ux.locale import language, pick
from adapters.telegram.ux.panels import generation_panel, help_panel, main_panel, stop_keyboard
from domain.services.cron.matcher import is_valid_cron
from domain.services.cron.timezone import describe_cron, next_run_at
from shared.utils.ai.status import build_tool_progress_text


def _callbacks(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}


def test_language_auto_detect_and_manual_override():
    update = type("Update", (), {"effective_user": type("User", (), {"language_code": "zh-hans"})()})()
    context = type("Context", (), {"user_data": {}})()
    assert language(update, context) == "zh"
    context.user_data["ux_language"] = "en"
    assert language(update, context) == "en"
    assert pick("zh", "中文", "English") == "中文"


def test_onboarding_panel_has_safe_setup_actions(monkeypatch):
    import adapters.telegram.ux.panels as panels

    monkeypatch.setattr(panels, "has_api_key", lambda _user_id: False)
    text, keyboard = main_panel(1, "zh")
    callbacks = _callbacks(keyboard)
    assert "API Key" in text
    assert "ux:onboard:key" in callbacks
    assert "ux:onboard:base_custom" in callbacks


def test_configured_main_panel_links_primary_tasks(monkeypatch):
    import adapters.telegram.ux.panels as panels

    monkeypatch.setattr(panels, "has_api_key", lambda _user_id: True)
    monkeypatch.setattr(panels, "get_current_persona_name", lambda _user_id: "default")
    _, keyboard = main_panel(1, "en")
    callbacks = _callbacks(keyboard)
    assert {"ux:chat:0", "ux:persona:0", "ux:settings", "ux:cron", "ux:help"} <= callbacks


def test_generation_panel_exposes_busy_and_tool_progress_controls(monkeypatch):
    import adapters.telegram.ux.panels as panels

    monkeypatch.setattr(
        panels,
        "get_user_settings",
        lambda _user_id: {
            "reasoning_effort": "medium",
            "stream_mode": "default",
            "show_thinking": False,
            "temperature": 0.7,
            "busy_mode": "queue",
            "tool_progress": "compact",
        },
    )
    text, keyboard = generation_panel(1, "en")
    callbacks = _callbacks(keyboard)
    assert "queue" in text.lower()
    assert "compact" in text.lower()
    assert {"ux:set:busy:interrupt", "ux:set:busy:queue"} <= callbacks
    assert {
        "ux:set:progress:off",
        "ux:set:progress:compact",
        "ux:set:progress:full",
    } <= callbacks


def test_help_hides_admin_tools_for_regular_users(monkeypatch):
    import adapters.telegram.ux.panels as panels

    monkeypatch.setattr(panels, "is_admin", lambda _user_id: False)
    _, regular = help_panel(2, "en")
    assert "ux:help:admin" not in _callbacks(regular)
    monkeypatch.setattr(panels, "is_admin", lambda _user_id: True)
    _, admin = help_panel(1, "en")
    assert "ux:help:admin" in _callbacks(admin)


def test_error_panels_offer_actionable_recovery():
    text, keyboard = error_panel(RuntimeError("401 invalid_api_key"), "en")
    assert "authentication" in text.lower()
    assert "ux:settings:connection" in _callbacks(keyboard)

    text, keyboard = error_panel(TimeoutError("request timed out"), "zh")
    assert "重试" in text or "超时" in text
    assert "ux:retry" in _callbacks(keyboard)


def test_usage_panel_is_localized(monkeypatch):
    import domain.services.platform.view as view

    monkeypatch.setattr(view, "get_current_persona_name", lambda _user_id: "default")
    monkeypatch.setattr(view, "get_token_usage", lambda *_args: {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})
    monkeypatch.setattr(view, "get_last_turn_prompt", lambda *_args: 100)
    monkeypatch.setattr(view, "get_user_settings", lambda _user_id: {"model": "unknown-model"})
    monkeypatch.setattr(view, "get_token_limit", lambda *_args: 1000)
    monkeypatch.setattr(view, "get_total_tokens_all_personas", lambda _user_id: 120)

    text = view.build_usage_text(1, lang="zh")
    assert "Token 用量" in text
    assert "剩余容量" in text
    assert "全部角色" in text


def test_stop_keyboard_has_callback():
    assert _callbacks(stop_keyboard("zh")) == {"ux:stop"}
    assert _callbacks(stop_keyboard("zh", user_id=42)) == {"ux:stop:42"}


def test_error_and_stop_actions_can_be_bound_to_request_owner():
    _, keyboard = error_panel(TimeoutError("request timed out"), "en", user_id=42)
    assert "ux:retry:42" in _callbacks(keyboard)


def test_group_member_cannot_use_another_users_stop_button():
    from adapters.telegram.ux.callbacks import ux_callback

    answers = []

    class Query:
        data = "ux:stop:42"

        async def answer(self, *args, **kwargs):
            answers.append((args, kwargs))

    update = type(
        "Update",
        (),
        {
            "callback_query": Query(),
            "effective_user": type("User", (), {"id": 7, "language_code": "en"})(),
            "effective_chat": type("Chat", (), {"id": -100, "type": "group"})(),
        },
    )()
    context = type("Context", (), {"user_data": {}})()

    asyncio.run(ux_callback(update, context))
    assert answers[0][1]["show_alert"] is True
    assert "started this request" in answers[0][0][0]


def test_model_picker_uses_short_index_callbacks_for_long_model_names():
    model = "provider/" + "very-long-model-name-" * 8
    keyboard = _build_model_keyboard([model], 0, "", lang="zh")
    callbacks = _callbacks(keyboard)
    assert "model:index:0" in callbacks
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_model_index_callback_persists_selected_model(monkeypatch):
    import adapters.telegram.handlers.callback as callback_handler

    saved = []
    synced = []

    class Query:
        data = "model:index:0"

        async def answer(self):
            return None

    update = type(
        "Update",
        (),
        {
            "callback_query": Query(),
            "effective_user": type("User", (), {"id": 1, "language_code": "en"})(),
            "effective_chat": type("Chat", (), {"id": 1, "type": "private"})(),
        },
    )()
    context = type("Context", (), {"user_data": {"models": ["provider/long-model"]}})()
    monkeypatch.setattr(callback_handler, "update_user_setting", lambda *args: saved.append(args))
    monkeypatch.setattr(callback_handler, "sync_to_database", lambda: synced.append(True))

    async def fake_edit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(callback_handler, "edit_query_rich_text", fake_edit)
    asyncio.run(callback_handler.model_callback(update, context))
    assert saved == [(1, "model", "provider/long-model")]
    assert synced == [True]


def test_tool_progress_is_localized_and_tracks_completion():
    text = build_tool_progress_text({"search": "done", "send_file": "running"}, lang="zh")
    assert "搜索资料完成" in text
    assert "准备文件" in text


def test_compact_tool_progress_limits_detail_but_keeps_active_and_errors():
    states = {
        "search": "done",
        "save_memory": "done",
        "list_memories": "done",
        "send_file": "running",
        "terminal": "error",
        "config_file": "running",
    }
    text = build_tool_progress_text(states, lang="en", mode="compact")
    assert "Preparing file" in text
    assert "Running command failed" in text
    assert "3 completed" in text
    assert len(text.splitlines()) <= 4


@pytest.mark.parametrize(
    ("callback_data", "setting", "value"),
    [
        ("ux:set:busy:queue", "busy_mode", "queue"),
        ("ux:set:progress:full", "tool_progress", "full"),
    ],
)
def test_telegram_ux_callbacks_persist_valid_modes(monkeypatch, callback_data, setting, value):
    import adapters.telegram.ux.callbacks as callbacks

    saved = []
    persisted = []

    class Query:
        data = callback_data

        async def answer(self, *_args, **_kwargs):
            return None

    update = type(
        "Update",
        (),
        {
            "callback_query": Query(),
            "effective_user": type("User", (), {"id": 1, "language_code": "en"})(),
            "effective_chat": type("Chat", (), {"id": 1, "type": "private"})(),
        },
    )()
    context = type("Context", (), {"user_data": {}})()

    async def fake_ensure_user_state(_user_id):
        return None

    async def fake_persist():
        persisted.append(True)

    async def fake_edit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(callbacks, "ensure_user_state", fake_ensure_user_state)
    monkeypatch.setattr(callbacks, "update_user_setting", lambda *args: saved.append(args))
    monkeypatch.setattr(callbacks, "_persist", fake_persist)
    monkeypatch.setattr(callbacks, "_edit", fake_edit)
    monkeypatch.setattr(callbacks, "generation_panel", lambda *_args: ("settings", None))

    asyncio.run(callbacks.ux_callback(update, context))
    assert saved == [(1, setting, value)]
    assert persisted == [True]


def test_cron_validation_preview_and_next_run():
    assert is_valid_cron("0 9 * * *")
    assert not is_valid_cron("not a cron")
    assert describe_cron("0 9 * * *", lang="zh") == "每天 09:00"
    assert describe_cron("0 9 * * 1", lang="zh") == "每周一 09:00"
    start = datetime(2026, 7, 10, 8, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = next_run_at("0 9 * * *", "Asia/Shanghai", start=start)
    assert result == datetime(2026, 7, 10, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_cron_pending_flow_keeps_state_and_uses_full_cancel(monkeypatch):
    import adapters.telegram.ux.pending as pending

    sent = []

    async def fake_send(_message, text, keyboard=None):
        sent.append((text, keyboard))

    monkeypatch.setattr(pending, "_send", fake_send)
    monkeypatch.setattr(pending.cache, "get_cron_tasks", lambda _user_id: [])

    chat = type("Chat", (), {"type": "private"})()
    message = type("Message", (), {"chat": chat, "text": "  Morning   digest  "})()
    update = type(
        "Update",
        (),
        {
            "effective_message": message,
            "effective_user": type("User", (), {"id": 1, "language_code": "en"})(),
        },
    )()
    context = type("Context", (), {"user_data": {"ux_pending": {"kind": "cron_name"}}})()

    with pytest.raises(pending.ApplicationHandlerStop):
        asyncio.run(pending.handle_pending_input(update, context))

    assert context.user_data["cron_draft"]["name"] == "Morning digest"
    assert context.user_data["ux_pending"] == {"kind": "cron_expression"}
    assert "ux:cron:cancel" in _callbacks(sent[-1][1])


def test_retry_message_builder_does_not_duplicate_persisted_user_turn(monkeypatch):
    run = importlib.import_module("adapters.telegram.handlers.messages.chat.run")

    monkeypatch.setattr(run, "get_system_prompt", lambda *_args: "system")
    monkeypatch.setattr(run, "format_memories_for_prompt", lambda *_args: "")
    monkeypatch.setattr(run, "get_datetime_prompt", lambda: "time")
    monkeypatch.setattr(run, "build_latex_guidance", lambda: "")
    req = {
        "user_id": 1,
        "persona_name": "default",
        "user_content": "hello",
        "conversation": [{"role": "user", "content": "hello"}],
        "retry_existing": True,
    }

    messages = run._build_messages(req)
    assert [message["role"] for message in messages].count("user") == 1


def test_queue_mode_does_not_cancel_active_response(monkeypatch):
    run = importlib.import_module("adapters.telegram.handlers.messages.chat.run")
    calls = []

    monkeypatch.setattr(
        run,
        "cancel_user_responses",
        lambda *args, **kwargs: calls.append((args, kwargs)) or ["active"],
    )

    assert run._cancel_previous_responses(10, 20, {"busy_mode": "queue"}, "ctx") == []
    assert calls == []

    assert run._cancel_previous_responses(10, 20, {"busy_mode": "interrupt"}, "ctx") == ["active"]
    assert calls == [((10, 20), {"platform": "telegram"})]


def test_cron_command_is_registered():
    from adapters.telegram.commands import get_command

    command = get_command("cron")
    assert command is not None
    assert command.category == "Automation"


def test_group_api_key_is_not_saved(monkeypatch):
    import adapters.telegram.commands.settings.core as core

    saved: list[tuple] = []

    class Chat:
        type = "group"

        async def send_message(self, *_args, **_kwargs):
            return None

    class Message:
        chat = Chat()
        from_user = type("User", (), {"language_code": "en"})()
        deleted = False

        async def delete(self):
            self.deleted = True

    message = Message()
    monkeypatch.setattr(core, "update_user_setting", lambda *args: saved.append(args))
    result = asyncio.run(core.set_api_key_secure(message, user_id=1, value="secret-key"))
    assert result == []
    assert saved == []
    assert message.deleted is True


def test_private_api_key_is_deleted_persisted_and_verified(monkeypatch):
    import adapters.telegram.commands.settings.core as core

    events = []

    class Status:
        pass

    class Chat:
        type = "private"

        async def send_message(self, *_args, **_kwargs):
            events.append("status")
            return Status()

    class Message:
        chat = Chat()
        from_user = type("User", (), {"language_code": "zh"})()

        async def delete(self):
            events.append("delete")

    async def fake_edit(*_args, **_kwargs):
        events.append("verified")

    monkeypatch.setattr(core, "update_user_setting", lambda *_args: events.append("save"))
    monkeypatch.setattr(core, "sync_to_database", lambda: events.append("sync"))
    monkeypatch.setattr(core, "fetch_models_for_user", lambda _user_id: ["model-a"])
    monkeypatch.setattr(core, "edit_rich_text", fake_edit)

    models = asyncio.run(core.set_api_key_secure(Message(), user_id=1, value="secret-key"))
    assert models == ["model-a"]
    assert events == ["delete", "status", "save", "sync", "verified"]
