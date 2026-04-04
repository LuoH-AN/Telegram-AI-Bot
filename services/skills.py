"""Skill runtime service."""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import tarfile
import time
import urllib.request
import urllib.error
from pathlib import Path

from cache import cache
from hf_dataset_store import get_hf_dataset_store

logger = logging.getLogger(__name__)

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "runtime_skills"
SKILL_NAMESPACE = "skills"
SKILL_TERMINAL_NAME = "skill_terminal"
HF_SYNC_NAME = "hf_sync"

_GITHUB_REPO_RE = re.compile(
    r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.+))?)?$"
)
_GITHUB_RAW_RE = re.compile(
    r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)(?:/(.+))?$"
)


def _to_github_raw_base(url: str) -> str | None:
    m = _GITHUB_REPO_RE.match(url.rstrip("/"))
    if m:
        owner, repo, branch, subpath = m.groups()
        branch = branch or "main"
        base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
        return f"{base}/{subpath.rstrip('/')}" if subpath else base
    m = _GITHUB_RAW_RE.match(url.rstrip("/"))
    if m:
        owner, repo, branch, subpath = m.groups()
        base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
        return f"{base}/{subpath.rstrip('/')}" if subpath else base
    return None


def _github_fetch(raw_url: str, timeout: int = 20) -> bytes | None:
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "gemen-skill-installer/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read()
    except urllib.error.HTTPError as e:
        logger.debug("GitHub fetch %s -> HTTP %s", raw_url, e.code)
    except Exception as e:
        logger.debug("GitHub fetch failed %s: %s", raw_url, e)
    return None


def _skill_dir(user_id: int, skill_name: str) -> Path:
    return SKILLS_ROOT / str(user_id) / skill_name


def _skill_hf_prefix(user_id: int, skill_name: str) -> str:
    return f"{SKILL_NAMESPACE}/{user_id}/{skill_name}"


def _snapshot_id() -> str:
    return time.strftime("snap_%Y%m%d_%H%M%S")


def _manifest_path(user_id: int, skill_name: str) -> Path:
    return _skill_dir(user_id, skill_name) / "manifest.json"


def _handler_path(user_id: int, skill_name: str) -> Path:
    return _skill_dir(user_id, skill_name) / "handler.py"


def _default_manifest(name: str, source_type: str, source_ref: str, persist_mode: str) -> dict:
    capabilities = ["skill_terminal", "skill"] if name == SKILL_TERMINAL_NAME else ["skill"]
    display_name = "Skill Terminal" if name == SKILL_TERMINAL_NAME else name
    return {
        "name": name,
        "display_name": display_name,
        "source_type": source_type,
        "source_ref": source_ref or name,
        "persist_mode": persist_mode,
        "restore_on_boot": persist_mode == "hf_git",
        "entrypoint": "handler.py",
        "capabilities": capabilities,
        "snapshots": [],
    }


def _default_handler_source(name: str) -> str:
    if name == SKILL_TERMINAL_NAME:
        return '''"""Runtime skill handler for skill_terminal."""

from services.skill_terminal import run_skill_terminal


def run(user_id: int, skill_name: str, input_text: str, state: dict) -> dict:
    result = run_skill_terminal(user_id, input_text)
    calls = int(state.get("calls", 0)) + 1
    return {
        "output": result.get("message", "Skill terminal execution completed."),
        "state": {
            **state,
            "calls": calls,
            "last_input": input_text,
            "last_terminal_steps": result.get("steps", []),
            "last_terminal_ok": bool(result.get("ok")),
        },
    }
'''
    if name == HF_SYNC_NAME:
        return '''"""Runtime skill handler for hf_sync."""

from services.skills import (
    persist_skill_state,
    persist_skill_snapshot,
    restore_skill_snapshot,
    list_skill_snapshots,
)


def run(user_id: int, skill_name: str, input_text: str, state: dict) -> dict:
    import json
    calls = int(state.get("calls", 0)) + 1
    try:
        args = json.loads(input_text) if input_text.strip().startswith("{") else {"action": "persist", "skill_name": input_text.strip()}
    except Exception:
        args = {"action": "persist", "skill_name": input_text.strip()}

    action = args.get("action", "persist")
    target = args.get("skill_name", "")
    snapshot_id = args.get("snapshot_id")

    if action == "persist":
        ok = persist_skill_state(user_id, target)
        output = f"Skill '{target}' persist {'succeeded' if ok else 'failed'}."
    elif action == "restore":
        ok = restore_skill_snapshot(user_id, target, snapshot_id=snapshot_id)
        output = f"Skill '{target}' restore {'succeeded' if ok else 'failed'}."
    elif action == "snapshot":
        ok = persist_skill_snapshot(user_id, target, snapshot_id=snapshot_id)
        output = f"Skill '{target}' snapshot {'succeeded' if ok else 'failed'}."
    elif action == "list_snapshots":
        snaps = list_skill_snapshots(user_id, target)
        output = f"Snapshots for '{target}': {', '.join(snaps) if snaps else 'none'}"
    else:
        output = f"Unknown action: {action}"

    return {
        "output": output,
        "state": {**state, "calls": calls, "last_action": action, "last_target": target},
    }
'''
    return f'''"""Runtime skill handler for {name}."""

def run(user_id: int, skill_name: str, input_text: str, state: dict) -> dict:
    calls = int(state.get("calls", 0)) + 1
    return {{
        "output": f"[{name}] {{input_text}}",
        "state": {{
            **state,
            "calls": calls,
            "last_input": input_text,
        }},
    }}
'''


