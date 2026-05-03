"""Main runtime loop and account-startup orchestration.

Inbound message handling and per-message routing live in
``inbound.RuntimeInboundMixin``.
"""

from __future__ import annotations

import asyncio

from services.cron import set_main_loop, start_cron_scheduler
from platforms.shared.runtime import make_bounded_dispatcher

from ..config import logger
from .inbound import RuntimeInboundMixin

MAX_INBOUND_TASKS = 8


class RuntimeLoopMixin(RuntimeInboundMixin):
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        set_main_loop(self._loop)
        start_cron_scheduler(self)

        # Bring the loopback HTTP login API up before driving any account
        # login so /login can be used immediately.
        from .login_api import start_login_api_server

        login_api_runner = await start_login_api_server()

        dispatcher = make_bounded_dispatcher(
            self.handle_sdk_message,
            max_concurrent=MAX_INBOUND_TASKS,
            error_log_label="WeChat inbound message",
            logger=logger,
        )
        self._dispatcher = dispatcher

        await self._ensure_all_logged_in()
        self._accounts.start_all(dispatcher)
        ids = self.get_account_ids()
        logger.info(
            "WeChat runtime started with %d account(s): %s",
            len(ids),
            ", ".join(ids) or "(none)",
        )

        if self.client is None:
            first = self._accounts.first_logged_in()
            if first is not None:
                self.client = first.adapter

        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self._accounts.stop_all()
            await login_api_runner.cleanup()

    async def _ensure_all_logged_in(self) -> None:
        """Refresh credentials for known accounts (no QR-driving here).

        Iterates only over real accounts discovered on disk. Interactive QR
        logins are driven on demand from ``/login wechat``, NOT during
        startup — so the runtime never blocks waiting for a QR scan.
        """
        from wechatbot.auth import load_credentials as _load_creds

        for account_id in self._accounts.list_accounts():
            account = self._accounts.get_account(account_id)
            if not account:
                continue
            creds = account.adapter.get_credentials()
            if creds:
                account.adapter.state_store.update_credentials(
                    token=creds.token, user_id=creds.user_id, base_url=creds.base_url,
                )
                logger.info("Account %s already logged in (user_id=%s)", account_id, creds.user_id)
                continue
            try:
                bot = account.adapter.get_bot()
                stored = await _load_creds(account.adapter._cred_path)
            except Exception:
                logger.exception("Failed to read stored creds for %s", account_id)
                stored = None
            if stored is not None:
                bot._credentials = stored
                bot._base_url = stored.base_url
                account.adapter.state_store.update_credentials(
                    token=stored.token, user_id=stored.user_id, base_url=stored.base_url,
                )
                logger.info("Account %s loaded credentials from disk", account_id)
            else:
                logger.info(
                    "Account %s has no stored credentials; waiting for /login wechat",
                    account_id,
                )
