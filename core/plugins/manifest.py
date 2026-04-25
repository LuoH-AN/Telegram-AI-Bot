"""Plugin manifest schema and parser."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginManifest:
    schema_version: str
    name: str
    version: str
    description: str
    author: str
    repository: str
    dependencies: list[str]
    entry_point: str
    capabilities: list[str]
    platforms: list[str]
    is_builtin: bool = False
    source_path: str = ""

    def to_json(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "repository": self.repository,
            "dependencies": self.dependencies,
            "entry_point": self.entry_point,
            "capabilities": self.capabilities,
            "platforms": self.platforms,
        }


MANIFEST_FILENAME = "manifest.json"
_REQUIRED_FIELDS = {"schema_version", "name", "entry_point"}


def load_manifest_from_path(path: Path, *, is_builtin: bool = False) -> PluginManifest | None:
    manifest_path = path / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read manifest at %s: %s", manifest_path, exc)
        return None

    missing = _REQUIRED_FIELDS - set(raw.keys())
    if missing:
        logger.warning("Manifest at %s missing required fields: %s", manifest_path, missing)
        return None

    schema_version = str(raw.get("schema_version", "1.0"))
    name = str(raw["name"]).strip()
    if not name:
        logger.warning("Manifest at %s has empty name", manifest_path)
        return None

    return PluginManifest(
        schema_version=schema_version,
        name=name,
        version=str(raw.get("version", "1.0.0")),
        description=str(raw.get("description", "")),
        author=str(raw.get("author", "")),
        repository=str(raw.get("repository", "")),
        dependencies=list(raw.get("dependencies") or []),
        entry_point=str(raw["entry_point"]),
        capabilities=list(raw.get("capabilities") or []),
        platforms=list(raw.get("platforms") or []),
        is_builtin=is_builtin,
        source_path=str(path),
    )
