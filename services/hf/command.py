"""Command handler for S3-style object storage operations."""
from __future__ import annotations

import base64
import json

from .delete import delete_storage_object
from .file import put_storage_file
from .help import _help_text
from .name import _normalize_object_key
from .object import (
    list_storage_objects,
    put_storage_object,
)
from .store import get_hf_dataset_store
from .url import resolve_url_output


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, (bool, int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _as_int(value, default: int, *, minimum: int = 1, maximum: int = 5000) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def _key_from_args(args: dict, *, include_path: bool = True) -> str:
    raw = str(args.get("key") or args.get("name") or (args.get("path") if include_path else "") or "").strip()
    return _normalize_object_key(raw, default="")


def _json_output(payload: dict | list) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


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
    encrypt = _as_bool(args.get("encrypt"), default=False)
    content_b64 = str(args.get("content_b64") or "").strip()
    text_payload = str(args.get("text") or "")
    store = get_hf_dataset_store()
    object_key = _key_from_args(args)
    if action in {"upload", "upload_text", "upload_b64"} and not object_key:
        object_key = _normalize_object_key("object.dat")

    if action == "upload":
        result = put_storage_file(
            user_id,
            file_path=str(path or ""),
            name=object_key,
            encrypt=encrypt,
        )
        ok = bool(result.get("ok"))
        output = _json_output(result)
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
        output = _json_output(result)
    elif action == "upload_b64":
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
        output = _json_output(result)
    elif action == "list":
        ok = True
        output = _json_output(list_storage_objects(user_id))
    elif action == "ls":
        if not store.enabled:
            return {"ok": False, "output": "S3 storage unavailable"}
        prefix = str(args.get("prefix") or args.get("key") or args.get("name") or args.get("dir") or args.get("folder") or "").strip()
        recursive = _as_bool(args.get("recursive"), default=True)
        limit = _as_int(args.get("limit"), 200, minimum=1, maximum=5000)
        rows = store.list_paths(prefix=prefix, limit=limit, recursive=recursive)
        ok = True
        output = _json_output(rows)
    elif action == "head":
        if not object_key:
            return {"ok": False, "output": "Missing key"}
        head = store.head(object_key) if store.enabled else None
        if head is None:
            ok = False
            output = f"Object '{object_key}' not found."
        else:
            head["repo_url"] = store.resolve_repo_url(object_key)
            ok = True
            output = _json_output(head)
    elif action == "exists":
        if not object_key:
            return {"ok": False, "output": "Missing key"}
        exists = bool(store.exists(object_key)) if store.enabled else False
        ok = True
        output = _json_output({"key": object_key, "exists": exists})
    elif action == "get_text":
        if not object_key:
            return {"ok": False, "output": "Missing key"}
        if not store.enabled:
            return {"ok": False, "output": "S3 storage unavailable"}
        encoding = str(args.get("encoding") or "utf-8")
        errors = str(args.get("errors") or "strict")
        payload = store.get_bytes(object_key, allow_plaintext=True)
        if payload is None:
            return {"ok": False, "output": f"Object '{object_key}' not found or cannot be decoded."}
        try:
            output = payload.decode(encoding, errors=errors)
            ok = True
        except Exception as exc:
            ok = False
            output = f"Decode failed for '{object_key}' with encoding={encoding}: {exc}"
    elif action == "get_b64":
        if not object_key:
            return {"ok": False, "output": "Missing key"}
        if not store.enabled:
            return {"ok": False, "output": "S3 storage unavailable"}
        payload = store.get_bytes(object_key, allow_plaintext=True)
        if payload is None:
            return {"ok": False, "output": f"Object '{object_key}' not found."}
        ok = True
        output = _json_output(
            {
                "key": object_key,
                "size": len(payload),
                "content_b64": base64.b64encode(payload).decode("ascii"),
            }
        )
    elif action == "copy":
        if not store.enabled:
            return {"ok": False, "output": "S3 storage unavailable"}
        src_key = _normalize_object_key(str(args.get("src_key") or args.get("source") or args.get("src") or ""), default="")
        dst_key = _normalize_object_key(str(args.get("dst_key") or args.get("target") or args.get("dst") or ""), default="")
        if not src_key or not dst_key:
            return {"ok": False, "output": "Missing src_key or dst_key"}
        overwrite = _as_bool(args.get("overwrite"), default=True)
        ok = store.copy(src_key, dst_key, overwrite=overwrite, commit_message=f"copy object: {src_key} -> {dst_key}")
        output = f"Copy '{src_key}' -> '{dst_key}' {'succeeded' if ok else 'failed'}."
    elif action == "move":
        if not store.enabled:
            return {"ok": False, "output": "S3 storage unavailable"}
        src_key = _normalize_object_key(str(args.get("src_key") or args.get("source") or args.get("src") or ""), default="")
        dst_key = _normalize_object_key(str(args.get("dst_key") or args.get("target") or args.get("dst") or ""), default="")
        if not src_key or not dst_key:
            return {"ok": False, "output": "Missing src_key or dst_key"}
        overwrite = _as_bool(args.get("overwrite"), default=True)
        ok = store.move(src_key, dst_key, overwrite=overwrite, commit_message=f"move object: {src_key} -> {dst_key}")
        output = f"Move '{src_key}' -> '{dst_key}' {'succeeded' if ok else 'failed'}."
    elif action == "delete":
        if not object_key:
            return {"ok": False, "output": "Missing key"}
        ok = delete_storage_object(user_id, name=object_key)
        if not ok and store.enabled:
            ok = store.delete(object_key, commit_message=f"delete object: {object_key}")
        output = f"Object '{object_key}' delete {'succeeded' if ok else 'failed'}."
    elif action == "delete_prefix":
        if not store.enabled:
            return {"ok": False, "output": "S3 storage unavailable"}
        prefix = str(args.get("prefix") or args.get("key") or args.get("name") or "").strip()
        result = store.delete_prefix(prefix, commit_message=f"delete prefix: {prefix or '/'}")
        ok = bool(result.get("ok"))
        output = _json_output(result)
    elif action == "url":
        items = list_storage_objects(user_id)
        ok, output = resolve_url_output(user_id, object_key, items)
    else:
        ok = False
        output = f"Unknown action: {action}\n\n{_help_text()}"

    return {"ok": ok, "output": output}
