"""Installation and binary resolution for search service."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

import requests

from .constants import BIN_DIR, DEFAULT_REPO_URL, REPO_DIR, BASE_DIR


def repo_url() -> str:
    return os.getenv("SEARCH_REPO_URL", DEFAULT_REPO_URL).strip() or DEFAULT_REPO_URL


def ensure_repo() -> Path:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    if (REPO_DIR / ".git").exists():
        return REPO_DIR
    if REPO_DIR.exists():
        shutil.rmtree(REPO_DIR)
    run = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url(), str(REPO_DIR)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if run.returncode != 0:
        raise RuntimeError(f"git clone failed: {(run.stderr or run.stdout or '').strip()}")
    return REPO_DIR


def find_binary_candidates() -> list[Path]:
    return [
        BIN_DIR / "SoSearch",
        REPO_DIR / "target" / "release" / "SoSearch",
        REPO_DIR / "target" / "debug" / "SoSearch",
    ]


def ensure_binary() -> Path:
    for candidate in find_binary_candidates():
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    if shutil.which("cargo"):
        built = build_from_source()
        if built is not None:
            return built
    downloaded = download_release_binary()
    if downloaded is not None:
        return downloaded
    raise RuntimeError("Search binary unavailable. Install cargo or provide prebuilt binary.")


def build_from_source() -> Path | None:
    run = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=str(REPO_DIR),
        capture_output=True,
        text=True,
        timeout=900,
    )
    if run.returncode != 0:
        return None
    built = REPO_DIR / "target" / "release" / "SoSearch"
    if built.exists() and os.access(built, os.X_OK):
        return built
    return None


def release_asset_name() -> str | None:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "SoSearch-linux-amd64.tar.gz"
    if machine in {"aarch64", "arm64"}:
        return "SoSearch-linux-arm64.tar.gz"
    return None


def download_release_binary() -> Path | None:
    asset = release_asset_name()
    if asset is None:
        return None
    url = f"https://github.com/netlops/SoSearch/releases/latest/download/{asset}"
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    archive = BIN_DIR / asset
    try:
        with requests.get(url, timeout=60, stream=True) as resp:
            resp.raise_for_status()
            with open(archive, "wb") as handle:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        handle.write(chunk)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(path=str(BIN_DIR))
    except Exception:
        return None
    finally:
        try:
            archive.unlink(missing_ok=True)
        except Exception:
            pass
    binary = BIN_DIR / "SoSearch"
    if binary.exists():
        binary.chmod(0o755)
        return binary
    return None

