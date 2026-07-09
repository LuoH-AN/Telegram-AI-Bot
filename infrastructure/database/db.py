"""Database connection management (thread-safe pooled)."""

from __future__ import annotations

import threading

from psycopg2.extras import RealDictCursor

from infrastructure.config import DATABASE_URL

# Lazily-created pool. Reused across the asyncio thread + sync daemon + cron
# threads; psycopg2's ThreadedConnectionPool is safe for concurrent checkout.
_pool_lock = threading.Lock()
_pool = None
_MINCONN = 1
_MAXCONN = 8


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            if not DATABASE_URL:
                raise RuntimeError("DATABASE_URL is not configured")
            from psycopg2.pool import ThreadedConnectionPool

            _pool = ThreadedConnectionPool(_MINCONN, _MAXCONN, DATABASE_URL)
    return _pool


class _PooledConnection:
    """Returns a checked-out connection to the pool on close.

    psycopg2's native connection treats `with conn:` as commit-only (it does
    NOT close), so callers relying on `with get_connection() as conn:` leaked
    one connection per use. This wrapper closes on __exit__ unconditionally.
    """

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        conn = self._conn
        self._conn = None
        if conn is None:
            return
        if _pool is not None:
            try:
                _pool.putconn(conn)
                return
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass


def get_connection():
    """Check out a pooled connection. Use `with get_connection() as conn:` so it
    is returned to the pool; the wrapper returns it even on bare exception."""
    pool = _get_pool()
    conn = pool.getconn()
    return _PooledConnection(conn)


def get_dict_cursor(connection):
    """Get a cursor that returns dict-like rows."""
    return connection.cursor(cursor_factory=RealDictCursor)
