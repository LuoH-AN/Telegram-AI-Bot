"""Strict terminal filesystem and persistent active-workspace behavior."""

from __future__ import annotations

import io
import asyncio
import json
import tarfile
from pathlib import Path

import pytest


def _seed(path: Path) -> None:
    with tarfile.open(path, "w:gz") as archive:
        payload = b"#!/bin/sh\n"
        info = tarfile.TarInfo("bin/bash")
        info.mode = 0o755
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def test_proot_rootfs_is_initialized_below_data_and_used_for_commands(monkeypatch, tmp_path):
    import infrastructure.tools.builtin.terminal.rootfs as rootfs

    seed = tmp_path / "seed.tar.gz"
    _seed(seed)
    persistent = tmp_path / "data" / "terminal"
    monkeypatch.setenv("TERMINAL_FILESYSTEM_MODE", "proot")
    monkeypatch.setenv("TERMINAL_PERSISTENT_ROOT", str(persistent))
    monkeypatch.setenv("TERMINAL_ROOTFS_SEED", str(seed))
    monkeypatch.setenv("TERMINAL_WORKSPACE_DIR", str(tmp_path / "data" / "workspace"))
    monkeypatch.setattr(rootfs.shutil, "which", lambda name: "/usr/bin/proot" if name == "proot" else None)

    command = rootfs.terminal_command("touch /usr/local/bin/demo", Path("/data/workspace"))

    assert (persistent / "rootfs" / "bin" / "bash").is_file()
    assert (persistent / "rootfs" / "opt" / "telegram-ai-bot").is_symlink()
    assert command[:4] == ["/usr/bin/proot", "-0", "-r", str(persistent / "rootfs")]
    assert command[-5:] == ["-w", "/data/workspace", "/bin/bash", "-lc", "touch /usr/local/bin/demo"]


def test_missing_proot_is_a_hard_error(monkeypatch, tmp_path):
    import infrastructure.tools.builtin.terminal.rootfs as rootfs

    monkeypatch.setenv("TERMINAL_FILESYSTEM_MODE", "proot")
    monkeypatch.setenv("TERMINAL_PERSISTENT_ROOT", str(tmp_path / "persistent"))
    monkeypatch.setattr(rootfs.shutil, "which", lambda _name: None)

    with pytest.raises(rootfs.TerminalRootfsError, match="rebuild the image"):
        rootfs.ensure_rootfs()


def test_terminal_reports_missing_persistent_filesystem_as_tool_error(monkeypatch, tmp_path):
    from infrastructure.tools.core import ToolContext
    import infrastructure.tools.builtin.terminal.rootfs as rootfs
    import infrastructure.tools.builtin.terminal.terminal as terminal_module

    monkeypatch.setenv("TERMINAL_FILESYSTEM_MODE", "proot")
    monkeypatch.setenv("TERMINAL_PERSISTENT_ROOT", str(tmp_path / "persistent"))
    monkeypatch.setattr(rootfs.shutil, "which", lambda _name: None)

    result = asyncio.run(terminal_module.terminal(ToolContext(user_id=1), "echo test"))
    assert result.ok is False
    assert json.loads(result.content)["error"]["code"] == "persistent_filesystem_unavailable"


def test_application_workspace_is_created_inside_data_without_exclusions(monkeypatch, tmp_path):
    import entrypoints.launcher.workspace as workspace

    packaged = tmp_path / "image" / "app"
    (packaged / "entrypoints").mkdir(parents=True)
    (packaged / "entrypoints" / "main.py").write_text("main = True\n", encoding="utf-8")
    (packaged / "node_modules" / "pkg").mkdir(parents=True)
    (packaged / "node_modules" / "pkg" / "index.js").write_text("module", encoding="utf-8")
    (packaged / ".hidden").write_text("hidden", encoding="utf-8")
    active = tmp_path / "data" / "workspace"
    monkeypatch.setenv("TERMINAL_WORKSPACE_DIR", str(active))

    assert workspace.prepare_active_workspace(packaged) == active
    assert (active / "entrypoints" / "main.py").is_file()
    assert (active / "node_modules" / "pkg" / "index.js").is_file()
    assert (active / ".hidden").is_file()

    (active / "user-created.txt").write_text("keep", encoding="utf-8")
    workspace.prepare_active_workspace(packaged)
    assert (active / "user-created.txt").read_text("utf-8") == "keep"
