"""Compatibility exports for HF dataset store.

Primary implementation lives under services.hf_sync.store.
"""

from services.hf_sync.store import HFDatasetStore, get_hf_dataset_store

__all__ = ["HFDatasetStore", "get_hf_dataset_store"]
