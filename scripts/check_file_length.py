#!/usr/bin/env python3
"""Fail when implementation files exceed max line count."""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_DIRS = ("core", "services", "platforms", "static")
DEFAULT_EXTS = {".py", ".js", ".css", ".html"}
SKIP_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
}


def should_skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)


def iter_targets(roots: list[str], exts: set[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if not path.is_file() or should_skip(path):
                continue
            if path.suffix.lower() in exts:
                files.append(path)
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-lines", type=int, default=100)
    parser.add_argument("--dirs", nargs="*", default=list(DEFAULT_DIRS))
    parser.add_argument("--ext", nargs="*", default=sorted(DEFAULT_EXTS))
    args = parser.parse_args()

    targets = iter_targets(args.dirs, {ext.lower() for ext in args.ext})
    violations: list[tuple[int, Path]] = []
    for path in targets:
        lines = count_lines(path)
        if lines > args.max_lines:
            violations.append((lines, path))

    if not violations:
        print(f"OK: checked {len(targets)} files (max={args.max_lines})")
        return 0

    print(f"Found {len(violations)} file(s) above {args.max_lines} lines:")
    for lines, path in violations:
        print(f"{lines:4d} {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

