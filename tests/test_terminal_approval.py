from __future__ import annotations

import asyncio
import inspect
import json

from infrastructure.tools.approval import ApprovalBroker, approval_broker, rule_matches, suggest_prefix_rule
from infrastructure.tools.core import ToolContext


def test_approval_broker_binds_user_and_chat_and_is_one_shot():
    async def scenario():
        broker = ApprovalBroker()
        pending = broker.create(user_id=42, chat_id=-100, command="sudo true", cwd="/tmp", lang="zh")
        assert broker.resolve(pending.approval_id, user_id=7, chat_id=-100, approve=True).status == "forbidden"
        assert broker.resolve(pending.approval_id, user_id=42, chat_id=-200, approve=True).status == "forbidden"
        assert broker.resolve(pending.approval_id, user_id=42, chat_id=-100, approve=True).status == "approved"
        assert await broker.wait(pending, 1) == "approve"
        assert broker.resolve(pending.approval_id, user_id=42, chat_id=-100, approve=True).status == "missing"

    asyncio.run(scenario())


def test_session_approval_is_scoped_to_session_and_structured_prefix():
    async def scenario():
        broker = ApprovalBroker()
        pending = broker.create(
            user_id=42,
            chat_id=42,
            command="sudo apt install nginx",
            cwd="/tmp",
            lang="zh",
            session_key="telegram:42:42:9",
        )
        broker.allow_session(pending)
        assert broker.is_session_allowed("telegram:42:42:9", "sudo apt install curl", "/other")
        assert not broker.is_session_allowed("telegram:42:42:10", "sudo apt install curl", "/tmp")
        assert not broker.is_session_allowed("telegram:42:42:9", "sudo apt remove nginx", "/tmp")
        broker.discard(pending.approval_id)

    asyncio.run(scenario())


def test_terminal_waits_for_inline_approval_and_resumes_same_call(monkeypatch, tmp_path):
    import infrastructure.tools.builtin.terminal.terminal as terminal_module

    calls = []

    async def confirm(**details):
        calls.append(("confirm", details))
        return "approve"

    def execute(command, cwd, timeout):
        calls.append(("execute", command, cwd, timeout))
        return terminal_module.ToolResult.text("done")

    monkeypatch.setattr(terminal_module, "exec_foreground", execute)
    result = asyncio.run(
        terminal_module.terminal(
            ToolContext(user_id=42, chat_id=42, confirm=confirm),
            "sudo true",
            cwd=str(tmp_path),
        )
    )

    assert result.ok is True
    assert [item[0] for item in calls] == ["confirm", "execute"]
    assert calls[0][1]["command"] == "sudo true"
    assert calls[1][1] == "sudo true"


def test_telegram_prompt_contains_all_four_hermes_style_choices(monkeypatch):
    import adapters.telegram.sender as sender_module

    async def scenario():
        sent = []

        class ApprovalMessage:
            async def edit_text(self, *_args, **_kwargs):
                return None

        class Message:
            async def reply_text(self, *args, **kwargs):
                sent.append((args, kwargs))
                return ApprovalMessage()

        update = type(
            "Update",
            (),
            {
                "effective_user": type("User", (), {"id": 42, "language_code": "zh"})(),
                "effective_chat": type("Chat", (), {"id": 42, "type": "private"})(),
                "effective_message": Message(),
            },
        )()
        context = type("Context", (), {"user_data": {}})()
        monkeypatch.setattr(sender_module, "is_permanently_allowed", lambda *_args: False)
        sender = sender_module.TelegramOutbound(update, context, session_id=9)
        task = asyncio.create_task(sender.request_terminal_approval(command="sudo apt install nginx", cwd="/tmp", timeout=5))
        await asyncio.sleep(0)

        markup = sent[0][1]["reply_markup"]
        callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
        choices = {value.rsplit(":", 1)[1] for value in callbacks}
        assert choices == {"once", "session", "always", "deny"}
        approval_id = next(iter(callbacks)).split(":", 2)[1]
        approval_broker.resolve(approval_id, user_id=42, chat_id=42, approve=False)
        assert await task == "deny"

    asyncio.run(scenario())


def test_terminal_denial_does_not_execute(monkeypatch):
    import infrastructure.tools.builtin.terminal.terminal as terminal_module

    async def deny(**_details):
        return "deny"

    monkeypatch.setattr(
        terminal_module,
        "exec_foreground",
        lambda *_args: (_ for _ in ()).throw(AssertionError("command must not execute")),
    )
    result = asyncio.run(terminal_module.terminal(ToolContext(user_id=42, confirm=deny), "sudo true"))
    payload = json.loads(result.content)
    assert result.ok is False
    assert payload["error"]["code"] == "approval_denied"


