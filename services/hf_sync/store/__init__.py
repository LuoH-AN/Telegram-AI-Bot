"""HF dataset storage backend used by hf_sync."""

from .singleton import get_hf_dataset_store
from .store import HFDatasetStore

__all__ = ["HFDatasetStore", "get_hf_dataset_store"]
