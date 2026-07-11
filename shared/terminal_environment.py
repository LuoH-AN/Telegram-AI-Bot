"""Persistent environment shared by terminal commands and launcher children."""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path
from typing import Mapping


def persistent_terminal_root() -> Path:
    configured = (os.getenv("TERMINAL_PERSISTENT_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    data_root = Path(os.getenv("BACKUP_DATA_DIR", "/data")).expanduser().resolve()
    return data_root / "telegram_ai_bot" / "terminal" / "filesystem"


def build_persistent_terminal_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Route package managers, caches, HOME and executable paths into backup data."""
    env = dict(base or os.environ)
    root = persistent_terminal_root()
    home = root / "home"
    dependencies = root / "dependencies"
    python_prefix = dependencies / "python"
    python_site = python_prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    paths = {
        "HOME": home,
        "XDG_CACHE_HOME": home / ".cache",
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_DATA_HOME": home / ".local" / "share",
        "XDG_STATE_HOME": home / ".local" / "state",
        "TMPDIR": root / "tmp",
        "PIP_PREFIX": python_prefix,
        "PYTHONUSERBASE": python_prefix,
        "PIP_CACHE_DIR": dependencies / "pip-cache",
        "NPM_CONFIG_PREFIX": dependencies / "npm",
        "NPM_CONFIG_CACHE": dependencies / "npm-cache",
        "NVM_DIR": dependencies / "nvm",
        "FNM_DIR": dependencies / "fnm",
        "VOLTA_HOME": dependencies / "volta",
        "COREPACK_HOME": dependencies / "corepack",
        "NODE_REPL_HISTORY": home / ".node_repl_history",
        "PNPM_HOME": dependencies / "pnpm",
        "BUN_INSTALL": dependencies / "bun",
        "CARGO_HOME": dependencies / "cargo",
        "RUSTUP_HOME": dependencies / "rustup",
        "GOPATH": dependencies / "go",
        "GOBIN": dependencies / "go" / "bin",
        "UV_CACHE_DIR": dependencies / "uv" / "cache",
        "UV_TOOL_DIR": dependencies / "uv" / "tools",
        "UV_TOOL_BIN_DIR": dependencies / "uv" / "bin",
        "PLAYWRIGHT_BROWSERS_PATH": dependencies / "playwright",
        "HF_HOME": dependencies / "huggingface",
        "TRANSFORMERS_CACHE": dependencies / "huggingface" / "transformers",
        "TORCH_HOME": dependencies / "torch",
    }
    for path in {root, *paths.values()}:
        Path(path).mkdir(parents=True, exist_ok=True)
    env.update({key: str(value) for key, value in paths.items()})

    persistent_bins = [
        python_prefix / "bin",
        dependencies / "npm" / "bin",
        dependencies / "volta" / "bin",
        dependencies / "fnm",
        dependencies / "pnpm",
        dependencies / "bun" / "bin",
        dependencies / "cargo" / "bin",
        dependencies / "go" / "bin",
        dependencies / "uv" / "bin",
        home / ".local" / "bin",
    ]
    nvm_versions = dependencies / "nvm" / "versions" / "node"
    if nvm_versions.is_dir():
        persistent_bins[0:0] = [
            version / "bin"
            for version in sorted(nvm_versions.iterdir(), reverse=True)
            if (version / "bin").is_dir()
        ]
    current_path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join([*(str(path) for path in persistent_bins), current_path])
    current_pythonpath = env.get("PYTHONPATH", "")
    inherited_sites: list[str] = []
    for candidate in [*sys.path, *site.getsitepackages(), site.getusersitepackages()]:
        text = str(candidate or "")
        if text and ("site-packages" in text or "dist-packages" in text) and text not in inherited_sites:
            inherited_sites.append(text)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(python_site), current_pythonpath, *inherited_sites) if part
    )
    env.setdefault("PIP_BREAK_SYSTEM_PACKAGES", "1")
    env.setdefault("PIP_ROOT_USER_ACTION", "ignore")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    return env


def build_persistent_runtime_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Expose persistent tools to the bot without replacing its image HOME/user-site."""
    original = dict(base or os.environ)
    env = build_persistent_terminal_env(original)
    for key in (
        "HOME",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "TMPDIR",
        "PYTHONUSERBASE",
    ):
        if key in original:
            env[key] = original[key]
        else:
            env.pop(key, None)
    return env