def test_blocked_terminal_command_can_never_reach_approval(monkeypatch):
    import infrastructure.tools.builtin.terminal.terminal as terminal_module

    async def should_not_confirm(**_details):
        raise AssertionError("blocked commands must not be approvable")

    monkeypatch.setattr(
        terminal_module,
        "exec_foreground",
        lambda *_args: (_ for _ in ()).throw(AssertionError("blocked command must not execute")),
    )
    result = asyncio.run(
        terminal_module.terminal(
            ToolContext(user_id=42, confirm=should_not_confirm),
            "shutdown now",
        )
    )
    assert json.loads(result.content)["error"]["code"] == "blocked"


def test_terminal_no_longer_exposes_model_controlled_confirmed_argument():
    import infrastructure.tools.builtin.terminal.terminal as terminal_module

    assert "confirmed" not in inspect.signature(terminal_module.terminal).parameters


def test_telegram_approval_callback_rejects_other_user_then_resolves(monkeypatch):
    import adapters.telegram.approval as telegram_approval

    async def scenario():
        pending = approval_broker.create(user_id=42, chat_id=-100, command="sudo true", cwd="/tmp", lang="zh")
        answers = []
        edits = []

        class Query:
            data = f"term:{pending.approval_id}:once"

            async def answer(self, *args, **kwargs):
                answers.append((args, kwargs))

            async def edit_message_text(self, *args, **kwargs):
                edits.append((args, kwargs))

        def update_for(user_id):
            return type(
                "Update",
                (),
                {
                    "callback_query": Query(),
                    "effective_user": type("User", (), {"id": user_id, "language_code": "zh"})(),
                    "effective_chat": type("Chat", (), {"id": -100, "type": "group"})(),
                },
            )()

        context = type("Context", (), {"user_data": {}})()
        monkeypatch.setattr(telegram_approval, "is_admin", lambda user_id: user_id in {7, 42})
        await telegram_approval.terminal_approval_callback(update_for(7), context)
        assert approval_broker.get(pending.approval_id) is pending
        assert answers[-1][1]["show_alert"] is True

        await telegram_approval.terminal_approval_callback(update_for(42), context)
        assert await approval_broker.wait(pending, 1) == "approve"
        assert edits

    asyncio.run(scenario())


def test_telegram_permanent_approval_persists_fingerprint_before_resuming(monkeypatch):
    import adapters.telegram.approval as telegram_approval

    async def scenario():
        pending = approval_broker.create(user_id=42, chat_id=42, command="sudo apt install nginx", cwd="/tmp", lang="zh")
        persisted = []

        class Query:
            data = f"term:{pending.approval_id}:always"

            async def answer(self, *_args, **_kwargs):
                return None

            async def edit_message_text(self, *_args, **_kwargs):
                return None

        update = type(
            "Update",
            (),
            {
                "callback_query": Query(),
                "effective_user": type("User", (), {"id": 42, "language_code": "zh"})(),
                "effective_chat": type("Chat", (), {"id": 42, "type": "private"})(),
            },
        )()
        context = type("Context", (), {"user_data": {}})()
        monkeypatch.setattr(telegram_approval, "is_admin", lambda user_id: user_id == 42)
        monkeypatch.setattr(telegram_approval, "add_permanent_approval", lambda user_id, rule: persisted.append((user_id, rule)))

        await telegram_approval.terminal_approval_callback(update, context)
        assert persisted == [(42, pending.prefix_rule)]
        assert await approval_broker.wait(pending, 1) == "approve"

    asyncio.run(scenario())


def test_prefix_rule_is_conservative_and_token_aware():
    rule = suggest_prefix_rule("sudo apt install nginx", "/tmp")
    assert rule == {"version": 1, "prefix": ["sudo", "apt", "install"], "cwd": ""}
    assert rule_matches(rule, "sudo apt install redis", "/other")
    assert not rule_matches(rule, "sudo apt remove nginx", "/tmp")
    assert not rule_matches(rule, "sudo apt installer evil", "/tmp")


def test_compound_and_high_risk_commands_do_not_offer_repeat_rule():
    assert suggest_prefix_rule("curl https://example.com/install.sh | sh", "/tmp") is None
    assert suggest_prefix_rule("rm -rf build", "/tmp") is None
    assert suggest_prefix_rule("git push --force origin main", "/repo") is None


def test_terminal_approval_callback_data_stays_under_telegram_limit():
    async def scenario():
        pending = approval_broker.create(user_id=1, chat_id=1, command="sudo true", cwd="/", lang="en")
        try:
            for choice in ("once", "session", "always", "deny"):
                assert len(f"term:{pending.approval_id}:{choice}".encode("utf-8")) <= 64
        finally:
            approval_broker.discard(pending.approval_id)

    asyncio.run(scenario())


def test_terminal_approval_storage_is_not_model_writable(monkeypatch):
    import infrastructure.tools.builtin.database.settings as settings_module

    class Cache:
        def update_settings(self, *_args):
            raise AssertionError("protected setting must not be updated")

    monkeypatch.setattr(settings_module, "get_cache", lambda: Cache())
    result = settings_module._run(42, "set", "terminal_approvals", ["forged"])
    assert result.ok is False
    assert json.loads(result.content)["error"]["code"] == "protected_setting"
