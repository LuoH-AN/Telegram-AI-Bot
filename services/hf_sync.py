"""General-purpose Hugging Face sync helpers."""

from __future__ import annotations

import io
import json
import logging
import shutil
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from hf_dataset_store import get_hf_dataset_store
from .terminal_exec import REPO_ROOT
from config import WEB_BASE_URL
from web.auth import create_artifact_token

logger = logging.getLogger(__name__)

SYNC_NAMESPACE = "sync"
OBJECT_NAMESPACE = "objects"


@dataclass(frozen=True)
class SyncTarget:
    name: str
    source_path: str
    is_dir: bool


@dataclass(frozen=True)
class ObjectRecord:
    object_name: str
    content_path: str
    meta_path: str
    content_type: str
    filename: str
    encrypted: bool
    size: int
    created_at: float


def _normalize_sync_name(name: str | None, *, default: str = "workspace") -> str:
    raw = (name or "").strip().lower().replace("\\", "/")
    if not raw:
        return default
    safe = []
    for ch in raw:
        if ch.isalnum() or ch in {"-", "_", "."}:
            safe.append(ch)
        else:
            safe.append("_")
    return "".join(safe).strip("._") or default


def _resolve_path(path: str | None) -> Path:
    raw = (path or "").strip()
    if not raw:
        return REPO_ROOT
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate.resolve()


def _target_prefix(user_id: int, sync_name: str) -> str:
    return f"{SYNC_NAMESPACE}/{user_id}/{sync_name}"


def _snapshot_id() -> str:
    return time.strftime("snap_%Y%m%d_%H%M%S")


def _object_prefix(user_id: int, object_name: str) -> str:
    return f"{OBJECT_NAMESPACE}/{user_id}/{object_name}"


def _object_index_path(user_id: int) -> str:
    return f"{OBJECT_NAMESPACE}/{user_id}/index.json"


def _default_target(path: str | None = None, *, name: str | None = None) -> SyncTarget:
    resolved = _resolve_path(path)
    target_name = _normalize_sync_name(name or resolved.name or "workspace")
    return SyncTarget(name=target_name, source_path=str(resolved), is_dir=resolved.is_dir())


def _load_object_index(user_id: int) -> list[dict]:
    store = get_hf_dataset_store()
    if not store.enabled:
        return []
    payload = store.get_json(_object_index_path(user_id), allow_plaintext=True)
    return payload if isinstance(payload, list) else []


def _save_object_index(user_id: int, items: list[dict]) -> bool:
    store = get_hf_dataset_store()
    if not store.enabled:
        return False
    return store.put_json(
        _object_index_path(user_id),
        items,
        commit_message=f"update object index: {user_id}",
        encrypt=False,
    )


def _artifact_view_url(record: ObjectRecord, *, user_id: int) -> str:
    token = create_artifact_token(
        user_id=user_id,
        path=record.content_path,
        content_type=record.content_type,
        filename=record.filename,
        encrypted=record.encrypted,
    )
    return f"{WEB_BASE_URL.rstrip('/')}/artifacts/{token}"


def put_storage_object(
    user_id: int,
    *,
    data: bytes,
    name: str,
    filename: str | None = None,
    content_type: str = "application/octet-stream",
    encrypt: bool = True,
) -> dict:
    store = get_hf_dataset_store()
    if not store.enabled:
        return {"ok": False, "message": "HF storage unavailable"}

    object_name = _normalize_sync_name(name, default="object")
    stored_filename = (filename or object_name or "object.bin").strip() or "object.bin"
    prefix = _object_prefix(user_id, object_name)
    content_path = f"{prefix}/content.bin"
    meta_path = f"{prefix}/meta.json"
    created_at = time.time()
    meta = {
        "object_name": object_name,
        "content_path": content_path,
        "meta_path": meta_path,
        "content_type": content_type,
        "filename": stored_filename,
        "encrypted": bool(encrypt),
        "size": len(data),
        "created_at": created_at,
    }

    ok = store.put_bytes(
        content_path,
        data,
        commit_message=f"put object: {object_name}",
        encrypt=encrypt,
    ) and store.put_json(
        meta_path,
        meta,
        commit_message=f"put object meta: {object_name}",
        encrypt=False,
    )
    if not ok:
        return {"ok": False, "message": f"Failed to store object '{object_name}'"}

    index = [item for item in _load_object_index(user_id) if str(item.get("object_name") or "") != object_name]
    index.insert(0, meta)
    _save_object_index(user_id, index)

    record = ObjectRecord(
        object_name=object_name,
        content_path=content_path,
        meta_path=meta_path,
        content_type=content_type,
        filename=stored_filename,
        encrypted=bool(encrypt),
        size=len(data),
        created_at=created_at,
    )
    return {
        "ok": True,
        "object_name": object_name,
        "path": content_path,
        "filename": stored_filename,
        "content_type": content_type,
        "encrypted": bool(encrypt),
        "size": len(data),
        "view_url": _artifact_view_url(record, user_id=user_id),
        "repo_url": store.resolve_repo_url(content_path) if not encrypt else None,
    }


