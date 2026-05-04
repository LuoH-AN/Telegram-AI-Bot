"""Walk directories to find every SKILL.md."""

from __future__ import annotations

from pathlib import Path

from .manifest import SKILL_FILENAME


def discover_manifests(root: Path):
    """Yield top-level SKILL.md files: <root>/<plugin>/SKILL.md.

    Depth-1 only — nested SKILL.md inside a plugin's own resources/ are
    not treated as separate plugins.
    """
    for path in root.glob(f"*/{SKILL_FILENAME}"):
        yield path
