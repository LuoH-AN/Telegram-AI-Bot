"""Compatibility exports for HF dataset store.

Primary implementation lives under services.hf.store.
"""

from services.hf.store import HFDatasetStore, get_hf_dataset_store

__all__ = ["HFDatasetStore", "get_hf_dataset_store"]
