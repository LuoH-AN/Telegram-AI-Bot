"""Group context mode (shared/individual) management for OneBot/QQ."""

from __future__ import annotations

import logging
from database.db import get_connection

from .config import logger

VALID_MODES = {"shared", "individual"}

_group_modes: dict[int, str] = {}


def load_group_modes() -> None:
    try:
        conn = get_connection()
        if conn is None:
            return
        with conn.cursor() as cur:
            cur.execute("SELECT group_id, mode FROM onebot_group_config")
            for row in cur.fetchall():
                mode = str(row["mode"]).strip().lower()
                if mode in VALID_MODES:
                    _group_modes[int(row["group_id"])] = mode
        logger.info("Loaded %d group mode config(s)", len(_group_modes))
    except Exception:
        logger.debug("onebot_group_config table not yet created, skipping load")


def get_group_mode(group_id: int) -> str:
    return _group_modes.get(group_id, "individual")


def set_group_mode(group_id: int, mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode}")
    _group_modes[group_id] = mode
    try:
        conn = get_connection()
        if conn is None:
            return
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO onebot_group_config (group_id, mode) VALUES (%s, %s) "
                "ON CONFLICT (group_id) DO UPDATE SET mode = EXCLUDED.mode, updated_at = CURRENT_TIMESTAMP",
                (group_id, mode),
            )
        conn.commit()
    except Exception:
        logger.exception("Failed to persist group mode for group %s", group_id)
