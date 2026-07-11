"""Backup includes dependency-style trees, hidden entries, empty dirs and links."""

from __future__ import annotations

import zipfile


def test_backup_has_no_dependency_or_hidden_directory_exclusions(monkeypatch, tmp_path):
    import entrypoints.launcher.backup as backup

    data = tmp_path / "data"
    destination = tmp_path / "backup"
    (data / "node_modules" / "package").mkdir(parents=True)
    (data / ".venv" / "lib" / "python" / "site-packages").mkdir(parents=True)
    (data / "empty-cache").mkdir(parents=True)
    (data / ".hidden").write_text("hidden", encoding="utf-8")
    (data / "node_modules" / "package" / "index.js").write_text("module", encoding="utf-8")
    (data / ".venv" / "lib" / "python" / "site-packages" / "dep.py").write_text("dep", encoding="utf-8")
    (data / "dependency-link").symlink_to("node_modules/package")
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "BACKUP_DIR", destination)
    monkeypatch.setattr(backup, "BACKUP_FILE", destination / "data.zip")
    monkeypatch.setattr(backup, "WORKSPACE_DIR", None)

    assert backup._snapshot() is True
    with zipfile.ZipFile(backup.BACKUP_FILE) as archive:
        names = set(archive.namelist())
    assert "node_modules/package/index.js" in names
    assert ".venv/lib/python/site-packages/dep.py" in names
    assert "empty-cache/" in names
    assert ".hidden" in names
    assert "dependency-link" in names

    for child in list(data.iterdir()):
        if child.is_dir() and not child.is_symlink():
            import shutil

            shutil.rmtree(child)
        else:
            child.unlink()
    assert backup.restore() is True
    assert (data / "node_modules" / "package" / "index.js").read_text("utf-8") == "module"
    assert (data / ".venv" / "lib" / "python" / "site-packages" / "dep.py").is_file()
    assert (data / "empty-cache").is_dir()
    assert (data / ".hidden").read_text("utf-8") == "hidden"
    assert (data / "dependency-link").is_symlink()


