"""Config file discovery and path helpers."""

from __future__ import annotations

import re
from pathlib import Path

from plugins.terminal.state import REPO_ROOT

CONFIG_SUFFIXES = {".json", ".ini", ".cfg", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {".git", "__pycache__", "runtime", ".venv", "venv", "node_modules"}
ENV_KEY_RE = re.compile(r'os\.getenv\(\s*["\']([A-Z0-9_]+)["\']')


def resolve_config_path(raw_path: str, *, must_exist: bool = False) -> Path:
    raw_text = str(raw_path or "").strip()
    if not raw_text:
        raise ValueError("path is required")
    target = Path(raw_text)
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


def ensure_supported_config_target(path: Path, file_format: str) -> None:
    suffix = path.suffix.lower()
    if file_format in {"env", "json", "ini"}:
        return
    if suffix in {".yaml", ".yml", ".toml", ".txt"}:
        return
    raise ValueError("project_config only supports repository config files, not source code files")


def discover_config_files(limit: int = 200) -> list[str]:
    found: list[str] = []
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
    files = list((REPO_ROOT / "config").rglob("*.py")) + list((REPO_ROOT / "launcher").rglob("*.py"))
    files += list((REPO_ROOT / "services").rglob("*.py")) + list((REPO_ROOT / "platforms").rglob("*.py")) + [REPO_ROOT / "main.py"]
    names: set[str] = set()
    for file_path in files:
        if not file_path.exists():
            continue
        text = file_path.read_text("utf-8", errors="ignore")
        names.update(ENV_KEY_RE.findall(text))
    return sorted(names)
