"""Login session bootstrap helpers.

Two endpoints drive interactive QR login:

- ``GET /api/wechat/login`` (non-forced): "show me the current login
  state". Starts a brand new pending slot only if no real account is
  logged in and no live pending login exists.
- ``POST /api/wechat/login/new`` (forced): "start a fresh login
  regardless of state". Cancels any prior pending slot and spawns a new
  one. Existing logged-in accounts are NEVER touched.

The runtime tracks at most one pending slot at a time via
``self._pending_login_id``. Background coroutine driver lives in
``login_runner.LoginRunnerMixin``.
"""

from __future__ import annotations

from .login_runner import LoginRunnerMixin, make_pending_snapshot


class RuntimeLoginStartMixin(LoginRunnerMixin):
    def _start_login_session_sync(self, *, force: bool = False) -> dict:
        if force:
            # Cancel any pending slot first so its lingering QR cache and
            # login coroutine don't taint the next session.
            self._cancel_pending_login()
            account = self._spawn_pending_login_account()
            self._kick_login_coroutine(account)
            return make_pending_snapshot(account.adapter, self._set_login_snapshot)

        # Non-forced: prefer reporting an already-logged-in account.
        existing = self._accounts.first_logged_in()
        if existing is not None:
            creds = existing.adapter.get_credentials()
            user_id = (creds.user_id if creds else existing.account_id)
            return self._set_login_snapshot(
                logged_in=True, status="connected",
                message="WeChat is already logged in", user_id=user_id, qr_url="",
            )

        pending = self.get_pending_account()
        if pending is not None and pending.adapter.login_in_progress:
            return make_pending_snapshot(pending.adapter, self._set_login_snapshot)

        # No accounts and no live pending login — start one.
        account = self._spawn_pending_login_account()
        self._kick_login_coroutine(account)
        return make_pending_snapshot(account.adapter, self._set_login_snapshot)

    def force_new_login_sync(self) -> dict:
        with self._login_state_lock:
            self._active_qr = None
        return self._start_login_session_sync(force=True)
