"""Shared pytest fixtures.

Tests run without a live database or Telegram token: the cache manager and the
pure-function modules under test need no external services. Tests that touch
config-derived env (e.g. ADMIN_IDS) rebind via monkeypatch where required.
"""

from __future__ import annotations

import os

# Keep config side-effects deterministic for the test process. load_dotenv is a
# no-op when .env is absent; these defaults only apply if not already set.
os.environ.setdefault("DATABASE_URL", "")