def put_storage_file(
    user_id: int,
    *,
    file_path: str,
    name: str | None = None,
    encrypt: bool = True,
) -> dict:
    source = _resolve_path(file_path)
    if not source.exists() or not source.is_file():
        return {"ok": False, "message": f"File not found: {source}"}
    content_type = __import__("mimetypes").guess_type(str(source))[0] or "application/octet-stream"
    return put_storage_object(
        user_id,
        data=source.read_bytes(),
        name=name or source.name,
        filename=source.name,
        content_type=content_type,
        encrypt=encrypt,
    )


def list_storage_objects(user_id: int) -> list[dict]:
    return _load_object_index(user_id)


def delete_storage_object(user_id: int, *, name: str) -> bool:
    store = get_hf_dataset_store()
    if not store.enabled:
        return False
    object_name = _normalize_sync_name(name, default="object")
    index = _load_object_index(user_id)
    match = next((item for item in index if str(item.get("object_name") or "") == object_name), None)
    if not match:
        return False
    ok = store.delete(str(match.get("content_path") or ""), commit_message=f"delete object: {object_name}")
    ok = store.delete(str(match.get("meta_path") or ""), commit_message=f"delete object meta: {object_name}") and ok
    if ok:
        _save_object_index(user_id, [item for item in index if str(item.get("object_name") or "") != object_name])
    return ok


def _build_archive(target: SyncTarget) -> bytes:
    source = Path(target.source_path)
    if not source.exists():
        raise FileNotFoundError(target.source_path)

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        if target.is_dir:
            for item in source.rglob("*"):
                if item.name == ".git":
                    continue
                if any(part == ".git" for part in item.parts):
                    continue
                arcname = Path("data") / item.relative_to(source)
                tar.add(item, arcname=str(arcname), recursive=False)
        else:
            tar.add(source, arcname=str(Path("data") / source.name), recursive=False)
    return buffer.getvalue()


def _write_archive_to_target(archive_bytes: bytes, target: SyncTarget, *, destination: str | None = None) -> None:
    restore_target = _resolve_path(destination or target.source_path)
    restore_parent = restore_target.parent if not target.is_dir else restore_target
    restore_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gemen_hf_restore_") as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / "archive.tar.gz"
        archive_path.write_bytes(archive_bytes)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(temp_path)
        extracted_root = temp_path / "data"
        if target.is_dir:
            if restore_target.exists():
                shutil.rmtree(restore_target)
            restore_target.mkdir(parents=True, exist_ok=True)
            if extracted_root.exists():
                for child in extracted_root.iterdir():
                    shutil.move(str(child), restore_target / child.name)
        else:
            extracted_file = extracted_root / Path(target.source_path).name
            if not extracted_file.exists():
                candidates = list(extracted_root.iterdir()) if extracted_root.exists() else []
                if not candidates:
                    raise FileNotFoundError("archive missing file payload")
                extracted_file = candidates[0]
            restore_target.parent.mkdir(parents=True, exist_ok=True)
            if restore_target.exists():
                restore_target.unlink()
            shutil.move(str(extracted_file), restore_target)


def persist_sync_target(user_id: int, *, path: str | None = None, name: str | None = None, snapshot_id: str | None = None) -> bool:
    store = get_hf_dataset_store()
    if not store.enabled:
        return False

    target = _default_target(path, name=name)
    archive_bytes = _build_archive(target)
    snapshot = snapshot_id or _snapshot_id()
    prefix = _target_prefix(user_id, target.name)
    snapshot_prefix = f"{prefix}/snapshots/{snapshot}"
    previous_meta = store.get_json(f"{prefix}/meta.json") or {}
    previous_snapshots = list(previous_meta.get("snapshots") or [])
    if snapshot not in previous_snapshots:
        previous_snapshots.append(snapshot)
    meta = {
        "name": target.name,
        "source_path": target.source_path,
        "is_dir": target.is_dir,
        "updated_at": time.time(),
        "current_snapshot": snapshot,
        "snapshots": previous_snapshots,
    }

    ops = [
        store.put_json(f"{prefix}/meta.json", meta, commit_message=f"sync meta: {target.name}"),
        store.put_bytes(f"{prefix}/archive.tar.gz", archive_bytes, commit_message=f"sync archive: {target.name}"),
        store.put_json(f"{snapshot_prefix}/meta.json", meta, commit_message=f"sync snapshot meta: {target.name}:{snapshot}"),
        store.put_bytes(f"{snapshot_prefix}/archive.tar.gz", archive_bytes, commit_message=f"sync snapshot archive: {target.name}:{snapshot}"),
    ]
    return all(ops)


def restore_sync_target(
    user_id: int,
    *,
    name: str,
    snapshot_id: str | None = None,
    destination: str | None = None,
) -> bool:
    store = get_hf_dataset_store()
    if not store.enabled:
        return False

    sync_name = _normalize_sync_name(name)
    prefix = _target_prefix(user_id, sync_name)
    if snapshot_id:
        base = f"{prefix}/snapshots/{snapshot_id}"
        meta = store.get_json(f"{base}/meta.json")
        archive = store.get_bytes(f"{base}/archive.tar.gz")
    else:
        meta = store.get_json(f"{prefix}/meta.json")
        archive = store.get_bytes(f"{prefix}/archive.tar.gz")
    if not meta or archive is None:
        return False

    target = SyncTarget(
        name=str(meta.get("name") or sync_name),
        source_path=str(meta.get("source_path") or ""),
        is_dir=bool(meta.get("is_dir")),
    )
    _write_archive_to_target(archive, target, destination=destination)
    return True


