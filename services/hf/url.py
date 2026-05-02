"""URL resolution branch for HF object commands."""

from __future__ import annotations

import json

from .store import get_hf_dataset_store


def resolve_url_output(user_id: int, object_key: str, items: list[dict]) -> tuple[bool, str]:
    del user_id
    store = get_hf_dataset_store()
    match = next(
        (item for item in items if str(item.get("object_name") or "") == object_key),
        None,
    )
    if match is None:
        repo_url = store.resolve_repo_url(object_key)
        if not repo_url:
            return False, f"Object '{object_key}' not found."
        return True, json.dumps({"repo_url": repo_url}, ensure_ascii=False, indent=2)

    encrypted = bool(match.get("encrypted"))
    payload = {
        "repo_url": (
            store.resolve_repo_url(str(match.get("content_path") or ""))
            if not encrypted
            else None
        ),
    }
    return True, json.dumps(payload, ensure_ascii=False, indent=2)
