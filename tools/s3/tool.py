"""S3 object storage tool for AI — full bucket/object CRUD."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from ..core.base import BaseTool

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {
    "create_bucket",
    "delete_bucket",
    "list_buckets",
    "head_bucket",
    "put_object",
    "get_object",
    "head_object",
    "delete_object",
    "list_objects",
    "copy_object",
    "move_object",
    "get_url",
    "url",
    "sync_from_hf",
    "sync_to_local",
    "status",
    "local_status",
}

# Per-user S3 service instances (lazy)
_s3_instances: dict[int, Any] = {}


def _get_s3(user_id: int):
    from services.s3 import S3Service, get_s3_backend
    if user_id not in _s3_instances:
        backend = get_s3_backend()
        svc = S3Service(user_id, backend)
        svc.load()
        _s3_instances[user_id] = svc
    return _s3_instances[user_id]


class S3Tool(BaseTool):
    @property
    def name(self) -> str:
        return "s3"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "s3",
                    "description": (
                        "S3-compatible object storage. Manage buckets and store/retrieve/delete objects. "
                        "Buckets hold objects identified by keys (like paths). "
                        "Supports encryption, metadata, presigned URLs, and copy/move operations."
                    ),
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(_VALID_ACTIONS),
                    "description": "Action to perform",
                },
                # Bucket args
                "bucket": {
                    "type": "string",
                    "description": "Bucket name (required for most bucket/object actions)",
                },
                "buckets": {
                    "type": "string",
                    "description": "Comma-separated list of bucket names for create_bucket",
                },
                # Object args
                "key": {
                    "type": "string",
                    "description": "Object key (e.g. 'images/cover.png')",
                },
                "text": {
                    "type": "string",
                    "description": "Text content to upload as an object",
                },
                "content_b64": {
                    "type": "string",
                    "description": "Base64-encoded binary content to upload",
                },
                "content_type": {
                    "type": "string",
                    "description": "MIME type for the object (default: application/octet-stream or text/plain for text)",
                },
                "metadata": {
                    "type": "object",
                    "description": "Key-value metadata to store with the object",
                },
                "encrypt": {
                    "type": "boolean",
                    "description": "Encrypt object content (default: true, encryption is always applied when HF_DATASET_ENCRYPTION_KEY is set)",
                },
                # List args
                "prefix": {
                    "type": "string",
                    "description": "Object key prefix filter for list operations",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results for list operations (default: 200, max: 5000)",
                },
                # Copy/move args
                "src_bucket": {
                    "type": "string",
                    "description": "Source bucket for copy/move",
                },
                "src_key": {
                    "type": "string",
                    "description": "Source object key for copy/move",
                },
                "dst_bucket": {
                    "type": "string",
                    "description": "Destination bucket for copy/move",
                },
                "dst_key": {
                    "type": "string",
                    "description": "Destination object key for copy/move",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Allow overwriting existing objects for copy/move (default: true)",
                },
                # URL args
                "expires": {
                    "type": "integer",
                    "description": "URL expiration time in seconds (default: 3600, max: 86400)",
                },
            },
            "required": ["action"],
        }

    def get_instruction(self) -> str:
        return (
            "\nS3 tool usage guidelines:\n"
            "- Always create a bucket before uploading objects: s3 action='create_bucket' bucket='my-bucket'\n"
            "- Use descriptive bucket names and object keys (e.g. 'documents/report.pdf', 'images/avatar.png')\n"
            "- Use content_type='text/plain' when uploading text content\n"
            "- Set encrypt=true for sensitive data (requires encryption key configured)\n"
            "- Use list_objects to explore bucket contents before get_object\n"
            "- Use get_url to generate temporary access links for downloads\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        action = str(arguments.get("action") or "").strip().lower()
        if action not in _VALID_ACTIONS:
            return f"Error: unknown action '{action}'. Allowed: {', '.join(sorted(_VALID_ACTIONS))}"

        # Aliases
        if action == "url":
            action = "get_url"

        svc = _get_s3(user_id)

        try:
            if action == "status":
                return self._status(svc)
            if action == "create_bucket":
                return self._create_bucket(svc, arguments)
            if action == "delete_bucket":
                return self._delete_bucket(svc, arguments)
            if action == "list_buckets":
                return self._list_buckets(svc)
            if action == "head_bucket":
                return self._head_bucket(svc, arguments)
            if action == "put_object":
                return self._put_object(svc, arguments)
            if action == "get_object":
                return self._get_object(svc, arguments)
            if action == "head_object":
                return self._head_object(svc, arguments)
            if action == "delete_object":
                return self._delete_object(svc, arguments)
            if action == "list_objects":
                return self._list_objects(svc, arguments)
            if action == "copy_object":
                return self._copy_object(svc, arguments)
            if action == "move_object":
                return self._move_object(svc, arguments)
            if action == "get_url":
                return self._get_url(svc, arguments)
            if action == "sync_from_hf":
                return self._sync_from_hf(svc, user_id)
            if action == "sync_to_local":
                return self._sync_to_local(svc, user_id)
            if action == "local_status":
                return self._local_status(svc, user_id)
            return f"Error: unhandled action '{action}'"
        except Exception as exc:
            logger.exception("S3 tool action '%s' failed for user %d", action, user_id)
            return f"Error: action '{action}' failed - {exc}"

    def _status(self, svc) -> str:
        buckets = svc.list_buckets()
        backend = svc._backend
        lines = [
            f"S3 Storage (HF Backend)",
            f"  HF Enabled: {backend.enabled}",
            f"  Total buckets: {len(buckets)}",
        ]
        total_objects = 0
        total_size = 0
        for b in buckets:
            total_objects += b["object_count"]
            total_size += b["total_size"]
        lines.append(f"  Total objects: {total_objects}")
        lines.append(f"  Total size: {_format_bytes(total_size)}")
        return "\n".join(lines)

    def _create_bucket(self, svc, args: dict) -> str:
        raw = str(args.get("bucket") or args.get("buckets") or "").strip()
        if not raw:
            return "Error: bucket name required"
        results = []
        for name in raw.split(","):
            name = name.strip()
            if not name:
                continue
            r = svc.create_bucket(name)
            results.append(f"  {'OK' if r['ok'] else 'FAIL'}: {name}" + (f" - {r.get('error', '')}" if not r['ok'] else ""))
        return "\n".join(results) or "No buckets specified"

    def _delete_bucket(self, svc, args: dict) -> str:
        name = str(args.get("bucket") or "").strip()
        if not name:
            return "Error: bucket name required"
        r = svc.delete_bucket(name)
        if r["ok"]:
            return f"Deleted bucket '{name}'"
        return f"Failed to delete bucket '{name}': {r.get('error', 'unknown error')}"

    def _list_buckets(self, svc) -> str:
        buckets = svc.list_buckets()
        if not buckets:
            return "No buckets. Create one with create_bucket action."
        lines = [f"Buckets ({len(buckets)}):"]
        for b in buckets:
            lines.append(f"  {b['name']}  objects={b['object_count']}  size={_format_bytes(b['total_size'])}  created={_format_time(b['created_at'])}")
        return "\n".join(lines)

    def _head_bucket(self, svc, args: dict) -> str:
        name = str(args.get("bucket") or "").strip()
        if not name:
            return "Error: bucket name required"
        info = svc.head_bucket(name)
        if not info:
            return f"Bucket '{name}' not found"
        lines = [f"Bucket: {info['name']}", f"  Objects: {info['object_count']}", f"  Size: {_format_bytes(info['total_size'])}", f"  Created: {_format_time(info['created_at'])}"]
        return "\n".join(lines)

    def _put_object(self, svc, args: dict) -> str:
        bucket = str(args.get("bucket") or "").strip()
        key = str(args.get("key") or "").strip()
        text = args.get("text")
        content_b64 = args.get("content_b64")
        encrypt = bool(args.get("encrypt", False))

        if not bucket:
            return "Error: bucket name required"
        if not key:
            return "Error: object key required"

        # Build data from text or base64
        if content_b64:
            import base64
            try:
                data = base64.b64decode(content_b64)
            except Exception as exc:
                return f"Error: invalid content_b64 - {exc}"
        elif text is not None:
            data = str(text).encode("utf-8")
        else:
            return "Error: either text or content_b64 required"

        content_type = str(args.get("content_type") or "").strip()
        if not content_type:
            content_type = "text/plain; charset=utf-8" if text is not None else "application/octet-stream"

        metadata = args.get("metadata") or {}

        r = svc.put_object(bucket, key, data, content_type=content_type, metadata=metadata, encrypt=encrypt)
        if r["ok"]:
            return f"Stored: {bucket}/{key} ({_format_bytes(r['size'])}) content_type={content_type}"
        return f"Failed to store object: {r.get('error', 'unknown error')}"

    def _get_object(self, svc, args: dict) -> str:
        bucket = str(args.get("bucket") or "").strip()
        key = str(args.get("key") or "").strip()
        if not bucket or not key:
            return "Error: bucket and key required"
        r = svc.get_object(bucket, key)
        if not r["ok"]:
            return f"Error: {r.get('error', 'object not found')}"
        data = r.get("data", b"")
        preview = data[:500].decode("utf-8", errors="replace")
        if len(data) > 500:
            preview += f"\n... ({_format_bytes(len(data))} total)"
        return f"{bucket}/{key} [{_format_bytes(len(data))}] content_type={r.get('content_type', 'unknown')}\n\n{preview}"

    def _head_object(self, svc, args: dict) -> str:
        bucket = str(args.get("bucket") or "").strip()
        key = str(args.get("key") or "").strip()
        if not bucket or not key:
            return "Error: bucket and key required"
        info = svc.head_object(bucket, key)
        if not info:
            return f"Object {bucket}/{key} not found"
        lines = [f"Object: {info['key']}", f"  Size: {_format_bytes(info['size'])}", f"  Content-Type: {info['content_type']}", f"  Modified: {_format_time(info['mtime'])}", f"  Encrypted: {info['encrypted']}"]
        if info.get("metadata"):
            lines.append(f"  Metadata: {json.dumps(info['metadata'], ensure_ascii=False)}")
        return "\n".join(lines)

    def _delete_object(self, svc, args: dict) -> str:
        bucket = str(args.get("bucket") or "").strip()
        key = str(args.get("key") or "").strip()
        if not bucket or not key:
            return "Error: bucket and key required"
        r = svc.delete_object(bucket, key)
        if r["ok"]:
            return f"Deleted: {bucket}/{key}"
        return f"Failed to delete: {r.get('error', 'unknown error')}"

    def _list_objects(self, svc, args: dict) -> str:
        bucket = str(args.get("bucket") or "").strip()
        prefix = str(args.get("prefix") or "").strip()
        limit = max(1, min(int(args.get("limit") or 200), 5000))
        if not bucket:
            return "Error: bucket name required"
        objects = svc.list_objects(bucket, prefix=prefix, limit=limit)
        if not objects:
            return f"No objects in {bucket}" + (f" with prefix '{prefix}'" if prefix else "")
        lines = [f"Objects in {bucket} ({len(objects)}):"]
        for obj in objects:
            meta = ""
            if obj.get("metadata"):
                meta = f"  meta={json.dumps(obj['metadata'], ensure_ascii=False)}"
            lines.append(f"  {obj['key']}  {_format_bytes(obj['size'])}  {obj['content_type']}{meta}")
        return "\n".join(lines)

    def _copy_object(self, svc, args: dict) -> str:
        src_b = str(args.get("src_bucket") or "").strip()
        src_k = str(args.get("src_key") or "").strip()
        dst_b = str(args.get("dst_bucket") or "").strip()
        dst_k = str(args.get("dst_key") or "").strip()
        overwrite = bool(args.get("overwrite", True))
        if not src_b or not src_k or not dst_b or not dst_k:
            return "Error: src_bucket, src_key, dst_bucket, and dst_key required"
        r = svc.copy_object(src_b, src_k, dst_b, dst_k, overwrite=overwrite)
        if r["ok"]:
            return f"Copied: {src_b}/{src_k} -> {dst_b}/{dst_k}"
        return f"Copy failed: {r.get('error', 'unknown error')}"

    def _move_object(self, svc, args: dict) -> str:
        src_b = str(args.get("src_bucket") or "").strip()
        src_k = str(args.get("src_key") or "").strip()
        dst_b = str(args.get("dst_bucket") or "").strip()
        dst_k = str(args.get("dst_key") or "").strip()
        overwrite = bool(args.get("overwrite", True))
        if not src_b or not src_k or not dst_b or not dst_k:
            return "Error: src_bucket, src_key, dst_bucket, and dst_key required"
        r = svc.move_object(src_b, src_k, dst_b, dst_k, overwrite=overwrite)
        if r["ok"]:
            return f"Moved: {src_b}/{src_k} -> {dst_b}/{dst_k}"
        return f"Move failed: {r.get('error', 'unknown error')}"

    def _local_status(self, svc, user_id: int) -> str:
        from services.s3.local_backend import LocalS3Backend
        backend = LocalS3Backend()
        objects = backend.list_all_objects(user_id)
        total_size = 0
        # Estimate size from storage paths
        lines = [
            f"Local S3 Storage",
            f"  Encrypted: {backend.encryption_available}",
            f"  Total objects: {len(objects)}",
        ]
        # Group by bucket
        buckets: dict[str, int] = {}
        for path, bucket in objects:
            buckets[bucket] = buckets.get(bucket, 0) + 1
        for b, count in sorted(buckets.items()):
            lines.append(f"  Bucket '{b}': {count} objects")
        return "\n".join(lines)

    def _sync_from_hf(self, svc, user_id: int) -> str:
        """Sync all HF S3 data to local encrypted storage."""
        from services.s3.local_backend import LocalS3Backend
        local_backend = LocalS3Backend()

        buckets = svc.list_buckets()
        if not buckets:
            return "No buckets to sync"

        total = 0
        errors = 0
        for b in buckets:
            bucket_name = b["name"]
            # List all objects in this bucket via HF backend
            # We need to use HF-specific listing since S3Service only shows indexed objects
            objects = svc.list_objects(bucket_name, prefix="", limit=5000)
            for obj in objects:
                key = obj.get("key", "")
                if not key:
                    continue
                try:
                    r = svc.get_object(bucket_name, key)
                    if r.get("ok") and r.get("data"):
                        data = r["data"]
                        # Store to local with encryption
                        ok = local_backend.put_object(
                            user_id,
                            f"{bucket_name}/{key}",
                            data,
                            encrypt=True,
                        )
                        if ok:
                            total += 1
                        else:
                            errors += 1
                except Exception as exc:
                    errors += 1
                    logger.warning("sync_from_hf failed for %s/%s: %s", bucket_name, key, exc)

        return f"Sync complete: {total} objects synced to local, {errors} errors"

    def _sync_to_local(self, svc, user_id: int) -> str:
        """Alias for sync_from_hf — sync HF storage to local."""
        return self._sync_from_hf(svc, user_id)


def _format_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _format_time(ts: float) -> str:
    if not ts:
        return "unknown"
    try:
        import datetime
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(int(ts))