def _ensure_skill_files(user_id: int, name: str, manifest: dict) -> None:
    skill_dir = _skill_dir(user_id, name)
    skill_dir.mkdir(parents=True, exist_ok=True)
    _manifest_path(user_id, name).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    handler_path = _handler_path(user_id, name)
    if not handler_path.exists():
        handler_path.write_text(_default_handler_source(name), encoding="utf-8")


def _load_skill_runner(user_id: int, name: str):
    handler_path = _handler_path(user_id, name)
    if not handler_path.exists():
        return None
    module_name = f"runtime_skill_{user_id}_{name}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "run", None)


def list_skills(user_id: int) -> list[dict]:
    return cache.get_skills(user_id)


def get_skill(user_id: int, name: str) -> dict | None:
    return cache.get_skill(user_id, name)


def install_skill(user_id: int, name: str, *, source_type: str = "builtin", source_ref: str = "", persist_mode: str = "none") -> dict:
    # Allow passing a GitHub URL as source_ref
    if source_ref and (source_ref.startswith("https://github.com/") or source_ref.startswith("https://raw.githubusercontent.com/")):
        remote = install_skill_from_github(user_id, source_ref, name_hint=name, persist_mode=persist_mode)
        if remote is not None:
            return remote

    manifest = _default_manifest(name, source_type, source_ref, persist_mode)
    skill = cache.add_skill(
        user_id,
        name=name,
        display_name=manifest.get("display_name") or name,
        source_type=source_type,
        source_ref=source_ref or name,
        version="1.0.0",
        enabled=True,
        install_status="installed",
        entrypoint="handler.py",
        manifest=manifest,
        capabilities=list(manifest.get("capabilities") or ["skill"]),
        persist_mode=persist_mode,
    )
    if skill is None:
        existing = cache.get_skill(user_id, name)
        if existing:
            return existing
        raise ValueError(f"skill install failed: {name}")

    _ensure_skill_files(user_id, name, manifest)
    cache.set_skill_state(
        user_id,
        name,
        {
            "state": {"installed": True, "calls": 0},
            "state_version": "1",
            "checkpoint_ref": "",
        },
    )
    return skill


def install_skill_from_github(user_id: int, github_url: str, *, name_hint: str = "", persist_mode: str = "none") -> dict | None:
    """Download and install a skill from a GitHub repo/directory URL."""
    raw_base = _to_github_raw_base(github_url)
    if raw_base is None:
        logger.warning("Not a valid GitHub URL: %s", github_url)
        return None

    manifest_raw = _github_fetch(f"{raw_base}/manifest.json")
    if manifest_raw is None:
        logger.warning("manifest.json not found at %s", raw_base)
        return None
    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except Exception as e:
        logger.warning("manifest.json parse failed from %s: %s", raw_base, e)
        return None

    name = str(manifest.get("name") or name_hint or "").strip().lower().replace(" ", "_") or "github_skill"
    entrypoint = str(manifest.get("entrypoint") or "handler.py")
    handler_raw = _github_fetch(f"{raw_base}/{entrypoint}")
    if handler_raw is None:
        logger.warning("entrypoint %s not found at %s", entrypoint, raw_base)
        return None

    skill = cache.add_skill(
        user_id,
        name=name,
        display_name=manifest.get("display_name") or name,
        source_type="github",
        source_ref=github_url,
        version=str(manifest.get("version") or "1.0.0"),
        enabled=True,
        install_status="installed",
        entrypoint=entrypoint,
        manifest=manifest,
        capabilities=list(manifest.get("capabilities") or ["skill"]),
        persist_mode=persist_mode or manifest.get("persist_mode") or "none",
    )
    if skill is None:
        existing = cache.get_skill(user_id, name)
        if existing:
            return existing
        return None

    skill_dir = _skill_dir(user_id, name)
    skill_dir.mkdir(parents=True, exist_ok=True)
    _manifest_path(user_id, name).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _handler_path(user_id, name).write_bytes(handler_raw)

    # Optionally download extra files listed in manifest
    extra_files: list[str] = manifest.get("extra_files") or []
    for fname in extra_files:
        data = _github_fetch(f"{raw_base}/{fname}")
        if data:
            dest = skill_dir / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

    # Optionally fetch pre-built workspace archive
    workspace_raw = _github_fetch(f"{raw_base}/workspace.tar.gz")
    if workspace_raw:
        archive_path = skill_dir / "workspace.tar.gz"
        archive_path.write_bytes(workspace_raw)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(skill_dir)
        archive_path.unlink(missing_ok=True)

    cache.set_skill_state(
        user_id,
        name,
        {
            "state": {"installed": True, "calls": 0, "source": github_url},
            "state_version": "1",
            "checkpoint_ref": "",
        },
    )
    logger.info("Skill %s installed from GitHub: %s", name, github_url)
    return skill


