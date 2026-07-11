"""Telegram tool activity should follow the assistant response timeline."""

from __future__ import annotations

import asyncio
import importlib


class _SentMessage:
    def __init__(self, text: str, events: list):
        self.text = text
        self.events = events
        self.deleted = False
        self.reply_markup = None

    async def edit_text(self, text: str, **kwargs):
        self.text = text
        self.reply_markup = kwargs.get("reply_markup", self.reply_markup)
        self.events.append(("edit", self, text))

    async def edit_reply_markup(self, *, reply_markup=None):
        self.reply_markup = reply_markup
        self.events.append(("markup", self, reply_markup))

    async def delete(self):
        self.deleted = True
        self.events.append(("delete", self, ""))


class _Chat:
    type = "private"

    def __init__(self, events: list):
        self.events = events

    async def send_message(self, text: str, **_kwargs):
        sent = _SentMessage(text, self.events)
        self.events.append(("send", sent, text))
        return sent


class _IncomingMessage:
    message_id = 10
    business_connection_id = None
    direct_messages_topic = None
    message_thread_id = None

    def __init__(self, events: list):
        self.events = events
        self.chat = _Chat(events)

    async def reply_text(self, text: str, **kwargs):
        sent = _SentMessage(text, self.events)
        sent.reply_markup = kwargs.get("reply_markup")
        self.events.append(("send", sent, text))
        return sent


def test_tool_rounds_are_retained_between_assistant_segments(monkeypatch):
    render = importlib.import_module("adapters.telegram.handlers.messages.chat.render")
    monkeypatch.setattr(render, "TELEGRAM_NATIVE_DRAFTS", False)

    async def no_rich_message(*_args, **_kwargs):
        return False

    monkeypatch.setattr(render, "send_rich_text", no_rich_message)
    events = []
    incoming = _IncomingMessage(events)
    update = type(
        "Update",
        (),
        {
            "effective_message": incoming,
            "effective_user": type("User", (), {"id": 1, "language_code": "en"})(),
            "effective_chat": type("EffectiveChat", (), {"id": 1, "type": "private"})(),
        },
    )()
    context = type("Context", (), {"user_data": {}})()

    async def run():
        runtime = await render.setup_render_runtime(update, context, None, "test", tool_progress_mode="full")
        await runtime.stream_update("First assistant segment ▌")
        await runtime.render_pump.drain()
        await runtime.prepare_tool_boundary("First assistant segment")

        runtime.tool_event_callback({"type": "tool_batch_start", "tool_names": ["search"]})
        runtime.tool_event_callback({"type": "tool_start", "tool_name": "search"})
        runtime.tool_event_callback({"type": "tool_end", "tool_name": "search", "ok": True})
        runtime.tool_event_callback({"type": "tool_batch_end"})
        await asyncio.sleep(0)
        await runtime.render_pump.drain()

        await runtime.stream_update("Second assistant segment ▌")
        await runtime.render_pump.drain()
        await runtime.prepare_tool_boundary("Second assistant segment")

        runtime.tool_event_callback({"type": "tool_batch_start", "tool_names": ["terminal"]})
        runtime.tool_event_callback({"type": "tool_end", "tool_name": "terminal", "ok": True})
        runtime.tool_event_callback({"type": "tool_batch_end"})
        await asyncio.sleep(0)
        await runtime.render_pump.drain()

        await runtime.stream_update("Final assistant segment ▌")
        await runtime.render_pump.drain()
        await runtime.clear_tool_status()
        runtime.status_seed_task.cancel()
        await runtime.render_pump.stop()
        return runtime

    runtime = asyncio.run(run())
    sent = [item for item in events if item[0] == "send"]
    assert len(sent) == 5
    assert "First assistant segment" in sent[0][2]
    assert "Searching" in sent[1][2]
    assert "Second assistant segment" in sent[2][2]
    assert "Running command" in sent[3][2]
    assert "Final assistant segment" in sent[4][2]
    assert len(runtime.state.tool_messages) == 2
    assert all(not message.deleted for message in runtime.state.tool_messages)


def test_generation_persists_all_interleaved_assistant_segments(monkeypatch):
    generate = importlib.import_module("adapters.telegram.handlers.messages.chat.generate")
    tools_module = importlib.import_module("infrastructure.tools")

    class ToolCall:
        id = "call-1"
        name = "search"
        arguments = '{"query":"example"}'

    responses = [
        ("I will check that first.", {}, 0.0, "tool_calls", "", [ToolCall()]),
        ("The result confirms it.", {}, 0.0, "stop", "", []),
    ]

    async def fake_stream(*_args, **_kwargs):
        return responses.pop(0)

    async def fake_process(*_args, **_kwargs):
        return [{"role": "tool", "tool_call_id": "call-1", "content": "ok"}]

    class Pump:
        async def drain(self):
            return None

    class Runtime:
        render_pump = Pump()
        tool_event_callback = None

        def __init__(self):
            self.boundaries = []

        async def prepare_tool_boundary(self, text):
            self.boundaries.append(text)
            return True

        async def stream_update(self, _text):
            return True

        async def status_update(self, _text):
            return True

    runtime = Runtime()
    monkeypatch.setattr(generate, "stream_response", fake_stream)
    monkeypatch.setattr(tools_module, "get_all_tools", lambda **_kwargs: [{"type": "function"}])
    monkeypatch.setattr(tools_module, "process_tool_calls", fake_process)

    result = asyncio.run(generate.generate_with_tools(
        client=object(),
        messages=[{"role": "user", "content": "question"}],
        settings={"model": "test", "temperature": 0.2},
        user_id=1,
        ctx="test",
        runtime=runtime,
    ))
    assert runtime.boundaries == ["I will check that first."]
    assert result["display_final"] == "The result confirms it."
    assert result["final_text"] == "I will check that first.\n\nThe result confirms it."
