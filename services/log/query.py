"""Read and delete operations for log rows."""

from database.db import get_connection, get_dict_cursor


def _build_where(user_id: int, log_type: str | None = None) -> tuple[str, tuple]:
    if log_type:
        return "WHERE user_id = %s AND log_type = %s", (user_id, log_type)
    return "WHERE user_id = %s", (user_id,)


def get_user_logs(user_id: int, log_type: str | None = None, page: int = 1, limit: int = 50) -> tuple[list[dict], int]:
    offset = (page - 1) * limit
    where, params = _build_where(user_id, log_type)
    conn = get_connection()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM user_logs {where}", params)
            total = cur.fetchone()["cnt"]
            cur.execute(f"SELECT * FROM user_logs {where} ORDER BY created_at DESC LIMIT %s OFFSET %s", params + (limit, offset))
            rows = cur.fetchall()
        return [dict(row) for row in rows], total
    finally:
        conn.close()


def delete_log_by_id(user_id: int, log_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_logs WHERE user_id = %s AND id = %s", (user_id, log_id))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()