def enable_skill(user_id: int, name: str, enabled: bool = True) -> bool:
    return cache.update_skill(user_id, name, enabled=enabled, install_status="installed" if enabled else "disabled")


def remove_skill(user_id: int, name: str) -> bool:
    skill_dir = _skill_dir(user_id, name)
    if skill_dir.exists():
        for child in sorted(skill_dir.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        skill_dir.rmdir()
    cache.delete_skill_state(user_id, name)
    return cache.delete_skill(user_id, name)


def call_skill(user_id: int, name: str, input_text: str) -> str:
    skill = cache.get_skill(user_id, name)
    if not skill:
        return f"Skill not found: {name}"
    if not skill.get("enabled"):
        return f"Skill is disabled: {name}"

    runner = _load_skill_runner(user_id, name)
    if runner is None:
        return f"Skill handler missing: {name}"

    state_row = cache.get_skill_state(user_id, name) or {}
    state_payload = dict(state_row.get("state") or {})

    try:
        result = runner(user_id, name, input_text, state_payload)
    except Exception as exc:
        logger.exception("Skill execution failed: %s", name)
        cache.update_skill(user_id, name, last_error=str(exc))
        return f"Skill execution failed: {name} - {exc}"

    if isinstance(result, dict):
        output = str(result.get("output") or "")
        next_state = result.get("state") if isinstance(result.get("state"), dict) else state_payload
    else:
        output = str(result)
        next_state = state_payload

    cache.set_skill_state(
        user_id,
        name,
        {
            "state": next_state,
            "state_version": state_row.get("state_version", "1"),
            "checkpoint_ref": state_row.get("checkpoint_ref", ""),
        },
    )
    cache.update_skill(user_id, name, last_error="")
    return output or f"Skill {name} executed successfully."


def _build_workspace_archive(user_id: int, name: str) -> Path:
    skill_dir = _skill_dir(user_id, name)
    workspace_path = skill_dir / "workspace.tar.gz"
    with tarfile.open(workspace_path, "w:gz") as tar:
        for item in skill_dir.iterdir():
            if item.name == "workspace.tar.gz":
                continue
            tar.add(item, arcname=item.name)
    return workspace_path


def persist_skill_state(user_id: int, name: str) -> bool:
    return persist_skill_snapshot(user_id, name, snapshot_id="latest")


def persist_skill_snapshot(user_id: int, name: str, snapshot_id: str | None = None) -> bool:
    skill = cache.get_skill(user_id, name)
    if not skill:
        return False
    store = get_hf_dataset_store()
    if not store.enabled:
        return False

    snapshot_id = snapshot_id or _snapshot_id()
    prefix = _skill_hf_prefix(user_id, name)
    snapshot_prefix = f"{prefix}/snapshots/{snapshot_id}"
    state = cache.get_skill_state(user_id, name) or {"state": {}, "state_version": "1", "checkpoint_ref": ""}
    manifest = skill.get("manifest") or {}
    snapshots = list(manifest.get("snapshots") or [])
    if snapshot_id not in snapshots and snapshot_id != "latest":
        snapshots.append(snapshot_id)
        manifest["snapshots"] = snapshots
        cache.update_skill(user_id, name, manifest=manifest)
    _ensure_skill_files(user_id, name, manifest)
    workspace_path = _build_workspace_archive(user_id, name)

    index_payload = {
        "name": name,
        "version": skill.get("version", ""),
        "persist_mode": skill.get("persist_mode", "none"),
        "state_version": state.get("state_version", "1"),
        "current_snapshot": snapshot_id,
        "artifacts": {
            "state": f"{prefix}/state.json",
            "manifest": f"{prefix}/manifest.json",
            "workspace": f"{prefix}/workspace/workspace.tar.gz",
        },
        "restore_on_boot": bool(manifest.get("restore_on_boot")),
        "snapshots": snapshots,
    }

    ops = [
        store.put_json(f"{prefix}/state.json", state, commit_message=f"persist skill state: {name}"),
        store.put_json(f"{prefix}/manifest.json", manifest, commit_message=f"persist skill manifest: {name}"),
        store.put_json(f"{prefix}/index.json", index_payload, commit_message=f"persist skill index: {name}"),
        store.put_bytes(f"{prefix}/workspace/workspace.tar.gz", workspace_path.read_bytes(), commit_message=f"persist skill workspace: {name}"),
        store.put_json(f"{snapshot_prefix}/state.json", state, commit_message=f"snapshot skill state: {name}:{snapshot_id}"),
        store.put_json(f"{snapshot_prefix}/manifest.json", manifest, commit_message=f"snapshot skill manifest: {name}:{snapshot_id}"),
        store.put_json(f"{snapshot_prefix}/meta.json", {"snapshot_id": snapshot_id, "created_at": time.time()}, commit_message=f"snapshot skill meta: {name}:{snapshot_id}"),
        store.put_bytes(f"{snapshot_prefix}/workspace.tar.gz", workspace_path.read_bytes(), commit_message=f"snapshot skill workspace: {name}:{snapshot_id}"),
    ]
    if all(ops):
        cache.update_skill(user_id, name, last_persist_at=None, last_error="")
        cache.set_skill_state(
            user_id,
            name,
            {
                "state": state.get("state", {}),
                "state_version": state.get("state_version", "1"),
                "checkpoint_ref": snapshot_id,
            },
        )
        return True
    cache.update_skill(user_id, name, last_error="persist failed")
    return False


def list_skill_snapshots(user_id: int, name: str) -> list[str]:
    skill = cache.get_skill(user_id, name)
    if not skill:
        return []
    manifest = skill.get("manifest") or {}
    snapshots = list(manifest.get("snapshots") or [])
    state = cache.get_skill_state(user_id, name) or {}
    current = state.get("checkpoint_ref")
    if current and current not in snapshots:
        snapshots.insert(0, current)
    return snapshots


def restore_skill(user_id: int, name: str) -> bool:
    return restore_skill_snapshot(user_id, name, snapshot_id=None)


def restore_skill_snapshot(user_id: int, name: str, snapshot_id: str | None = None) -> bool:
    skill = cache.get_skill(user_id, name)
    if not skill:
        return False
    store = get_hf_dataset_store()
    if not store.enabled:
        return False

    prefix = _skill_hf_prefix(user_id, name)
    if snapshot_id:
        base = f"{prefix}/snapshots/{snapshot_id}"
        state = store.get_json(f"{base}/state.json")
        manifest = store.get_json(f"{base}/manifest.json")
        workspace = store.get_bytes(f"{base}/workspace.tar.gz")
    else:
        state = store.get_json(f"{prefix}/state.json")
        manifest = store.get_json(f"{prefix}/manifest.json")
        workspace = store.get_bytes(f"{prefix}/workspace/workspace.tar.gz")

    if state is None and manifest is None and workspace is None:
        return False

    if manifest:
        cache.update_skill(
            user_id,
            name,
            manifest=manifest,
            entrypoint=manifest.get("entrypoint", skill.get("entrypoint", "handler.py")),
            persist_mode=manifest.get("persist_mode", skill.get("persist_mode", "none")),
            last_error="",
        )
        _ensure_skill_files(user_id, name, manifest)

    skill_dir = _skill_dir(user_id, name)
    skill_dir.mkdir(parents=True, exist_ok=True)
    if workspace:
        archive_path = skill_dir / "workspace.tar.gz"
        archive_path.write_bytes(workspace)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(skill_dir)
        archive_path.unlink(missing_ok=True)

    if state:
        cache.set_skill_state(
            user_id,
            name,
            {
                "state": state.get("state", {}),
                "state_version": state.get("state_version", "1"),
                "checkpoint_ref": snapshot_id or state.get("checkpoint_ref", ""),
            },
        )
    return True


def auto_restore_skills(user_id: int) -> None:
    for skill in cache.get_skills(user_id):
        if not skill.get("enabled"):
            continue
        if skill.get("persist_mode") != "hf_git":
            continue
        manifest = skill.get("manifest") or {}
        if not manifest.get("restore_on_boot", True):
            continue
        try:
            restore_skill(user_id, skill["name"])
        except Exception:
            logger.exception("Failed to auto-restore skill %s for user %s", skill.get("name"), user_id)
