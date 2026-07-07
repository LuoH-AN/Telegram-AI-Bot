"""Walk directories to find every SKILL.md (depth-1 plugin layout)."""

from __future__ import annotations

from pathlib import Path

from .manifest import SKILL_FILENAME


def discover_skill_dirs(root: Path):
    """Yield top-level plugin dirs containing a SKILL.md: <root>/<plugin>/SKILL.md.

    Depth-1 only — nested SKILL.md inside a plugin's own resources/ are not
    treated as separate skills.
    """
    if not root.is_dir():
        return
    yield from root.glob(f"*/{SKILL_FILENAME}")
