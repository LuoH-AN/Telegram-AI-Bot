"""Walk directories to find all manifest.json files."""

from __future__ import annotations

from pathlib import Path


def discover_manifests(root: Path):
    """Recursively yield Path objects for every manifest.json found under *root*."""
    for path in root.rglob("manifest.json"):
        yield path