"""Outbound mixin: send_text, send_media, typing, reply, download.

These wrap the underlying ``WeChatBot`` instance owned by ``WeChatBotAdapter``.
Kept separate so the adapter core stays focused on the login lifecycle.
"""

from __future__ import annotations

from wechatbot.types import IncomingMessage


class AdapterOutboundMixin:
    def _seed_context_token(self, bot, user_id: str, ct: str | None) -> str | None:
        resolved = ct or self.state_store.resolve_context_token(user_id)
        if resolved:
            bot._context_tokens[user_id] = resolved
        return resolved

    async def send_text(self, user_id: str, text: str, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.send(user_id, text)

    async def send_media(self, user_id: str, content: dict, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.send_media(user_id, content)

    async def reply_to_message(self, msg: IncomingMessage, text: str) -> None:
        await self.get_bot().reply(msg, text)

    async def download_media(self, msg: IncomingMessage):
        return await self.get_bot().download(msg)

    async def send_typing(self, user_id: str, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.send_typing(user_id)

    async def stop_typing(self, user_id: str, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.stop_typing(user_id)
