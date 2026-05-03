"""Login lifecycle methods for WeChatBotAdapter.

Split from adapter.py to keep each module under the 120-line file limit.
Provides login(), cancel_login(), relabel(), adopt_credentials_from().
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from shutil import copy2

logger = logging.getLogger(__name__)


class AdapterLifecycleMixin:
    async def login(self, *, force: bool = False) -> dict:
        async with self._get_login_lock():
            self._login_in_progress = True
            try:
                bot = self.get_bot()
                creds = bot.get_credentials()
                if creds is None or force:
                    try:
                        creds = await bot.login(force=force)
                    finally:
                        # Clear cached QR URL even on failure: a leaked stale
                        # URL would let the snapshot keep handing out an
                        # already-expired QR.
                        self._qr_url_cache = None
            finally:
                self._login_in_progress = False
        self.state_store.update_credentials(
            token=creds.token, user_id=creds.user_id, base_url=creds.base_url,
        )
        return {
            "bot_token": creds.token,
            "ilink_user_id": creds.user_id,
            "baseurl": creds.base_url,
            "account_id": creds.account_id,
        }

    def set_login_task(self, task: asyncio.Task | None) -> None:
        self._login_task = task

    def cancel_login(self) -> None:
        task = self._login_task
        self._login_task = None
        if task and not task.done():
            task.cancel()
        self._login_in_progress = False
        self._qr_url_cache = None
        if self._bot is not None:
            try:
                self._bot.stop()
            except Exception:
                pass

    def relabel(self, new_account_id: str, new_state_dir: Path) -> None:
        self.account_id = new_account_id
        self.state_dir = Path(new_state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._cred_path = self.state_dir / "credentials.json"
        self.state_store.relabel(new_account_id)
        if self._bot is not None:
            try:
                self._bot._cred_path = self._cred_path
            except Exception:
                pass

    def adopt_credentials_from(self, other) -> None:
        creds = other.get_credentials()
        if not creds:
            return
        self.state_store.update_credentials(
            token=creds.token, user_id=creds.user_id, base_url=creds.base_url,
        )
        bot = self.get_bot()
        bot._credentials = creds
        bot._base_url = creds.base_url
        try:
            if other._cred_path.exists():
                self._cred_path.parent.mkdir(parents=True, exist_ok=True)
                copy2(other._cred_path, self._cred_path)
        except Exception:
            logger.exception("Failed to copy credentials.json into %s", self._cred_path)

    def reset(self, *, clear_credentials: bool = False, clear_mappings: bool = False) -> None:
        if self._bot:
            self._bot.stop()
        self._bot = None
        self._handler_registered = False
        self._qr_url_cache = None
        if clear_credentials:
            self._cred_path.unlink(missing_ok=True)
        if clear_mappings:
            self.state_store.clear_all()
        else:
            self.state_store.clear_token()
