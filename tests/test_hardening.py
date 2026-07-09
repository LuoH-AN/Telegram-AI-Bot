"""Tests for delivery/shutdown hardening (L2, L3)."""

from __future__ import annotations

import asyncio

from adapters.telegram.rate.item import QueueItem
from adapters.telegram.rate.limiter import QueuedRateLimiter


def _make_item(loop, **kw):
    base = dict(
        ready_at=loop.time(),
        priority=10,
        sequence=1,
        callback=lambda: None,
        args=(),
        kwargs={},
        future=loop.create_future(),
        endpoint="sendMessage",
        chat_key=1,
    )
    base.update(kw)
    return QueueItem(**base)


def test_in_flight_futures_cancelled_on_shutdown():
    """L2: shutdown cancels in-flight (already-popped) items' futures, not just queued ones."""
    lim = QueuedRateLimiter()

    async def run():
        await lim.initialize()
        item = _make_item(asyncio.get_running_loop())
        lim._in_flight[id(item)] = item  # simulate a popped, dispatched item
        await lim.shutdown()
        return item

    item = asyncio.run(run())
    assert item.future.cancelled()
    assert not lim._in_flight


class _FakeBotMessage:
    def __init__(self, *, delete_raises=False):
        self.delete_raises = delete_raises
        self.deleted = False

    async def delete(self):
        if self.delete_raises:
            raise RuntimeError("message to delete not found")
        self.deleted = True


class _State:
    def __init__(self, bot_message):
        self.bot_message = bot_message
        self.final_delivery_confirmed = False
        self.user_message_persisted = True


class _Runtime:
    def __init__(self, bot_message):
        self.state = _State(bot_message)

        class _Outbound:
            async def deliver_final(self, text):
                return True

        self.outbound = _Outbound()

    class _Pump:
        async def drain(self):
            pass

        async def stop(self):
            pass

    render_pump = _Pump()
    status_seed_task = None


def test_empty_response_delete_failure_does_not_break_delivery():
    """L3: a failing placeholder delete on an empty response must not flip final_delivery_confirmed."""
    from adapters.telegram.handlers.messages.chat.save import deliver_and_persist

    bot_message = _FakeBotMessage(delete_raises=True)
    runtime = _Runtime(bot_message)
    runtime.state.bot_message = bot_message

    req = {"session_id": 1, "save_msg": None, "ctx": "u1", "persona_name": "default",
           "user_id": 1, "settings": {"model": "m"}}
    generated = {
        "display_final": "(Empty response)", "thinking_block": None,
        "final_text": "(Empty response)", "reasoning_content": None,
        "total_prompt_tokens": 0, "total_completion_tokens": 0, "messages": [],
    }

    asyncio.run(deliver_and_persist(generated=generated, runtime=runtime, req=req, request_start=0.0))
    assert runtime.state.final_delivery_confirmed is True
    assert runtime.state.bot_message is None
