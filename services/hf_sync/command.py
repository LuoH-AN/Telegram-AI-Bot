"""Command handler for HF object storage operations."""

from __future__ import annotations

import json

from .command_help import _help_text
from .command_url import resolve_url_output
from .naming import _normalize_object_key
from .objects import (
    delete_storage_object,
    list_storage_objects,
    put_storage_file,
    put_storage_object,
)


def run_hf_sync_command(user_id: int, input_text: str) -> dict:
    stripped = (input_text or "").strip()
    if stripped.lower() in {"help", "?", ""}:
        return {"ok": True, "output": _help_text()}

    if not stripped.startswith("{"):
        return {"ok": False, "output": "Input must be JSON.\n\n" + _help_text()}

    try:
        args = json.loads(stripped)
    except Exception as exc:
        return {"ok": False, "output": f"Invalid JSON: {exc}\n\n" + _help_text()}

    action = str(args.get("action") or "list").strip().lower()
    path = args.get("path")
    key = args.get("key")
    name = args.get("name")  # backward compatibility
    encrypt = bool(args.get("encrypt", True))
    content_b64 = str(args.get("content_b64") or "").strip()
    text_payload = str(args.get("text") or "")

    object_key = _normalize_object_key(str(key or name or path or "object.dat"))
    if action == "upload":
        result = put_storage_file(
            user_id,
            file_path=str(path or ""),
            name=object_key,
            encrypt=encrypt,
        )
        ok = bool(result.get("ok"))
        output = json.dumps(result, ensure_ascii=False, indent=2)
    elif action == "upload_text":
        result = put_storage_object(
            user_id,
            data=text_payload.encode("utf-8"),
            name=object_key,
            filename=(object_key.rsplit("/", 1)[-1] or "text.txt"),
            content_type="text/plain; charset=utf-8",
            encrypt=encrypt,
        )
        ok = bool(result.get("ok"))
        output = json.dumps(result, ensure_ascii=False, indent=2)
    elif action == "upload_b64":
        import base64

        try:
            payload = base64.b64decode(content_b64)
        except Exception as exc:
            return {"ok": False, "output": f"Invalid content_b64: {exc}"}
        result = put_storage_object(
            user_id,
            data=payload,
            name=object_key,
            filename=(object_key.rsplit("/", 1)[-1] or "blob.dat"),
            content_type=str(args.get("content_type") or "application/octet-stream"),
            encrypt=encrypt,
        )
        ok = bool(result.get("ok"))
        output = json.dumps(result, ensure_ascii=False, indent=2)
    elif action == "list":
        items = list_storage_objects(user_id)
        ok = True
        output = json.dumps(items, ensure_ascii=False, indent=2)
    elif action == "delete":
        ok = delete_storage_object(user_id, name=object_key)
        output = f"Object '{object_key}' delete {'succeeded' if ok else 'failed'}."
    elif action == "url":
        items = list_storage_objects(user_id)
        ok, output = resolve_url_output(user_id, object_key, items)
    else:
        ok = False
        output = f"Unknown action: {action}\n\n{_help_text()}"

    return {"ok": ok, "output": output}
