"""Durable registry for managed terminal sessions.

The bot process is not the owner of a background command.  A detached worker
owns the child process while this SQLite registry provides the reconnectable
control-plane state used after bot restarts.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
from pathlib import Path

from .state import TERMINAL_DIR


def database_path() -> Path:
    raw = (os.getenv("TERMINAL_STATE_DB") or "").strip()
    return Path(raw).expanduser().resolve() if raw else TERMINAL_DIR / "sessions.sqlite3"


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS terminal_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            chat_id INTEGER,
            conversation_id INTEGER,
            command TEXT NOT NULL,
            cwd TEXT NOT NULL,
            worker_pid INTEGER,
            pid INTEGER,
            status TEXT NOT NULL,
            exit_code INTEGER,
            started_at REAL NOT NULL,
            ended_at REAL,
            last_output_at REAL,
            log_file TEXT NOT NULL,
            socket_path TEXT NOT NULL,
            pty INTEGER NOT NULL DEFAULT 0,
            notify_on_exit INTEGER NOT NULL DEFAULT 0,
            delivery_status TEXT NOT NULL DEFAULT 'pending',
            delivery_attempts INTEGER NOT NULL DEFAULT 0,
            delivery_error TEXT,
            claimed_at REAL,
            delivered_at REAL,
            completion_response TEXT
        )
        """
    )
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(terminal_sessions)").fetchall()
    }
    migrations = {
        "notify_on_exit": "INTEGER NOT NULL DEFAULT 0",
        "delivery_status": "TEXT NOT NULL DEFAULT 'pending'",
        "delivery_attempts": "INTEGER NOT NULL DEFAULT 0",
        "delivery_error": "TEXT",
        "claimed_at": "REAL",
        "delivered_at": "REAL",
        "completion_response": "TEXT",
    }
    for column, definition in migrations.items():
        if column not in existing:
            try:
                conn.execute(f"ALTER TABLE terminal_sessions ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_terminal_sessions_scope "
        "ON terminal_sessions(user_id, conversation_id, started_at DESC)"
    )
    return conn


def create_session(record: dict) -> None:
    fields = (
        "session_id", "user_id", "chat_id", "conversation_id", "command", "cwd",
        "worker_pid", "pid", "status", "exit_code", "started_at", "ended_at",
        "last_output_at", "log_file", "socket_path", "pty",
        "notify_on_exit", "delivery_status", "delivery_attempts", "delivery_error",
        "claimed_at", "delivered_at", "completion_response",
    )
    values = [record.get(field) for field in fields]
    with _connect() as conn:
        conn.execute(
            f"INSERT INTO terminal_sessions ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})",
            values,
        )


def update_session(session_id: str, **changes) -> None:
    allowed = {
        "worker_pid", "pid", "status", "exit_code", "ended_at", "last_output_at",
        "notify_on_exit", "delivery_status", "delivery_attempts", "delivery_error",
        "claimed_at", "delivered_at", "completion_response",
    }
    values = {key: value for key, value in changes.items() if key in allowed}
    if not values:
        return
    assignments = ", ".join(f"{key} = ?" for key in values)
    with _connect() as conn:
        conn.execute(
            f"UPDATE terminal_sessions SET {assignments} WHERE session_id = ?",
            [*values.values(), session_id],
        )


def get_session(identifier: str | int) -> dict | None:
    text = str(identifier).strip()
    if not text:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM terminal_sessions WHERE session_id = ?",
            (text,),
        ).fetchone()
        if row is None and text.isdigit():
            row = conn.execute(
                "SELECT * FROM terminal_sessions WHERE pid = ? ORDER BY started_at DESC LIMIT 1",
                (int(text),),
            ).fetchone()
    return dict(row) if row else None


def list_sessions(*, user_id: int | None = None, conversation_id: int | None = None, limit: int = 30) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(int(user_id))
    if conversation_id is not None:
        clauses.append("conversation_id = ?")
        params.append(int(conversation_id))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(200, int(limit))))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM terminal_sessions{where} ORDER BY started_at DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def mark_stale_sessions() -> None:
    """Reconcile workers that disappeared without recording a terminal state."""
    now = time.time()
    for row in list_sessions(limit=200):
        if row["status"] not in {"starting", "running"}:
            continue
        worker_pid = row.get("worker_pid")
        if worker_pid and _pid_alive(int(worker_pid)) and _worker_responsive(row):
            continue
        with _connect() as conn:
            changed = conn.execute(
                """
                UPDATE terminal_sessions
                SET status = 'lost', ended_at = ?
                WHERE session_id = ? AND status IN ('starting', 'running')
                """,
                (now, row["session_id"]),
            ).rowcount
        if not changed:
            continue
        try:
            Path(row["socket_path"]).unlink(missing_ok=True)
        except OSError:
            pass


