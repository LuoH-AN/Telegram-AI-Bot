"""SKILL.md loader — Anthropic Claude Skills format.

A SKILL.md is a markdown file with optional YAML frontmatter:

    ---
    name: my-skill
    description: ...
    entry_point: plugins.foo.tool:FooTool   # optional — only for code plugins
    capabilities: [a, b]
    platforms: [telegram, wechat]
    ---

    (skill body — natural-language guidance for the model)

Plugins WITHOUT entry_point are prompt-only: their body is injected into the
system prompt and any bundled scripts/ directory is exposed to the model so it
can invoke them via the `terminal` plugin.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"


@dataclass(frozen=True)
class PluginManifest:
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
    body: str = ""


def load_manifest_from_path(path: Path, *, is_builtin: bool = False) -> PluginManifest | None:
    skill_path = path / SKILL_FILENAME
    if not skill_path.is_file():
        return None
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read %s: %s", skill_path, exc)
        return None

    meta, body = _split_frontmatter(text)
    name = (meta.get("name") or _heuristic_name(text) or "").strip()
    if not name:
        logger.warning("SKILL.md at %s missing name", skill_path)
        return None

    clean_body = _strip_heuristic_header(body, name)

    return PluginManifest(
        name=name,
        version=str(meta.get("version", "1.0.0")),
        description=str(meta.get("description") or _heuristic_desc(text)),
        author=str(meta.get("author", "")),
        repository=str(meta.get("repository", "")),
        dependencies=_as_list(meta.get("dependencies")),
        entry_point=str(meta.get("entry_point", "")),
        capabilities=_as_list(meta.get("capabilities")),
        platforms=_as_list(meta.get("platforms")),
        is_builtin=is_builtin,
        source_path=str(path),
        body=clean_body.strip(),
    )


def _split_frontmatter(text: str) -> tuple[dict, str]:
    fm = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not fm:
        return {}, text
    meta: dict = {}
    for line in fm.group(1).splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith("[") and raw.endswith("]"):
            meta[key] = [v.strip().strip('"\'') for v in raw[1:-1].split(",") if v.strip()]
        else:
            meta[key] = raw.strip('"\'')
    return meta, fm.group(2)


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and v:
        return [v]
    return []


def _heuristic_name(text: str) -> str | None:
    h1 = re.search(r"^#\s+`?([^\s`]+)`?\s*$", text, re.M)
    return h1.group(1).strip() if h1 else None


def _heuristic_desc(text: str) -> str:
    m = re.search(r"^\*\*Description:\*\*\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def _strip_heuristic_header(body: str, name: str) -> str:
    pattern = rf"^#\s+`?{re.escape(name)}`?\s*\n"
    body = re.sub(pattern, "", body, count=1, flags=re.M)
    body = re.sub(r"^\*\*Name:\*\*\s*`?[^`]+`?\s*\n", "", body, count=1, flags=re.M)
    body = re.sub(r"^\*\*Description:\*\*\s*.+\n", "", body, count=1, flags=re.M)
    return body.strip()
