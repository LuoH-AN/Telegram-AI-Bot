#!/usr/bin/env python3
"""Find files exceeding a max line threshold."""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_EXTS = {".py", ".js", ".css", ".html"}
DEFAULT_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
}


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)


def should_skip(path: Path, skip_dirs: set[str]) -> bool:
    return any(part in skip_dirs for part in path.parts)


def iter_candidates(root: Path, exts: set[str], skip_dirs: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or should_skip(path, skip_dirs):
            continue
        if path.suffix.lower() in exts:
            files.append(path)
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="root directory")
    parser.add_argument("--max-lines", type=int, default=100)
    parser.add_argument("--ext", nargs="*", default=sorted(DEFAULT_EXTS))
    parser.add_argument("--skip-dir", nargs="*", default=sorted(DEFAULT_SKIP_DIRS))
    parser.add_argument("--top", type=int, default=0, help="show only top N (0=all)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    exts = {ext.lower() for ext in args.ext}
    skip_dirs = set(args.skip_dir)

    rows: list[tuple[int, Path]] = []
    for path in iter_candidates(root, exts, skip_dirs):
        lines = count_lines(path)
        if lines > args.max_lines:
            rows.append((lines, path))

    rows.sort(reverse=True, key=lambda item: item[0])
    if args.top > 0:
        rows = rows[: args.top]

    print(f"root={root}")
    print(f"threshold>{args.max_lines}")
    print(f"count={len(rows)}")
    for lines, path in rows:
        rel = path.relative_to(root)
        print(f"{lines:5d} {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