def test_terminal_environment_routes_dependency_managers_into_backup_data(monkeypatch, tmp_path):
    from shared.terminal_environment import build_persistent_terminal_env

    monkeypatch.setenv("BACKUP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("TERMINAL_PERSISTENT_ROOT", raising=False)
    env = build_persistent_terminal_env({"PATH": "/usr/bin"})
    root = tmp_path / "data" / "telegram_ai_bot" / "terminal" / "filesystem"

    assert env["HOME"].startswith(str(root))
    assert env["PIP_PREFIX"].startswith(str(root))
    assert env["NPM_CONFIG_PREFIX"].startswith(str(root))
    assert env["NVM_DIR"].startswith(str(root))
    assert env["FNM_DIR"].startswith(str(root))
    assert env["VOLTA_HOME"].startswith(str(root))
    assert env["COREPACK_HOME"].startswith(str(root))
    assert env["CARGO_HOME"].startswith(str(root))
    assert env["GOPATH"].startswith(str(root))
    assert env["UV_TOOL_DIR"].startswith(str(root))
    assert env["TMPDIR"].startswith(str(root))
    assert env["PATH"].startswith(str(root))


def test_bot_runtime_keeps_image_user_site_importable(monkeypatch, tmp_path):
    import subprocess
    import sys

    from shared.terminal_environment import build_persistent_runtime_env

    legacy_site = tmp_path / "legacy" / "site-packages"
    legacy_site.mkdir(parents=True)
    (legacy_site / "legacy_dependency.py").write_text("VALUE = 42\n", encoding="utf-8")
    monkeypatch.setenv("BACKUP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(sys, "path", [*sys.path, str(legacy_site)])
    env = build_persistent_runtime_env({"PATH": "/usr/bin", "HOME": "/original-home"})

    assert env["HOME"] == "/original-home"
    completed = subprocess.run(
        [sys.executable, "-c", "import legacy_dependency; assert legacy_dependency.VALUE == 42"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_terminal_backup_requests_are_coalesced_in_data_dir(monkeypatch, tmp_path):
    import entrypoints.launcher.backup as backup

    data = tmp_path / "data"
    request = data / ".backup-request"
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "REQUEST_FILE", request)
    monkeypatch.setenv("BACKUP_ENABLED", "1")

    backup.request_snapshot()
    backup.request_snapshot()
    assert request.is_file()


def test_backup_includes_complete_terminal_workspace(monkeypatch, tmp_path):
    import entrypoints.launcher.backup as backup

    data = tmp_path / "data"
    workspace = tmp_path / "workspace"
    destination = tmp_path / "backup"
    data.mkdir()
    (workspace / ".git").mkdir(parents=True)
    (workspace / "node_modules" / "pkg").mkdir(parents=True)
    (workspace / ".venv" / "bin").mkdir(parents=True)
    (workspace / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (workspace / "node_modules" / "pkg" / "index.js").write_text("module", encoding="utf-8")
    (workspace / ".venv" / "bin" / "python").write_text("binary", encoding="utf-8")
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "BACKUP_DIR", destination)
    monkeypatch.setattr(backup, "BACKUP_FILE", destination / "data.zip")
    monkeypatch.setattr(backup, "WORKSPACE_DIR", workspace)

    assert backup._snapshot() is True
    import shutil

    shutil.rmtree(workspace)
    workspace.mkdir()
    assert backup.restore() is True
    assert (workspace / ".git" / "HEAD").read_text("utf-8") == "ref"
    assert (workspace / "node_modules" / "pkg" / "index.js").is_file()
    assert (workspace / ".venv" / "bin" / "python").is_file()


def test_restore_does_not_roll_back_a_newer_current_workspace(monkeypatch, tmp_path):
    import entrypoints.launcher.backup as backup

    data = tmp_path / "data"
    workspace = tmp_path / "workspace"
    destination = tmp_path / "backup"
    data.mkdir()
    (workspace / ".git" / "refs" / "heads").mkdir(parents=True)
    (workspace / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (workspace / ".git" / "refs" / "heads" / "main").write_text("a" * 40 + "\n", encoding="utf-8")
    (workspace / "version.txt").write_text("old", encoding="utf-8")
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "BACKUP_DIR", destination)
    monkeypatch.setattr(backup, "BACKUP_FILE", destination / "data.zip")
    monkeypatch.setattr(backup, "WORKSPACE_DIR", workspace)
    monkeypatch.setattr(backup, "_git_commit", lambda _path: (workspace / ".git" / "refs" / "heads" / "main").read_text().strip())

    assert backup._snapshot() is True
    (workspace / ".git" / "refs" / "heads" / "main").write_text("b" * 40 + "\n", encoding="utf-8")
    (workspace / "version.txt").write_text("new", encoding="utf-8")
    (data / "state.txt").write_text("current", encoding="utf-8")

    assert backup.restore() is True
    assert (workspace / "version.txt").read_text("utf-8") == "new"
    assert (workspace / ".git" / "refs" / "heads" / "main").read_text().strip() == "b" * 40


def test_controlled_restart_can_explicitly_skip_workspace_restore(monkeypatch, tmp_path):
    import entrypoints.launcher.backup as backup

    data = tmp_path / "data"
    workspace = tmp_path / "workspace"
    destination = tmp_path / "backup"
    data.mkdir()
    workspace.mkdir()
    (workspace / "state.txt").write_text("backup", encoding="utf-8")
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "BACKUP_DIR", destination)
    monkeypatch.setattr(backup, "BACKUP_FILE", destination / "data.zip")
    monkeypatch.setattr(backup, "WORKSPACE_DIR", workspace)

    assert backup._snapshot() is True
    (workspace / "state.txt").write_text("live", encoding="utf-8")
    assert backup.restore(restore_workspace=False) is True
    assert (workspace / "state.txt").read_text("utf-8") == "live"
