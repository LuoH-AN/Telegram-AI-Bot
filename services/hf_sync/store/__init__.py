"""HF dataset storage backend used by hf_sync."""

from .dataset import HFDatasetStore
from .instance import get_hf_dataset_store

__all__ = ["HFDatasetStore", "get_hf_dataset_store"]
