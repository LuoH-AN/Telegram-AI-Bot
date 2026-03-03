"""In-memory live log buffer for lightweight /logs endpoint."""

from __future__ import annotations

import logging
import os
import threading
from collections import deque

logger = logging.getLogger(__name__)

_MIN_BUFFER_LINES = 100
_MAX_BUFFER_LINES = 50000
_DEFAULT_BUFFER_LINES = 4000


def _resolve_buffer_lines() -> int:
    raw = (os.getenv("WEB_LOG_BUFFER_LINES") or "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_BUFFER_LINES
    except ValueError:
        value = _DEFAULT_BUFFER_LINES
    return max(_MIN_BUFFER_LINES, min(value, _MAX_BUFFER_LINES))


_BUFFER_LINES = _resolve_buffer_lines()
_LOG_BUFFER: deque[str] = deque(maxlen=_BUFFER_LINES)
_BUFFER_LOCK = threading.Lock()
_INSTALL_LOCK = threading.Lock()
_INSTALLED = False


class _RingLogHandler(logging.Handler):
    """Capture formatted log lines into an in-memory ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:
            line = record.getMessage()
        with _BUFFER_LOCK:
            _LOG_BUFFER.append(line)


def install_live_log_handler() -> None:
    """Install global ring log handler once."""
    global _INSTALLED
    if _INSTALLED:
        return

    with _INSTALL_LOCK:
        if _INSTALLED:
            return

        root = logging.getLogger()
        handler = _RingLogHandler(level=logging.NOTSET)

        # Reuse an existing formatter so /logs matches container log format.
        for existing in root.handlers:
            if existing.formatter:
                handler.setFormatter(existing.formatter)
                break
        if handler.formatter is None:
            handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

        root.addHandler(handler)
        _INSTALLED = True
        logger.info("Live log ring buffer enabled (size=%d)", _BUFFER_LINES)


def get_live_logs_text(*, lines: int = 500) -> str:
    """Return the latest log lines as plain text."""
    try:
        requested = int(lines)
    except (TypeError, ValueError):
        requested = 500
    limit = max(1, min(requested, _BUFFER_LINES))

    with _BUFFER_LOCK:
        if not _LOG_BUFFER:
            return "(no logs yet)\n"
        tail = list(_LOG_BUFFER)[-limit:]
    return "\n".join(tail) + "\n"
