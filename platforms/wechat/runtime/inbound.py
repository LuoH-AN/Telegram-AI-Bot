"""Inbound message handler for WeChat runtime (extracted from loop.py)."""

from __future__ import annotations

from platforms.wechat.services.official import local_chat_id_for_wechat

from ..config import logger
from ..context import WeChatMessageContext


class RuntimeInboundMixin:
    async def handle_sdk_message(self, msg) -> None:
        from ..chat.process import process_chat_message
        from ..commands.dispatch import dispatch_command

        inbound = self._parse_sdk_message(msg)

        account_id = self._resolve_account_id(msg)
        if account_id:
            self.set_active_account(account_id)

        if not self.client:
            logger.warning("No active WeChat account, dropping message")
            return

        state = self.client.state_store.load()
        if self._should_skip_inbound_echo(inbound, str(state.user_id or "").strip()):
            return
        if self._seen_messages.remember_once(inbound.inbound_key):
            return

        peer_id = inbound.from_user_id
        if not peer_id:
            return

        context_token = getattr(msg, "_context_token", None) or str(
            getattr(msg, "raw", {}).get("context_token") or ""
        ).strip() or None

        local_user_id = self.client.state_store.remember_peer(peer_id, context_token=context_token)
        reply_to_id = peer_id
        if context_token:
            self.client.state_store.remember_context_token(reply_to_id, context_token)

        ctx = WeChatMessageContext(
            runtime=self,
            peer_id=peer_id,
            reply_to_id=reply_to_id,
            local_user_id=local_user_id,
            local_chat_id=local_chat_id_for_wechat(reply_to_id),
            is_group=False,
            group_id=None,
            context_token=context_token,
            inbound_key=inbound.inbound_key,
            _sdk_msg=msg,
        )
        if inbound.normalized_text.startswith(self.command_prefix):
            await dispatch_command(ctx, inbound.normalized_text)
            return
        await process_chat_message(self, ctx, msg)

    def _resolve_account_id(self, msg) -> str | None:
        """Pick the logged-in account that received this message.

        ``to_user_id`` is the bot's own wxid for direct messages; we look
        it up in ``_accounts`` (keyed by wxid). If it doesn't match any
        known account, fall back to the first logged-in one so legacy
        messages aren't silently dropped — but log a warning.
        """
        to_user = getattr(msg, "to_user_id", None)
        if not to_user:
            raw = getattr(msg, "raw", {}) or {}
            to_user = raw.get("to_user_id") or raw.get("toUserName") or raw.get("self_id")
        to_user = str(to_user or "").strip()

        if to_user and self._accounts.get_account(to_user) is not None:
            return to_user

        first = self._accounts.first_logged_in()
        if to_user and first is not None:
            logger.warning(
                "WeChat message to_user_id=%s did not match any known account "
                "(known: %s); falling back to %s",
                to_user, self.get_account_ids(), first.account_id,
            )
        return first.account_id if first is not None else None
