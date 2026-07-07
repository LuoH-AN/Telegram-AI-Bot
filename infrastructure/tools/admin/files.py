"""Config file discovery and path helpers (config_file tool support)."""

from __future__ import annotations

import re
from pathlib import Path

from infrastructure.tools.system.state import REPO_ROOT

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
    if full_path != REPO_ROOT and REPO_ROOT not in full_path.parents:
        raise ValueError("path must stay inside repository root")
    if must_exist and not full_path.exists():
        raise FileNotFoundError(full_path)
    return full_path


def detect_format(path: Path, format_hint: str = "auto") -> str:
    hinted = str(format_hint or "auto").strip().lower()
    if hinted in {"env", "json", "ini", "text"}:
        return hinted
    name = path.name.lower()
    if name == ".env" or name.startswith(".env."):
        return "env"
    if path.suffix.lower() == ".json":
        return "json"
    if path.suffix.lower() in {".ini", ".cfg"}:
        return "ini"
    return "text"


def is_external_skill_manifest(path: Path) -> bool:
    try:
        rel_path = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    parts = rel_path.parts
    return len(parts) == 4 and parts[0] == "runtime" and parts[1] == "plugins" and bool(parts[2]) and parts[3] == "SKILL.md"


def ensure_supported_config_target(path: Path, file_format: str) -> None:
    suffix = path.suffix.lower()
    if file_format in {"env", "json", "ini"}:
        return
    if file_format == "text" and is_external_skill_manifest(path):
        return
    if suffix in {".yaml", ".yml", ".toml", ".txt"}:
        return
    raise ValueError("config_file supports config files and runtime/plugins/<name>/SKILL.md manifests, not source code files")


def discover_config_files(limit: int = 200) -> list[str]:
    found: list[str] = []
    plugin_root = REPO_ROOT / "runtime" / "plugins"
    if plugin_root.is_dir():
        for path in plugin_root.glob("*/SKILL.md"):
            found.append(str(path.relative_to(REPO_ROOT)))
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
