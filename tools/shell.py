"""Shell tool - execute commands in the container."""

import io
import hashlib
import json
import logging
import os
import queue
import re
import shlex
import shutil
import subprocess
import tarfile
import threading
import time
from dataclasses import dataclass

from hf_dataset_store import get_hf_dataset_store
from services.hf_backup_gate import should_backup_shell

from .registry import BaseTool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 120
_MAX_OUTPUT = 10000
_HEAD_TAIL = 4000
_DEFAULT_WORK_ROOT = (os.getenv("SHELL_WORK_ROOT") or "/tmp/shell").strip() or "/tmp/shell"


def _parse_env_items(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default or [])
    items = []
    for part in raw.split(","):
        value = part.strip()
        if value:
            items.append(value)
    return items


def _get_bool_env(name: str, default: bool) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "y"}:
        return True
    if raw in {"0", "false", "no", "off", "n"}:
        return False
    return default


_HF_SNAPSHOT_MAX_BYTES = int(os.getenv("SHELL_HF_SNAPSHOT_MAX_BYTES", "0"))
_HF_SNAPSHOT_MAX_FILE_BYTES = int(os.getenv("SHELL_HF_SNAPSHOT_MAX_FILE_BYTES", "0"))
_HF_SYNC_INTERVAL_SECONDS = max(0, int(os.getenv("SHELL_HF_SYNC_INTERVAL_SECONDS", "0")))
_HF_MAX_FILES = int(os.getenv("SHELL_HF_MAX_FILES", "0"))
_HF_SKIP_DIRS = set(_parse_env_items("SHELL_HF_SKIP_DIRS"))
_HF_SKIP_SUFFIXES = set(_parse_env_items("SHELL_HF_SKIP_SUFFIXES"))
_HF_SNAPSHOT_ASYNC = _get_bool_env("SHELL_HF_SNAPSHOT_ASYNC", True)
_HF_SNAPSHOT_QUEUE_MAX = max(1, int(os.getenv("SHELL_HF_SNAPSHOT_QUEUE_MAX", "2")))
_HF_RESTORE_PACKAGES_ENABLED = _get_bool_env("SHELL_HF_RESTORE_PACKAGES", True)
_HF_RESTORE_PACKAGES_MAX_SECONDS = max(0, int(os.getenv("SHELL_HF_RESTORE_PACKAGES_MAX_SECONDS", "20")))
_HF_AESGCM_MAX_BYTES = (1 << 31) - 1
_DEFAULT_PERSISTENT_PATHS = [
    "~/.local",
    "~/.nvm",
    "~/.npm",
    "~/.yarn",
    "~/.config/yarn",
    "~/.cache/node/corepack",
    "~/.pnpm-store",
]
_HF_PERSISTENT_PATHS = [
    os.path.realpath(os.path.expanduser(path))
    for path in _parse_env_items("SHELL_HF_PERSIST_PATHS", _DEFAULT_PERSISTENT_PATHS)
    if str(path).strip()
]
_HF_STATE_LOCK = threading.Lock()
_HF_RESTORED_WORKSPACES: set[tuple[int, str]] = set()
_HF_LAST_SYNC_AT: dict[tuple[int, str], float] = {}
_HF_RESTORED_PERSISTENT_PATHS: set[tuple[int, str]] = set()
_SNAPSHOT_QUEUE: queue.Queue | None = None
_SNAPSHOT_THREAD: threading.Thread | None = None
_SNAPSHOT_LOCK = threading.Lock()

_PKG_SINGLE_TIMEOUT = 120
_PKG_RESTORED_USERS: set[int] = set()

# Patterns that should be blocked
_BLOCKED_PATTERNS = [
    r"\brm\s+-[^\s]*r[^\s]*f\s+/",  # rm -rf /
    r"\brm\s+-[^\s]*f[^\s]*r\s+/",  # rm -fr /
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bhalt\b",
    r"\binit\s+[06]\b",
    r"\bmkfs\b",
    r"\bdd\b.*\bof=/dev/",  # dd writing to devices
    r"\bsudo\b",
    r"\bsu\s",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;",  # fork bomb :(){ :|:& };:
    r"\biptables\b",
    r"\bnft\b",
    r"\bcrontab\b",
    r"\bchmod\s+[0-7]*s",  # setuid
    r"\bchown\s+-R\s+.*\s+/",  # recursive chown on /
    r"\bmount\b",
    r"\bumount\b",
    r"\bsystemctl\b",
    r"\bservice\b",
    r"\bnsenter\b",
    r"\bunshare\b",
    r">\s*/dev/[sh]d",  # redirect to block devices
    r"\bkill\s+-9\s+1\b",  # kill init
    r"\bpkill\b.*-9",
    r"\bkillall\b",
]
_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

