"""AST-based discovery of self-registering tool modules."""

from __future__ import annotations

import ast
import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _module_dotted(path: Path) -> str:
    parts = [path.stem]
    parent = path.parent
    while (parent / "__init__.py").exists():
        parts.append(parent.name)
        parent = parent.parent
    return ".".join(reversed(parts))


def _declares_tool(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return False
    for stmt in tree.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in stmt.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Name) and target.id == "tool":
                return True
    return False


def discover(root: Path | None = None) -> list[str]:
    base = Path(root) if root else Path(__file__).resolve().parent.parent
    imported: list[str] = []
    for path in sorted(base.rglob("*.py")):
        if path.name == "__init__.py" or "core" in path.parts:
            continue
        if not _declares_tool(path):
            continue
        module = _module_dotted(path)
        try:
            importlib.import_module(module)
            imported.append(module)
        except Exception as exc:
            logger.warning("Could not import tool module %s: %s", module, exc)
    return imported
