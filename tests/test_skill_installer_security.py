"""Regression tests for external skill filesystem safety."""

from __future__ import annotations

from infrastructure.tools.skills import installer
from infrastructure.tools.skills.manifest import load_manifest


def test_manifest_rejects_path_like_name(tmp_path):
    plugin = tmp_path / "downloaded"
    plugin.mkdir()
    (plugin / "SKILL.md").write_text("---\nname: ../escaped\n---\nbody\n", encoding="utf-8")
    assert load_manifest(plugin, is_builtin=False) is None


def test_finalize_cannot_escape_plugin_directory(tmp_path, monkeypatch):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    downloaded = plugin_root / "downloaded"
    downloaded.mkdir()
    (downloaded / "SKILL.md").write_text("---\nname: ../escaped\n---\nbody\n", encoding="utf-8")

    monkeypatch.setattr(installer, "PLUGIN_DIR", plugin_root)

    result = installer._finalize(downloaded)
    assert result["ok"] is False
    assert not (tmp_path / "escaped").exists()


def test_uninstall_rejects_unsafe_name(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "PLUGIN_DIR", tmp_path / "plugins")
    result = installer.uninstall("../outside")
    assert result["ok"] is False
    assert "unsafe" in result["message"].lower()


def test_transactional_upgrade_can_restore_previous_install(tmp_path, monkeypatch):
    plugin_root = tmp_path / "plugins"
    old = plugin_root / "demo"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text(
        "---\nname: demo\nversion: '1'\ndescription: old\n---\nold body\n",
        encoding="utf-8",
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: demo\nversion: '2'\ndescription: new\n---\nnew body\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(installer, "PLUGIN_DIR", plugin_root)
    result = installer.install_from_local(source, transactional=True)
    assert "new body" in (old / "SKILL.md").read_text("utf-8")

    assert installer.rollback_install(result)["ok"] is True
    assert "old body" in (old / "SKILL.md").read_text("utf-8")
