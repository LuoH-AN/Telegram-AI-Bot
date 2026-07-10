"""Skill manifest: real YAML frontmatter parsing for SKILL.md files.

A SKILL.md is markdown with optional YAML frontmatter:

    ---
    name: my-skill
    version: 1.0.0
    description: ...
    entry_point: infrastructure.tools.foo:FooTool   # optional, code skills only
    capabilities: [a, b]
    platforms: [telegram]
    ---

    (body — natural-language guidance, injected into the system prompt)

Uses pyyaml (robust: nesting, multiline, quoting). Falls back to a minimal
hand-parser only if pyyaml is somehow absent, so the bot still boots.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)
SKILL_FILENAME = "SKILL.md"
SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)


@dataclass(frozen=True)
class SkillManifest:
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    repository: str = ""
    dependencies: list[str] = field(default_factory=list)
    entry_point: str = ""
    capabilities: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    is_builtin: bool = False
    source_path: str = ""
    body: str = ""


def _split_frontmatter(text: str) -> tuple[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    return match.group(1), match.group(2)


def _parse_yaml(yaml_text: str) -> dict:
    try:
        import yaml

        data = yaml.safe_load(yaml_text)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("YAML frontmatter parse failed, using fallback: %s", exc)
        return _fallback_parse(yaml_text)


def _fallback_parse(yaml_text: str) -> dict:
    """Minimal key: value / [a, b] parser — only used without pyyaml."""
    meta: dict = {}
    for line in yaml_text.splitlines():
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        if raw.startswith("[") and raw.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in raw[1:-1].split(",") if v.strip()]
        else:
            meta[key] = raw.strip("\"'")
    return meta


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def load_manifest(path: Path, *, is_builtin: bool = False) -> SkillManifest | None:
    skill_path = path / SKILL_FILENAME if (path / SKILL_FILENAME).is_file() else path
    if not skill_path.is_file():
        return None
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read %s: %s", skill_path, exc)
        return None

    frontmatter, body = _split_frontmatter(text)
    meta = _parse_yaml(frontmatter)
    name = str(meta.get("name") or "").strip()
    if not name:
        logger.warning("SKILL.md at %s missing name", skill_path)
        return None
    if not SKILL_NAME_RE.fullmatch(name):
        logger.warning("SKILL.md at %s has unsafe name: %r", skill_path, name)
        return None

    return SkillManifest(
        name=name,
        version=str(meta.get("version", "1.0.0")),
        description=str(meta.get("description") or ""),
        author=str(meta.get("author") or ""),
        repository=str(meta.get("repository") or ""),
        dependencies=_as_list(meta.get("dependencies")),
        entry_point=str(meta.get("entry_point") or ""),
        capabilities=_as_list(meta.get("capabilities")),
        platforms=_as_list(meta.get("platforms")),
        is_builtin=is_builtin,
        source_path=str(skill_path.parent),
        body=body.strip(),
    )
