"""Disk-based account discovery for the AccountManager."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .account import PENDING_PREFIX, WeChatAccount
from .accounts_db import migrate_db_account_key
from ..config import WECHAT_STATE_BASE, logger


def discover_existing_accounts(on_qr_url: Any | None) -> dict[str, WeChatAccount]:
    """Scan WECHAT_STATE_BASE for previously-logged-in accounts.

    Stale ``_pending_*`` directories are wiped, since they belong to a
    prior process that didn't reach the promotion step. For real account
    directories, the wxid is read from credentials.json; if the directory
    name doesn't match (e.g. legacy ``primary``), the dir is renamed and
    its DB row migrated to the wxid key.
    """
    accounts: dict[str, WeChatAccount] = {}
    base = Path(WECHAT_STATE_BASE)
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        return accounts

    for subdir in sorted(base.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith(PENDING_PREFIX):
            shutil.rmtree(subdir, ignore_errors=True)
            continue
        cred_file = subdir / "credentials.json"
        if not cred_file.exists():
            continue

        wxid = _read_wxid(cred_file) or subdir.name
        target_dir = subdir
        if wxid and wxid != subdir.name:
            desired = base / wxid
            if not desired.exists():
                try:
                    subdir.rename(desired)
                    target_dir = desired
                    migrate_db_account_key(subdir.name, wxid)
                except OSError:
                    logger.exception("Failed to migrate account dir %s -> %s", subdir, desired)
            else:
                logger.warning(
                    "Found duplicate WeChat account dirs %s and %s; using %s",
                    subdir.name, wxid, wxid,
                )
                continue

        account_id = wxid or subdir.name
        accounts[account_id] = WeChatAccount(
            account_id=account_id,
            state_dir=target_dir,
            on_qr_url=on_qr_url,
        )
        logger.info("Discovered WeChat account: %s", account_id)
    return accounts


def _read_wxid(cred_file: Path) -> str | None:
    try:
        data = json.loads(cred_file.read_text("utf-8"))
    except Exception:
        return None
    return (data.get("user_id") or data.get("userId") or "").strip() or None