def list_sync_snapshots(user_id: int, *, name: str) -> list[str]:
    store = get_hf_dataset_store()
    if not store.enabled:
        return []
    sync_name = _normalize_sync_name(name)
    prefix = _target_prefix(user_id, sync_name)
    meta = store.get_json(f"{prefix}/meta.json") or {}
    snapshots = [str(item).strip() for item in (meta.get("snapshots") or []) if str(item).strip()]
    current = str(meta.get("current_snapshot") or "").strip()
    if current and current not in snapshots:
        snapshots.insert(0, current)
    return snapshots


def run_hf_sync_command(user_id: int, input_text: str) -> dict:
    try:
        args = json.loads(input_text) if input_text.strip().startswith("{") else {}
    except Exception:
        args = {}

    action = str(args.get("action") or "persist").strip().lower()
    path = args.get("path")
    name = args.get("name")
    snapshot_id = args.get("snapshot_id")
    destination = args.get("destination")
    skill_name = str(args.get("skill_name") or "").strip()
    encrypt = bool(args.get("encrypt", True))
    content_b64 = str(args.get("content_b64") or "").strip()
    text_payload = str(args.get("text") or "")

    from .skills import (
        list_skill_snapshots,
        persist_skill_snapshot,
        persist_skill_state,
        restore_skill_snapshot,
    )

    if skill_name:
        if action == "persist":
            ok = persist_skill_state(user_id, skill_name)
            output = f"Skill '{skill_name}' persist {'succeeded' if ok else 'failed'}."
        elif action == "restore":
            ok = restore_skill_snapshot(user_id, skill_name, snapshot_id=snapshot_id)
            output = f"Skill '{skill_name}' restore {'succeeded' if ok else 'failed'}."
        elif action == "snapshot":
            ok = persist_skill_snapshot(user_id, skill_name, snapshot_id=snapshot_id)
            output = f"Skill '{skill_name}' snapshot {'succeeded' if ok else 'failed'}."
        elif action == "list_snapshots":
            snaps = list_skill_snapshots(user_id, skill_name)
            ok = True
            output = f"Snapshots for skill '{skill_name}': {', '.join(snaps) if snaps else 'none'}"
        else:
            ok = False
            output = f"Unknown skill sync action: {action}"
        return {"ok": ok, "output": output}

    sync_name = _normalize_sync_name(name or path or "workspace")
    if action in {"persist", "snapshot"}:
        ok = persist_sync_target(user_id, path=path, name=sync_name, snapshot_id=snapshot_id if action == "snapshot" else None)
        output = f"Sync target '{sync_name}' {action} {'succeeded' if ok else 'failed'}."
    elif action == "restore":
        ok = restore_sync_target(user_id, name=sync_name, snapshot_id=snapshot_id, destination=destination)
        output = f"Sync target '{sync_name}' restore {'succeeded' if ok else 'failed'}."
    elif action == "list_snapshots":
        snaps = list_sync_snapshots(user_id, name=sync_name)
        ok = True
        output = f"Snapshots for '{sync_name}': {', '.join(snaps) if snaps else 'none'}"
    elif action == "upload":
        result = put_storage_file(user_id, file_path=str(path or ""), name=name, encrypt=encrypt)
        ok = bool(result.get("ok"))
        output = json.dumps(result, ensure_ascii=False, indent=2)
    elif action == "upload_text":
        result = put_storage_object(
            user_id,
            data=text_payload.encode("utf-8"),
            name=name or "text",
            filename=(name or "text") + ".txt",
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
            name=name or "blob",
            filename=name or "blob.bin",
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
        ok = delete_storage_object(user_id, name=sync_name)
        output = f"Object '{sync_name}' delete {'succeeded' if ok else 'failed'}."
    elif action == "url":
        items = list_storage_objects(user_id)
        match = next((item for item in items if str(item.get("object_name") or "") == sync_name), None)
        ok = match is not None
        if ok:
            record = ObjectRecord(
                object_name=str(match["object_name"]),
                content_path=str(match["content_path"]),
                meta_path=str(match["meta_path"]),
                content_type=str(match["content_type"]),
                filename=str(match["filename"]),
                encrypted=bool(match["encrypted"]),
                size=int(match["size"]),
                created_at=float(match["created_at"]),
            )
            output = json.dumps(
                {
                    "view_url": _artifact_view_url(record, user_id=user_id),
                    "repo_url": get_hf_dataset_store().resolve_repo_url(record.content_path) if not record.encrypted else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        else:
            output = f"Object '{sync_name}' not found."
    else:
        ok = False
        output = f"Unknown sync action: {action}"

    return {"ok": ok, "output": output}
