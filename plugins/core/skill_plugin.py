"""Adapter: prompt-only Claude Skill (no entry_point) → BasePlugin."""

from __future__ import annotations

from pathlib import Path

from .base import BasePlugin
from .manifest import PluginManifest


class SkillPlugin(BasePlugin):
    """Contributes SKILL.md guidance to system prompt; owns no tool calls.

    The model invokes any bundled scripts via the `terminal` plugin.
    """

    def __init__(self, manifest: PluginManifest):
        self._manifest = manifest

    @property
    def name(self) -> str:
        return self._manifest.name

    def definitions(self) -> list[dict]:
        return []

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        return None

    def get_instruction(self) -> str:
        scripts_dir = Path(self._manifest.source_path) / "scripts"
        lines = [f"\n## Skill: {self._manifest.name}"]
        if self._manifest.description:
            lines.append(self._manifest.description)
        if scripts_dir.is_dir():
            scripts = [f.name for f in scripts_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
            if scripts:
                lines.append(f"Scripts directory: {scripts_dir}")
                lines.append("Invoke via terminal tool, e.g.:")
                for s in scripts[:3]:
                    lines.append(f'  {{"action":"exec","command":"python3 {scripts_dir}/{s} <args>"}}')
        lines.append("")
        return "\n".join(lines) + self._manifest.body + "\n"