def arm_completion_event(session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE terminal_sessions
            SET notify_on_exit = 1,
                delivery_status = CASE
                    WHEN delivery_status IN ('dismissed', 'failed') THEN 'pending'
                    ELSE delivery_status
                END,
                delivery_error = NULL
            WHERE session_id = ?
            """,
            (session_id,),
        )


def acknowledge_completion_event(session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE terminal_sessions
            SET notify_on_exit = 0, delivery_status = 'dismissed', claimed_at = NULL
            WHERE session_id = ? AND delivery_status NOT IN ('ready', 'delivered')
            """,
            (session_id,),
        )


def claim_completion_events(*, limit: int = 4, lease_seconds: int = 600) -> list[dict]:
    now = time.time()
    cutoff = now - max(60, int(lease_seconds))
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE terminal_sessions
            SET delivery_status = 'pending', claimed_at = NULL
            WHERE delivery_status = 'processing' AND claimed_at < ?
            """,
            (cutoff,),
        )
        rows = conn.execute(
            """
            SELECT * FROM terminal_sessions
            WHERE notify_on_exit = 1
              AND status IN ('completed', 'failed', 'lost')
              AND delivery_status = 'pending'
              AND chat_id IS NOT NULL
              AND conversation_id IS NOT NULL
            ORDER BY ended_at ASC, started_at ASC
            LIMIT ?
            """,
            (max(1, min(20, int(limit))),),
        ).fetchall()
        ids = [row["session_id"] for row in rows]
        for session_id in ids:
            conn.execute(
                """
                UPDATE terminal_sessions
                SET delivery_status = 'processing', claimed_at = ?,
                    delivery_attempts = delivery_attempts + 1, delivery_error = NULL
                WHERE session_id = ? AND delivery_status = 'pending'
                """,
                (now, session_id),
            )
        conn.commit()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def claim_ready_completion_events(*, limit: int = 10, lease_seconds: int = 300) -> list[dict]:
    now = time.time()
    cutoff = now - max(60, int(lease_seconds))
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE terminal_sessions
            SET delivery_status = 'ready', claimed_at = NULL
            WHERE delivery_status = 'delivering' AND claimed_at < ?
            """,
            (cutoff,),
        )
        rows = conn.execute(
            """
            SELECT * FROM terminal_sessions
            WHERE notify_on_exit = 1 AND delivery_status = 'ready'
            ORDER BY ended_at ASC, started_at ASC
            LIMIT ?
            """,
            (max(1, min(50, int(limit))),),
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                UPDATE terminal_sessions
                SET delivery_status = 'delivering', claimed_at = ?
                WHERE session_id = ? AND delivery_status = 'ready'
                """,
                (now, row["session_id"]),
            )
        conn.commit()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def claim_ready_completion_event(session_id: str) -> dict | None:
    now = time.time()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        changed = conn.execute(
            """
            UPDATE terminal_sessions
            SET delivery_status = 'delivering', claimed_at = ?
            WHERE session_id = ? AND notify_on_exit = 1 AND delivery_status = 'ready'
            """,
            (now, session_id),
        ).rowcount
        row = conn.execute(
            "SELECT * FROM terminal_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone() if changed else None
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()


def save_completion_response(session_id: str, response: str) -> None:
    update_session(
        session_id,
        completion_response=str(response),
        delivery_status="ready",
        claimed_at=None,
        delivery_error=None,
    )


def release_completion_event(session_id: str, error: str, *, max_attempts: int = 3) -> None:
    job = get_session(session_id)
    if not job:
        return
    status = "failed" if int(job.get("delivery_attempts") or 0) >= max_attempts else "pending"
    update_session(
        session_id,
        delivery_status=status,
        delivery_error=str(error)[:2000],
        claimed_at=None,
    )


def mark_completion_delivered(session_id: str) -> None:
    update_session(
        session_id,
        notify_on_exit=0,
        delivery_status="delivered",
        delivered_at=time.time(),
        claimed_at=None,
        delivery_error=None,
    )


def release_completion_delivery(session_id: str, error: str) -> None:
    update_session(
        session_id,
        delivery_status="ready",
        delivery_error=str(error)[:2000],
        claimed_at=None,
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def _worker_responsive(row: dict) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.5)
            client.connect(row["socket_path"])
            client.sendall(b'{"action":"status"}\n')
            response = b""
            while b"\n" not in response:
                part = client.recv(4096)
                if not part:
                    break
                response += part
        payload = json.loads(response.decode("utf-8").splitlines()[0])
        return bool(payload.get("ok") and payload.get("running"))
    except Exception:
        return False
