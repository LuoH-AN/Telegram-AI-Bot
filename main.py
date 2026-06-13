"""Compatibility entrypoints.launcher for container and local starts."""

from entrypoints.main import main


if __name__ == "__main__":
    raise SystemExit(main())
