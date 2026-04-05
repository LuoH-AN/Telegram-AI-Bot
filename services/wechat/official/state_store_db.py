"""Database persistence functions for WeChat runtime state."""

from __future__ import annotations

import json

from database import get_connection, get_dict_cursor

from .constants import DEFAULT_BASE_URL
from .state_models import WeChatAccountState


def load_state_from_db(account_key: str, logger) -> WeChatAccountState:
    try:
        with get_connection() as conn:
            with get_dict_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT token, user_id, base_url, get_updates_buf, peer_map, context_tokens
                    FROM wechat_runtime_state
                    WHERE account_key = %s
                    """,
                    (account_key,),
                )
                row = cur.fetchone()
    except Exception:
        logger.exception("Failed to load WeChat state from database")
        return WeChatAccountState()
    if not row:
        return WeChatAccountState()
    return WeChatAccountState(
        token=str(row.get("token") or ""),
        user_id=str(row.get("user_id") or ""),
        base_url=str(row.get("base_url") or DEFAULT_BASE_URL),
        get_updates_buf=str(row.get("get_updates_buf") or ""),
        peer_map=coerce_map(row.get("peer_map")),
        context_tokens=coerce_map(row.get("context_tokens")),
    )


def save_state_to_db(account_key: str, state: WeChatAccountState, logger) -> None:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO wechat_runtime_state
                        (account_key, token, user_id, base_url, get_updates_buf, peer_map, context_tokens, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (account_key) DO UPDATE SET
                        token = EXCLUDED.token,
                        user_id = EXCLUDED.user_id,
                        base_url = EXCLUDED.base_url,
                        get_updates_buf = EXCLUDED.get_updates_buf,
                        peer_map = EXCLUDED.peer_map,
                        context_tokens = EXCLUDED.context_tokens,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        account_key,
                        state.token,
                        state.user_id,
                        state.base_url,
                        state.get_updates_buf,
                        json.dumps(state.peer_map, ensure_ascii=False),
                        json.dumps(state.context_tokens, ensure_ascii=False),
                    ),
                )
            conn.commit()
    except Exception:
        logger.exception("Failed to save WeChat state to database")


def coerce_map(value: object) -> dict[str, str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = {}
    elif isinstance(value, dict):
        parsed = value
    else:
        parsed = {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items() if str(k).strip() and str(v).strip()}