# Environment variable keywords to scrub
_SENSITIVE_KEYWORDS = [
    "TOKEN",
    "SECRET",
    "KEY",
    "PASSWORD",
    "PASSWD",
    "DATABASE_URL",
    "CREDENTIAL",
    "AUTH",
]


def _is_blocked(command: str) -> str | None:
    """Return a reason string if the command is blocked, else None."""
    for pattern in _BLOCKED_RE:
        if pattern.search(command):
            return f"Command blocked by security policy (matched: {pattern.pattern})"
    return None


def _clean_env() -> dict[str, str]:
    """Return a copy of os.environ with sensitive variables removed."""
    env = {}
    for k, v in os.environ.items():
        upper = k.upper()
        if any(kw in upper for kw in _SENSITIVE_KEYWORDS):
            continue
        env[k] = v
    env["NVM_DIR"] = env.get("NVM_DIR") or os.path.join(env.get("HOME") or os.path.expanduser("~"), ".nvm")
    path_entries = []
    home = env.get("HOME") or os.path.expanduser("~")
    for candidate in (
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".yarn", "bin"),
        os.path.join(home, ".local", "share", "pnpm"),
        os.path.join(home, ".bun", "bin"),
    ):
        if os.path.isdir(candidate):
            path_entries.append(candidate)

    nvm_root = env.get("NVM_DIR") or os.path.join(home, ".nvm")
    versions_dir = os.path.join(nvm_root, "versions", "node")
    if os.path.isdir(versions_dir):
        for entry in sorted(os.listdir(versions_dir), reverse=True):
            candidate = os.path.join(versions_dir, entry, "bin")
            if os.path.isdir(candidate):
                path_entries.append(candidate)

    existing_parts = [part for part in str(env.get("PATH") or "").split(os.pathsep) if part]
    merged_path = []
    seen = set()
    for part in [*path_entries, *existing_parts]:
        if part in seen:
            continue
        seen.add(part)
        merged_path.append(part)
    if merged_path:
        env["PATH"] = os.pathsep.join(merged_path)
    return env


def _truncate_output(text: str) -> str:
    """Truncate output to _MAX_OUTPUT chars, keeping head and tail."""
    if len(text) <= _MAX_OUTPUT:
        return text
    head = text[:_HEAD_TAIL]
    tail = text[-_HEAD_TAIL:]
    skipped = len(text) - _HEAD_TAIL * 2
    return f"{head}\n\n... [{skipped} characters truncated] ...\n\n{tail}"


def _workspace_has_content(path: str) -> bool:
    try:
        with os.scandir(path) as entries:
            return any(True for _ in entries)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _path_exists_with_state(path: str) -> bool:
    if os.path.isfile(path):
        return True
    if os.path.isdir(path):
        return True
    return False


def _remove_path(path: str) -> None:
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
        return
    if os.path.isdir(path):
        shutil.rmtree(path)


def _clear_directory_contents(path: str) -> None:
    if not os.path.isdir(path):
        return
    for entry in os.scandir(path):
        _remove_path(entry.path)


def _join_archive_path(root_name: str | None, rel_path: str) -> str:
    clean_rel = rel_path.replace("\\", "/").strip("/")
    if root_name and clean_rel:
        return f"{root_name}/{clean_rel}"
    if root_name:
        return root_name
    return clean_rel


def _normalize_workspace_path(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))


def _workspace_store_paths(user_id: int, cwd: str) -> dict[str, str]:
    normalized_cwd = _normalize_workspace_path(cwd)
    workspace_key = hashlib.sha256(normalized_cwd.encode("utf-8")).hexdigest()[:24]
    base = f"shell/{user_id}/workspaces/{workspace_key}"
    return {
        "key": workspace_key,
        "cwd": normalized_cwd,
        "archive_path": f"{base}/workspace.tar.gz",
        "meta_path": f"{base}/workspace_meta.json",
        "index_path": f"shell/{user_id}/workspaces/index.json",
    }


def _load_workspace_index(user_id: int) -> dict:
    store = get_hf_dataset_store()
    if not store.enabled:
        return {"version": 2, "updated_at": 0, "workspaces": {}}

    data = store.get_json(f"shell/{user_id}/workspaces/index.json")
    if isinstance(data, dict) and isinstance(data.get("workspaces"), dict):
        return data
    return {"version": 2, "updated_at": 0, "workspaces": {}}


