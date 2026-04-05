"""Database synchronization logic."""

from __future__ import annotations

from cache.manager import cache

from .load import load_from_database
from .runtime import init_database as _init_database_runtime
from .write import sync_to_database as _sync_to_database_impl


def sync_to_database() -> None:
    _sync_to_database_impl(cache)


def init_database() -> None:
    _init_database_runtime(cache, load_from_database, sync_to_database)


__all__ = ["init_database", "sync_to_database"]
