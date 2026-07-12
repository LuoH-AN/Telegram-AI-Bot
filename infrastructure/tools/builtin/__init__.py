"""Explicit builtin-tool module list; importing a module registers its tools."""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

TOOL_MODULES = (
    "infrastructure.tools.builtin.config_file.config_file",
    "infrastructure.tools.builtin.database.conversations",
    "infrastructure.tools.builtin.database.cron",
    "infrastructure.tools.builtin.database.personas",
    "infrastructure.tools.builtin.database.sessions",
    "infrastructure.tools.builtin.database.settings",
    "infrastructure.tools.builtin.database.skill_state",
    "infrastructure.tools.builtin.database.skills",
    "infrastructure.tools.builtin.database.tokens",
    "infrastructure.tools.builtin.memory.memory",
    "infrastructure.tools.builtin.search.search",
    "infrastructure.tools.builtin.send_file.send_file",
    "infrastructure.tools.builtin.terminal.terminal",
)


def load_builtin_tools() -> list[str]:
    loaded: list[str] = []
    for module in TOOL_MODULES:
        try:
            importlib.import_module(module)
            loaded.append(module)
        except Exception as exc:
            logger.warning("Could not import tool module %s: %s", module, exc)
    return loaded


__all__ = ["TOOL_MODULES", "load_builtin_tools"]