def _load_legacy_workspace_archive(user_id: int, cwd: str) -> bytes | None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return None

    meta = store.get_json(f"shell/{user_id}/workspace_meta.json")
    if not isinstance(meta, dict):
        return None

    legacy_cwd = str(meta.get("cwd", "")).strip()
    if not legacy_cwd:
        return None
    if _normalize_workspace_path(legacy_cwd) != _normalize_workspace_path(cwd):
        return None

    return store.get_bytes(f"shell/{user_id}/workspace.tar.gz")


def _persistent_path_store_paths(user_id: int, path: str) -> dict[str, str]:
    normalized_path = _normalize_workspace_path(path)
    path_key = hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()[:24]
    base = f"shell/{user_id}/persistent_paths/{path_key}"
    return {
        "key": path_key,
        "path": normalized_path,
        "archive_path": f"{base}/state.tar.gz",
        "meta_path": f"{base}/state_meta.json",
        "index_path": f"shell/{user_id}/persistent_paths/index.json",
    }


def _load_persistent_path_index(user_id: int) -> dict:
    store = get_hf_dataset_store()
    if not store.enabled:
        return {"version": 1, "updated_at": 0, "paths": {}}

    data = store.get_json(f"shell/{user_id}/persistent_paths/index.json")
    if isinstance(data, dict) and isinstance(data.get("paths"), dict):
        return data
    return {"version": 1, "updated_at": 0, "paths": {}}


def _build_snapshot_archive(
    source_path: str,
    *,
    root_name: str | None,
    skip_dirs: set[str] | None = None,
    skip_suffixes: set[str] | None = None,
) -> tuple[bytes | None, dict]:
    normalized_source = _normalize_workspace_path(source_path)
    skip_dirs = skip_dirs or set()
    skip_suffixes = skip_suffixes or set()
    dir_entries: list[tuple[str, str]] = []
    file_entries: list[tuple[str, str, int]] = []
    total_input_bytes = 0

    if os.path.isdir(normalized_source):
        for dirpath, dirnames, filenames in os.walk(normalized_source):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            rel_dir = os.path.relpath(dirpath, normalized_source)
            rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")
            archive_dir = _join_archive_path(root_name, rel_dir)
            if archive_dir:
                dir_entries.append((dirpath, archive_dir))

            for filename in filenames:
                if any(filename.endswith(suffix) for suffix in skip_suffixes):
                    continue
                abs_path = os.path.join(dirpath, filename)
                if not (os.path.isfile(abs_path) or os.path.islink(abs_path)):
                    continue
                try:
                    size = os.path.getsize(abs_path)
                except OSError:
                    continue
                if _HF_SNAPSHOT_MAX_FILE_BYTES > 0 and size > _HF_SNAPSHOT_MAX_FILE_BYTES:
                    continue

                rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
                archive_path = _join_archive_path(root_name, rel_path)
                file_entries.append((abs_path, archive_path, size))
                total_input_bytes += size
                if _HF_MAX_FILES > 0 and len(file_entries) >= _HF_MAX_FILES:
                    break

            if _HF_MAX_FILES > 0 and len(file_entries) >= _HF_MAX_FILES:
                break
    elif os.path.isfile(normalized_source) or os.path.islink(normalized_source):
        archive_name = _join_archive_path(root_name, os.path.basename(normalized_source))
        try:
            size = os.path.getsize(normalized_source)
        except OSError:
            size = 0
        file_entries.append((normalized_source, archive_name, size))
        total_input_bytes += size
    else:
        return None, {
            "exists": False,
            "files": 0,
            "directories": 0,
            "total_input_bytes": 0,
        }

    metadata = {
        "exists": True,
        "files": len(file_entries),
        "directories": len(dir_entries),
        "total_input_bytes": total_input_bytes,
    }

    try:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz", dereference=True) as archive:
            for abs_path, arc_path in dir_entries:
                archive.add(abs_path, arcname=arc_path, recursive=False)
            for abs_path, arc_path, _size in file_entries:
                archive.add(abs_path, arcname=arc_path, recursive=False)
        archive_bytes = buffer.getvalue()
    except Exception as e:
        logger.warning("Failed to build shell snapshot archive: %s", e)
        return None, metadata

    metadata["archive_bytes"] = len(archive_bytes)
    if len(archive_bytes) > _HF_AESGCM_MAX_BYTES:
        logger.warning(
            "Skip shell snapshot: archive exceeds AESGCM limit (%d > %d bytes).",
            len(archive_bytes),
            _HF_AESGCM_MAX_BYTES,
        )
        return None, metadata
    if _HF_SNAPSHOT_MAX_BYTES > 0 and len(archive_bytes) > _HF_SNAPSHOT_MAX_BYTES:
        logger.warning(
            "Skip shell snapshot: archive too large (%d > %d bytes).",
            len(archive_bytes),
            _HF_SNAPSHOT_MAX_BYTES,
        )
        return None, metadata

    return archive_bytes, metadata


