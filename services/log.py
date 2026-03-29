"""Logging service for AI interactions and errors."""

import json
import logging
from datetime import datetime

from database.connection import get_connection, get_dict_cursor

logger = logging.getLogger(__name__)


def _execute_insert(sql: str, params: tuple) -> None:
    """Execute an INSERT statement with connection lifecycle management."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to record log entry")


def record_ai_interaction(
    user_id: int,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    tool_calls: list[str] | None = None,
    latency_ms: int | None = None,
    persona_name: str | None = None,
):
    """Record an AI interaction log entry."""
    _execute_insert(
        """INSERT INTO user_logs
           (user_id, log_type, model, prompt_tokens, completion_tokens,
            total_tokens, latency_ms, persona_name)
           VALUES (%s, 'ai_interaction', %s, %s, %s, %s, %s, %s)""",
        (
            user_id, model, prompt_tokens, completion_tokens, total_tokens,
            latency_ms, persona_name,
        ),
    )


def record_error(
    user_id: int,
    error_message: str,
    error_context: str | None = None,
    model: str | None = None,
    persona_name: str | None = None,
):
    """Record an error log entry."""
    _execute_insert(
        """INSERT INTO user_logs
           (user_id, log_type, error_message, error_context, model, persona_name)
           VALUES (%s, 'error', %s, %s, %s, %s)""",
        (user_id, error_message, error_context, model, persona_name),
    )


def record_web_action(
    user_id: int,
    action: str,
    detail: dict | None = None,
    persona_name: str | None = None,
):
    """Record a web UI action log entry."""
    _execute_insert(
        """INSERT INTO user_logs
           (user_id, log_type, error_message, error_context, persona_name)
           VALUES (%s, 'web_action', %s, %s, %s)""",
        (
            user_id, action,
            json.dumps(detail, ensure_ascii=False) if detail is not None else None,
            persona_name,
        ),
    )


def record_terminal_command(
    user_id: int,
    *,
    command: str,
    exit_code: int,
    cwd: str,
    stdout: str,
    stderr: str,
    blocked: bool = False,
):
    """Record one terminal command execution."""
    detail = {
        "command": command,
        "exit_code": exit_code,
        "cwd": cwd,
        "stdout": stdout,
        "stderr": stderr,
        "blocked": blocked,
    }
    _execute_insert(
        """INSERT INTO user_logs
           (user_id, log_type, error_message, error_context)
           VALUES (%s, 'terminal_command', %s, %s)""",
        (
            user_id,
            command,
            json.dumps(detail, ensure_ascii=False),
        ),
    )


def _build_where(user_id: int, log_type: str | None = None) -> tuple[str, tuple]:
    """Build a WHERE clause with optional log_type filter."""
    if log_type:
        return "WHERE user_id = %s AND log_type = %s", (user_id, log_type)
    return "WHERE user_id = %s", (user_id,)


def get_user_logs(
    user_id: int,
    log_type: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict], int]:
    """Get paginated user logs.

    Returns (rows, total_count).
    """
    offset = (page - 1) * limit
    where, params = _build_where(user_id, log_type)
    conn = get_connection()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM user_logs {where}", params)
            total = cur.fetchone()["cnt"]

            cur.execute(
                f"SELECT * FROM user_logs {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                params + (limit, offset),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows], total
    finally:
        conn.close()


def delete_log_by_id(user_id: int, log_id: int) -> bool:
    """Delete one log row by id for the current user."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_logs WHERE user_id = %s AND id = %s",
                (user_id, log_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


def delete_logs_filtered(
    user_id: int,
    log_type: str | None = None,
    before: datetime | None = None,
    after: datetime | None = None,
) -> int:
    """Delete logs by optional type/time filters and return deleted row count."""
    clauses = ["user_id = %s"]
    params: list = [user_id]
    if log_type:
        clauses.append("log_type = %s")
        params.append(log_type)
    if before is not None:
        clauses.append("created_at < %s")
        params.append(before)
    if after is not None:
        clauses.append("created_at > %s")
        params.append(after)

    query = "DELETE FROM user_logs WHERE " + " AND ".join(clauses)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            deleted = cur.rowcount
        conn.commit()
        return int(deleted)
    finally:
        conn.close()


def keep_latest_logs(
    user_id: int,
    keep_latest: int,
    log_type: str | None = None,
) -> int:
    """Keep latest N logs for user (optionally by type), delete older rows."""
    keep_latest = max(0, int(keep_latest))
    where, params = _build_where(user_id, log_type)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if keep_latest == 0:
                cur.execute(f"DELETE FROM user_logs {where}", params)
            else:
                cur.execute(
                    f"""DELETE FROM user_logs
                    {where}
                      AND id NOT IN (
                        SELECT id FROM user_logs
                        {where}
                        ORDER BY created_at DESC, id DESC
                        LIMIT %s
                      )""",
                    params + params + (keep_latest,),
                )
            deleted = cur.rowcount
        conn.commit()
        return int(deleted)
    finally:
        conn.close()
