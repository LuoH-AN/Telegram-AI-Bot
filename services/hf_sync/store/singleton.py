"""Store singleton provider."""

from __future__ import annotations

import threading

from .store import HFDatasetStore

_store_lock = threading.Lock()
_store: HFDatasetStore | None = None


def get_hf_dataset_store() -> HFDatasetStore:
    """Return singleton HF dataset store."""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            _store = HFDatasetStore()
    return _store