def _safe_extract_tar_gz(data: bytes, target_dir: str) -> bool:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            root = os.path.abspath(target_dir)
            safe_members = []
            for member in archive.getmembers():
                if member.issym() or member.islnk():
                    continue
                destination = os.path.abspath(os.path.join(root, member.name))
                if destination == root or destination.startswith(root + os.sep):
                    safe_members.append(member)
            archive.extractall(path=target_dir, members=safe_members)
        return True
    except Exception as e:
        logger.warning("Failed to restore shell workspace archive: %s", e)
        return False


def _build_workspace_snapshot(cwd: str) -> tuple[bytes | None, dict]:
    return _build_snapshot_archive(
        cwd,
        root_name=None,
        skip_dirs=_HF_SKIP_DIRS,
        skip_suffixes=_HF_SKIP_SUFFIXES,
    )


def _restore_workspace_from_hf(user_id: int, cwd: str) -> None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    paths = _workspace_store_paths(user_id, cwd)
    restored_key = (user_id, paths["key"])

    with _HF_STATE_LOCK:
        if restored_key in _HF_RESTORED_WORKSPACES:
            return
        _HF_RESTORED_WORKSPACES.add(restored_key)

    meta = store.get_json(paths["meta_path"])
    archive = store.get_bytes(paths["archive_path"])
    if not archive and not meta:
        archive = _load_legacy_workspace_archive(user_id, cwd)
    if not archive:
        return

    _clear_directory_contents(cwd)
    if _safe_extract_tar_gz(archive, cwd):
        logger.info(
            "[user=%d] restored shell workspace from HF dataset (cwd=%s)",
            user_id,
            paths["cwd"],
        )


def _snapshot_workspace_to_hf(user_id: int, cwd: str, command: str) -> None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    normalized_cwd = _normalize_workspace_path(cwd)
    if normalized_cwd == "/tmp":
        logger.warning("Skip shell snapshot: cwd is /tmp.")
        return

    paths = _workspace_store_paths(user_id, cwd)
    now = time.time()
    with _HF_STATE_LOCK:
        sync_key = (user_id, paths["key"])
        last = _HF_LAST_SYNC_AT.get(sync_key, 0.0)
        if _HF_SYNC_INTERVAL_SECONDS > 0 and now - last < _HF_SYNC_INTERVAL_SECONDS:
            return
        _HF_LAST_SYNC_AT[sync_key] = now

    archive, snapshot_meta = _build_workspace_snapshot(cwd)
    if archive is None:
        return

    ok = store.put_bytes(
        paths["archive_path"],
        archive,
        commit_message=f"shell workspace snapshot user={user_id}",
    )
    if not ok:
        return

    meta_payload = {
        "version": 2,
        "user_id": user_id,
        "workspace_key": paths["key"],
        "cwd": paths["cwd"],
        "updated_at": int(now),
        "archive_bytes": len(archive),
        "last_command": command[:200],
        **snapshot_meta,
    }
    store.put_json(
        paths["meta_path"],
        meta_payload,
        commit_message=f"shell workspace metadata user={user_id}",
    )

    index = _load_workspace_index(user_id)
    workspaces = index.setdefault("workspaces", {})
    workspaces[paths["key"]] = {
        "cwd": paths["cwd"],
        "updated_at": int(now),
        "archive_path": paths["archive_path"],
        "meta_path": paths["meta_path"],
        "files": meta_payload.get("files", 0),
        "archive_bytes": meta_payload.get("archive_bytes", 0),
        "last_command": meta_payload.get("last_command", ""),
    }
    index["version"] = 2
    index["updated_at"] = int(now)
    store.put_json(
        paths["index_path"],
        index,
        commit_message=f"shell workspace index user={user_id}",
    )


