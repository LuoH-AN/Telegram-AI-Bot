"""Object storage facade."""

from __future__ import annotations

from .index import _load_object_index, _save_object_index
from .delete import delete_storage_object
from .file import put_storage_file
from .write import put_storage_object


def list_storage_objects(user_id: int) -> list[dict]:
    return _load_object_index(user_id)
