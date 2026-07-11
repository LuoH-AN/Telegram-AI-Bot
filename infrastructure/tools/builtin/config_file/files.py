"""Config file discovery and path helpers (config_file tool support)."""

from __future__ import annotations

import re
from pathlib import Path

from infrastructure.tools.builtin.terminal.state import REPO_ROOT
from infrastructure.tools.skills.manager import EXTERNAL_SKILL_DIR

CONFIG_SUFFIXES = {".json", ".ini", ".cfg", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {".git", "__pycache__", "runtime", ".venv", "venv", "node_modules"}
ENV_KEY_RE = re.compile(r'os\.getenv\(\s*["\']([A-Z0-9_]+)["\']')


def resolve_config_path(raw_path: str, *, must_exist: bool = False) -> Path:
    raw_text = str(raw_path or "").strip()
    if not raw_text:
        raise ValueError("path is required")
    target = Path(raw_path)
    full_path = target if target.is_absolute() else (REPO_ROOT / target)
    full_path = full_path.resolve()
    plugin_root = EXTERNAL_SKILL_DIR.expanduser().resolve()
    in_repo = full_path == REPO_ROOT or REPO_ROOT in full_path.parents
    in_plugin_root = full_path == plugin_root or plugin_root in full_path.parents
    if not in_repo and not in_plugin_root:
        raise ValueError("path must stay inside the repository or the managed plugin directory")
    if must_exist and not full_path.exists():
        raise FileNotFoundError(full_path)
    return full_path


def detect_format(path: Path, format_hint: str = "auto") -> str:
    hinted = str(format_hint or "auto").strip().lower()
    name = path.name.lower()
    if name == ".env" or name.startswith(".env."):
        expected = "env"
    elif path.suffix.lower() == ".json":
        expected = "json"
    elif path.suffix.lower() in {".ini", ".cfg"}:
        expected = "ini"
    else:
        expected = "text"
    if hinted != "auto" and hinted != expected:
        raise ValueError(f"format_hint={hinted} does not match {path.name} ({expected})")
    return expected


def is_external_skill_manifest(path: Path) -> bool:
    resolved = path.resolve()
    try:
        rel_path = resolved.relative_to(EXTERNAL_SKILL_DIR.expanduser().resolve())
        return len(rel_path.parts) == 2 and bool(rel_path.parts[0]) and rel_path.parts[1] == "SKILL.md"
    except ValueError:
        pass
    try:
        parts = resolved.relative_to(REPO_ROOT).parts
        return len(parts) == 4 and parts[:2] == ("runtime", "plugins") and bool(parts[2]) and parts[3] == "SKILL.md"
    except ValueError:
        return False


def ensure_supported_config_target(path: Path, file_format: str) -> None:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if file_format == "env" and (name == ".env" or name.startswith(".env.")):
        return
    if file_format == "json" and suffix == ".json":
        return
    if file_format == "ini" and suffix in {".ini", ".cfg"}:
        return
    if file_format == "text" and (is_external_skill_manifest(path) or suffix in {".yaml", ".yml", ".toml", ".txt"}):
        return
    raise ValueError("config_file supports declared config extensions and managed SKILL.md manifests, not source code files")


def discover_config_files(limit: int = 200) -> list[str]:
    found: list[str] = []
    for plugin_root in (EXTERNAL_SKILL_DIR.expanduser(), REPO_ROOT / "runtime" / "plugins"):
        if not plugin_root.is_dir():
            continue
        for path in plugin_root.glob("*/SKILL.md"):
            if REPO_ROOT in path.resolve().parents:
                label = str(path.resolve().relative_to(REPO_ROOT))
            else:
                label = str(path.resolve())
            found.append(label)
            if len(found) >= limit:
                return sorted(set(found))
    for path in REPO_ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        name = path.name.lower()
        if name == ".env" or name.startswith(".env.") or path.suffix.lower() in CONFIG_SUFFIXES:
            found.append(str(path.relative_to(REPO_ROOT)))
        if len(found) >= limit:
            break
    return sorted(set(found))


def discover_env_keys() -> list[str]:
    candidates = list((REPO_ROOT / "infrastructure").rglob("*.py")) + list((REPO_ROOT / "domain").rglob("*.py"))
    candidates += list((REPO_ROOT / "adapters").rglob("*.py")) + list((REPO_ROOT / "entrypoints").rglob("*.py")) + [REPO_ROOT / "main.py"]
    names: set[str] = set()
    for file_path in candidates:
        if not file_path.exists():
            continue
        text = file_path.read_text("utf-8", errors="ignore")
        names.update(ENV_KEY_RE.findall(text))
    return sorted(names)