def _restore_persistent_paths_from_hf(user_id: int) -> None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    for path in _HF_PERSISTENT_PATHS:
        paths = _persistent_path_store_paths(user_id, path)
        restored_key = (user_id, paths["key"])
        with _HF_STATE_LOCK:
            if restored_key in _HF_RESTORED_PERSISTENT_PATHS:
                continue
            _HF_RESTORED_PERSISTENT_PATHS.add(restored_key)

        meta = store.get_json(paths["meta_path"])
        if not isinstance(meta, dict):
            continue

        exists = bool(meta.get("exists", False))
        if not exists:
            if _path_exists_with_state(path):
                try:
                    _remove_path(path)
                except Exception as e:
                    logger.warning("[user=%d] failed to remove persistent path %s: %s", user_id, path, e)
            continue

        archive = store.get_bytes(paths["archive_path"])
        if not archive:
            continue

        try:
            if _path_exists_with_state(path):
                _remove_path(path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if _safe_extract_tar_gz(archive, os.path.dirname(path)):
                logger.info("[user=%d] restored persistent path %s", user_id, path)
        except Exception as e:
            logger.warning("[user=%d] failed to restore persistent path %s: %s", user_id, path, e)


def _snapshot_persistent_paths_to_hf(user_id: int) -> None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    now = int(time.time())
    index = _load_persistent_path_index(user_id)
    path_index = index.setdefault("paths", {})

    for path in _HF_PERSISTENT_PATHS:
        paths = _persistent_path_store_paths(user_id, path)
        if _path_exists_with_state(path):
            archive, meta = _build_snapshot_archive(
                path,
                root_name=os.path.basename(path.rstrip(os.sep)) or os.path.basename(os.path.dirname(path)),
            )
            if archive is None:
                continue
            ok = store.put_bytes(
                paths["archive_path"],
                archive,
                commit_message=f"shell persistent path snapshot user={user_id}",
            )
            if not ok:
                continue
            meta_payload = {
                "version": 1,
                "path": paths["path"],
                "exists": True,
                "updated_at": now,
                **meta,
            }
            store.put_json(
                paths["meta_path"],
                meta_payload,
                commit_message=f"shell persistent path metadata user={user_id}",
            )
            path_index[paths["key"]] = {
                "path": paths["path"],
                "exists": True,
                "updated_at": now,
                "archive_path": paths["archive_path"],
                "meta_path": paths["meta_path"],
                "files": meta_payload.get("files", 0),
                "directories": meta_payload.get("directories", 0),
                "archive_bytes": meta_payload.get("archive_bytes", 0),
            }
            continue

        store.delete(paths["archive_path"], commit_message=f"shell persistent path delete user={user_id}")
        meta_payload = {
            "version": 1,
            "path": paths["path"],
            "exists": False,
            "updated_at": now,
            "files": 0,
            "directories": 0,
            "archive_bytes": 0,
        }
        store.put_json(
            paths["meta_path"],
            meta_payload,
            commit_message=f"shell persistent path metadata user={user_id}",
        )
        path_index[paths["key"]] = {
            "path": paths["path"],
            "exists": False,
            "updated_at": now,
            "archive_path": paths["archive_path"],
            "meta_path": paths["meta_path"],
            "files": 0,
            "directories": 0,
            "archive_bytes": 0,
        }

    index["version"] = 1
    index["updated_at"] = now
    store.put_json(
        f"shell/{user_id}/persistent_paths/index.json",
        index,
        commit_message=f"shell persistent path index user={user_id}",
    )


# ── Snapshot async worker ──────────────────────────────


@dataclass
class _SnapshotJob:
    user_id: int
    cwd: str
    command: str
    exec_env: dict[str, str]
    exit_code: int | None


def _run_snapshot_job(job: _SnapshotJob) -> None:
    _snapshot_workspace_to_hf(job.user_id, job.cwd, job.command)
    _snapshot_persistent_paths_to_hf(job.user_id)
    if job.exit_code is not None:
        _snapshot_packages_to_hf(job.user_id, job.exit_code, job.command, job.exec_env)


def _snapshot_worker() -> None:
    while True:
        item = _SNAPSHOT_QUEUE.get() if _SNAPSHOT_QUEUE else None
        if item is None:
            if _SNAPSHOT_QUEUE:
                _SNAPSHOT_QUEUE.task_done()
            return
        try:
            _run_snapshot_job(item)
        except Exception as e:
            logger.warning("HF snapshot worker failed: %s", e)
        finally:
            if _SNAPSHOT_QUEUE:
                _SNAPSHOT_QUEUE.task_done()


def _ensure_snapshot_worker() -> queue.Queue | None:
    if not _HF_SNAPSHOT_ASYNC:
        return None
    global _SNAPSHOT_QUEUE, _SNAPSHOT_THREAD
    with _SNAPSHOT_LOCK:
        if _SNAPSHOT_QUEUE is None:
            _SNAPSHOT_QUEUE = queue.Queue(maxsize=_HF_SNAPSHOT_QUEUE_MAX)
            _SNAPSHOT_THREAD = threading.Thread(
                target=_snapshot_worker,
                name="hf-snapshot-worker",
                daemon=True,
            )
            _SNAPSHOT_THREAD.start()
    return _SNAPSHOT_QUEUE


def _schedule_snapshot(job: _SnapshotJob) -> None:
    queue_ref = _ensure_snapshot_worker()
    if queue_ref is None:
        _run_snapshot_job(job)
        return
    try:
        queue_ref.put_nowait(job)
    except queue.Full:
        logger.warning("Skip HF snapshot: snapshot queue is full.")


# ── Package manifest backup / restore ──────────────────────────────


def _split_shell_segments(command: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"(?:&&|\|\||;|\n)", command) if segment.strip()]


