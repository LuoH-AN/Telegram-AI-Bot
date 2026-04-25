"""Cleanup and retention operations for logs."""

from datetime import datetime

from database.db import get_connection

from .query import _build_where


def delete_logs_filtered(user_id: int, log_type: str | None = None, before: datetime | None = None, after: datetime | None = None) -> int:
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
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_logs WHERE " + " AND ".join(clauses), tuple(params))
            deleted = cur.rowcount
        conn.commit()
        return int(deleted)
    finally:
        conn.close()


def keep_latest_logs(user_id: int, keep_latest: int, log_type: str | None = None) -> int:
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
