"""Object storage facade."""

from __future__ import annotations

from .artifact import _artifact_view_url
from .index_store import _load_object_index, _save_object_index
from .object_delete import delete_storage_object
from .object_file import put_storage_file
from .object_write import put_storage_object


def list_storage_objects(user_id: int) -> list[dict]:
    return _load_object_index(user_id)