def _strip_env_assignments(tokens: list[str]) -> list[str]:
    idx = 0
    while idx < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", tokens[idx]):
        idx += 1
    return tokens[idx:]


def _extract_apt_packages_from_command(command: str) -> tuple[str | None, list[str]]:
    actions_with_packages = {"install", "remove", "purge", "autoremove"}
    option_takes_value = {"-o", "--option", "-c", "--config-file", "-t", "--target-release"}
    for segment in _split_shell_segments(command):
        try:
            tokens = _strip_env_assignments(shlex.split(segment))
        except ValueError:
            continue
        if not tokens:
            continue

        if tokens[0] not in {"apt", "apt-get"}:
            continue

        action_index = None
        action = None
        for idx, token in enumerate(tokens[1:], start=1):
            if token in actions_with_packages:
                action_index = idx
                action = token
                break
        if action_index is None or action is None:
            continue

        packages = []
        skip_next = False
        for token in tokens[action_index + 1 :]:
            if skip_next:
                skip_next = False
                continue
            if token in option_takes_value:
                skip_next = True
                continue
            if token.startswith("-"):
                continue
            if token.startswith("$") or "=" in token or "::" in token:
                continue
            packages.append(token)

        if packages:
            return action, packages
    return None, []


def _capture_pip_manifest(env: dict[str, str]) -> list[str]:
    """Run ``pip freeze --local`` and return the list of installed packages."""
    try:
        proc = subprocess.run(
            ["pip", "freeze", "--local"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except Exception as e:
        logger.warning("Failed to capture pip manifest: %s", e)
        return []


def _capture_npm_manifest(env: dict[str, str]) -> list[str]:
    """Run ``npm list -g --depth=0`` and return global packages."""
    if not shutil.which("npm", path=env.get("PATH")):
        return []
    try:
        proc = subprocess.run(
            ["npm", "list", "-g", "--depth=0", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if proc.returncode != 0 and not proc.stdout:
            return []
        data = json.loads(proc.stdout)
        deps = data.get("dependencies", {})
        packages = []
        for pkg, info in deps.items():
            if pkg == "npm":
                continue
            version = info.get("version", "")
            packages.append(f"{pkg}@{version}" if version else pkg)
        return packages
    except Exception as e:
        logger.warning("Failed to capture npm manifest: %s", e)
        return []


def _get_existing_manifest(user_id: int) -> dict:
    """Load the existing package manifest from HF, or return an empty skeleton."""
    store = get_hf_dataset_store()
    if not store.enabled:
        return {"version": 2, "updated_at": 0, "pip": [], "npm": [], "apt": []}
    path = f"shell/{user_id}/packages_manifest.json"
    data = store.get_json(path)
    if isinstance(data, dict) and data.get("version"):
        return data
    return {"version": 2, "updated_at": 0, "pip": [], "npm": [], "apt": []}


def _snapshot_packages_to_hf(user_id: int, exit_code: int, command: str, env: dict[str, str]) -> None:
    """Capture current package state and upload manifest to HF."""
    if exit_code != 0:
        return

    store = get_hf_dataset_store()
    if not store.enabled:
        return

    manifest = _get_existing_manifest(user_id)
    manifest["version"] = 2
    manifest["pip"] = _capture_pip_manifest(env)
    manifest["npm"] = _capture_npm_manifest(env)

    action, packages = _extract_apt_packages_from_command(command)
    if action and packages:
        existing = set(manifest.get("apt", []))
        if action in {"remove", "purge", "autoremove"}:
            existing.difference_update(packages)
        else:
            existing.update(packages)
        manifest["apt"] = sorted(existing)

    manifest["updated_at"] = int(time.time())
    path = f"shell/{user_id}/packages_manifest.json"
    store.put_json(
        path,
        manifest,
        commit_message=f"shell package manifest user={user_id}",
    )
    logger.info(
        "[user=%d] saved package manifest (pip=%d, npm=%d, apt=%d)",
        user_id,
        len(manifest.get("pip", [])),
        len(manifest.get("npm", [])),
        len(manifest.get("apt", [])),
    )

def _time_left(deadline: float | None) -> int | None:
    if deadline is None:
        return None
    remaining = int(deadline - time.time())
    if remaining <= 0:
        return 0
    return remaining


def _restore_apt(user_id: int, packages: list[str], env: dict[str, str], deadline: float | None) -> None:
    """Reinstall apt packages."""
    if not packages:
        return
    try:
        timeout = _time_left(deadline)
        if timeout == 0:
            return
        subprocess.run(
            ["apt-get", "update"],
            capture_output=True,
            timeout=timeout or _PKG_SINGLE_TIMEOUT,
            env=env,
        )
        timeout = _time_left(deadline)
        if timeout == 0:
            return
        subprocess.run(
            ["apt-get", "install", "-y", "--no-install-recommends", *packages],
            capture_output=True,
            timeout=timeout or _PKG_SINGLE_TIMEOUT,
            env=env,
        )
        logger.info("[user=%d] restored %d apt packages", user_id, len(packages))
    except Exception as e:
        logger.warning("[user=%d] apt restore failed: %s", user_id, e)


def _restore_pip(user_id: int, packages: list[str], env: dict[str, str], deadline: float | None) -> None:
    """Reinstall pip packages."""
    if not packages:
        return
    timeout = _time_left(deadline)
    if timeout == 0:
        return
    try:
        subprocess.run(
            ["pip", "install", "--quiet", *packages],
            capture_output=True,
            timeout=timeout or _PKG_SINGLE_TIMEOUT,
            env=env,
        )
        logger.info("[user=%d] restored %d pip packages", user_id, len(packages))
    except Exception as e:
        logger.warning("[user=%d] pip restore failed: %s", user_id, e)


def _restore_npm(user_id: int, packages: list[str], env: dict[str, str], deadline: float | None) -> None:
    """Reinstall global npm packages."""
    if not packages or not shutil.which("npm", path=env.get("PATH")):
        return
    timeout = _time_left(deadline)
    if timeout == 0:
        return
    try:
        subprocess.run(
            ["npm", "install", "-g", "--silent", *packages],
            capture_output=True,
            timeout=timeout or _PKG_SINGLE_TIMEOUT,
            env=env,
        )
        logger.info("[user=%d] restored %d npm packages", user_id, len(packages))
    except Exception as e:
        logger.warning("[user=%d] npm restore failed: %s", user_id, e)


def _restore_packages_from_hf(user_id: int) -> None:
    """Load the package manifest from HF and reinstall everything."""
    store = get_hf_dataset_store()
    if not store.enabled:
        return
    if not _HF_RESTORE_PACKAGES_ENABLED:
        return
    if _HF_RESTORE_PACKAGES_MAX_SECONDS == 0:
        return

    with _HF_STATE_LOCK:
        if user_id in _PKG_RESTORED_USERS:
            return
        _PKG_RESTORED_USERS.add(user_id)

    manifest = _get_existing_manifest(user_id)
    apt_pkgs = manifest.get("apt", [])
    pip_pkgs = manifest.get("pip", [])
    npm_pkgs = manifest.get("npm", [])

    if not apt_pkgs and not pip_pkgs and not npm_pkgs:
        return

    env = _clean_env()
    deadline = time.time() + _HF_RESTORE_PACKAGES_MAX_SECONDS if _HF_RESTORE_PACKAGES_MAX_SECONDS > 0 else None

    logger.info(
        "[user=%d] restoring packages (apt=%d, pip=%d, npm=%d)",
        user_id,
        len(apt_pkgs),
        len(pip_pkgs),
        len(npm_pkgs),
    )

    # Restore order: apt → pip → npm
    _restore_apt(user_id, apt_pkgs, env, deadline)
    _restore_pip(user_id, pip_pkgs, env, deadline)
    _restore_npm(user_id, npm_pkgs, env, deadline)


class ShellTool(BaseTool):
    """Execute shell commands in the container."""

    @property
    def name(self) -> str:
        return "shell"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "shell_exec",
                    "description": (
                        "Execute a shell command in the container and return the output. "
                        "Supports pipes, redirects, and chained commands. "
                        "Use for file operations, running scripts, system info, etc."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute",
                            },
                            "timeout": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": _MAX_TIMEOUT,
                                "default": _DEFAULT_TIMEOUT,
                                "description": f"Timeout in seconds (1-{_MAX_TIMEOUT}, default {_DEFAULT_TIMEOUT})",
                            },
                            "working_directory": {
                                "type": "string",
                                "description": "Working directory for the command (default: per-user temp dir)",
                            },
                            "persist_packages": {
                                "type": "boolean",
                                "default": True,
                                "description": (
                                    "Deprecated. Package and runtime persistence is now enabled by default "
                                    "for every command."
                                ),
                            },
                            "apt_packages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Deprecated. apt packages are now detected automatically from the command."
                                ),
                            },
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name != "shell_exec":
            return f"Unknown tool: {tool_name}"

        command = (arguments.get("command") or "").strip()
        if not command:
            return "Error: No command provided."

        # Security check
        reason = _is_blocked(command)
        if reason:
            logger.warning("[user=%d] shell command blocked: %s", user_id, command[:200])
            return f"Error: {reason}"

        # Timeout
        timeout = _DEFAULT_TIMEOUT
        if arguments.get("timeout") is not None:
            try:
                timeout = max(1, min(_MAX_TIMEOUT, int(arguments["timeout"])))
            except (TypeError, ValueError):
                pass

        # Working directory
        default_cwd = f"{_DEFAULT_WORK_ROOT}/{user_id}"
        cwd = (arguments.get("working_directory") or "").strip() or default_cwd
        cwd = _normalize_workspace_path(cwd)
        os.makedirs(cwd, exist_ok=True)
        _restore_persistent_paths_from_hf(user_id)
        _restore_workspace_from_hf(user_id, cwd)
        _restore_packages_from_hf(user_id)
        exec_env = _clean_env()
        store = get_hf_dataset_store()
        snapshot_allowed = store.enabled and should_backup_shell(user_id)

        # Execute
        logger.info("[user=%d] shell_exec: %s (timeout=%ds, cwd=%s)", user_id, command[:200], timeout, cwd)
        result = None
        timeout_error = False
        runtime_error: Exception | None = None
        try:
            result = subprocess.run(
                ["bash", "-lc", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=exec_env,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            timeout_error = True
            logger.warning("[user=%d] shell command timed out after %ds: %s", user_id, timeout, command[:200])
        except Exception as e:
            runtime_error = e
            logger.exception("[user=%d] shell exec error", user_id)
        finally:
            if snapshot_allowed:
                job = _SnapshotJob(
                    user_id=user_id,
                    cwd=cwd,
                    command=command,
                    exec_env=exec_env,
                    exit_code=result.returncode if result is not None else None,
                )
                _schedule_snapshot(job)

        if timeout_error:
            return f"Error: Command timed out after {timeout} seconds."
        if runtime_error is not None:
            return "Error. Please retry."
        if result is None:
            return "Error: command execution returned no result."

        # Build output
        parts = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        if result.returncode != 0:
            parts.append(f"[exit code: {result.returncode}]")

        output = "\n".join(parts) if parts else "(no output)"
        return _truncate_output(output)

    def get_instruction(self) -> str:
        from config.settings import WEB_BASE_URL
        return (
            "\n\nYou have the shell_exec tool to execute shell commands in the container.\n"
            "Use it when the user asks you to run commands, write/run scripts, check system info, "
            "process files, or perform tasks that require a terminal.\n"
            "You can use pipes, redirects, and chain multiple commands.\n"
            f"Each user has their own working directory at {_DEFAULT_WORK_ROOT}/<user_id>/.\n"
            "When HF_DATASET_USERNAME/HF_DATASET_TOKEN/HF_DATASET_NAME are configured, "
            "every command now snapshots the full working directory and common user runtime paths to a Hugging Face dataset.\n"
            "Package/runtime persistence is automatic: apt packages are inferred from the command, and pip/npm state is captured after successful runs.\n"
            "Use working_directory instead of relying on `cd ... &&` when you want a project folder to be restored exactly after container restarts.\n"
            "\n"
            "**Web service proxy:** When you start a web service (Flask, Gradio, Streamlit, etc.) "
            "that listens on a port inside the container, users can access it via:\n"
            f"  {WEB_BASE_URL}/proxy/<port>/\n"
            "Tell the user this URL so they can open it in their browser. "
            "Make sure the service binds to 0.0.0.0 (not just 127.0.0.1) for the proxy to work.\n"
        )
