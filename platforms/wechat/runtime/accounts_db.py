"""DB helpers for the WeChat AccountManager."""

from __future__ import annotations

from database import get_connection

from ..config import logger


def migrate_db_account_key(old_key: str, new_key: str) -> None:
    """Move an account's DB row to a new account_key.

    If a row already exists at ``new_key`` (e.g. the user is re-logging-in
    a previously-known wxid), drop the old row instead of overwriting; the
    new row already holds the most recent credentials.
    """
    if old_key == new_key:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM wechat_runtime_state WHERE account_key = %s AND EXISTS "
                    "(SELECT 1 FROM wechat_runtime_state WHERE account_key = %s)",
                    (old_key, new_key),
                )
                cur.execute(
                    "UPDATE wechat_runtime_state SET account_key = %s WHERE account_key = %s",
                    (new_key, old_key),
                )
            conn.commit()
    except Exception:
        logger.exception("Failed to migrate DB account_key %s -> %s", old_key, new_key)


def delete_db_account_row(account_key: str) -> None:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM wechat_runtime_state WHERE account_key = %s",
                    (account_key,),
                )
            conn.commit()
    except Exception:
        logger.exception("Failed to delete DB account row for %s", account_key)
