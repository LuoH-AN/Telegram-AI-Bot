#!/usr/bin/env python3
"""Standalone entrypoints.launcher for the OpenWebUI-compatible OpenAPI tool server.

Usage:
    OPENAPI_TOOLS_PORT=18090 OPENAPI_TOOLS_TOKEN=secret python scripts/run_openapi_tools.py

OpenWebUI configuration:
    Settings → Tools → Add Tool Server
      URL:    http://<host>:18090
      Auth:   Bearer  <OPENAPI_TOOLS_TOKEN>
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from adapters.http.openapi_tools import build_app  # noqa: E402


def _host() -> str:
    return (os.getenv("OPENAPI_TOOLS_HOST") or "0.0.0.0").strip() or "0.0.0.0"


def _port() -> int:
    raw = (os.getenv("OPENAPI_TOOLS_PORT") or "18090").strip()
    try:
        return max(1, min(65535, int(raw)))
    except ValueError:
        return 18090


def main() -> None:
    logging.basicConfig(
        level=os.getenv("OPENAPI_TOOLS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not (os.getenv("OPENAPI_TOOLS_TOKEN") or "").strip():
        raise SystemExit("OPENAPI_TOOLS_TOKEN is required")
    app = build_app()
    host, port = _host(), _port()
    logging.getLogger(__name__).info(
        "adapters.http.openapi_tools listening on %s:%d (token=required)",
        host,
        port,
    )
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("OPENAPI_TOOLS_LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
