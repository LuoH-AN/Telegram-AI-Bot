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
    marker_root = plugin_root / ".installed"
    plugin_root.mkdir()
    marker_root.mkdir()
    downloaded = plugin_root / "downloaded"
    downloaded.mkdir()
    (downloaded / "SKILL.md").write_text("---\nname: ../escaped\n---\nbody\n", encoding="utf-8")

    monkeypatch.setattr(installer, "PLUGIN_DIR", plugin_root)
    monkeypatch.setattr(installer, "INSTALLED_MARKER", marker_root)

    result = installer._finalize(downloaded, "test")
    assert result["ok"] is False
    assert not (tmp_path / "escaped").exists()
    assert not (plugin_root / "escaped.json").exists()


def test_uninstall_rejects_unsafe_name(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "PLUGIN_DIR", tmp_path / "plugins")
    monkeypatch.setattr(installer, "INSTALLED_MARKER", tmp_path / "plugins" / ".installed")
    result = installer.uninstall("../outside")
    assert result["ok"] is False
    assert "unsafe" in result["message"].lower()


def test_transactional_upgrade_can_restore_previous_install(tmp_path, monkeypatch):
    plugin_root = tmp_path / "plugins"
    marker_root = plugin_root / ".installed"
    old = plugin_root / "demo"
    old.mkdir(parents=True)
    marker_root.mkdir()
    (old / "SKILL.md").write_text(
        "---\nname: demo\nversion: '1'\ndescription: old\n---\nold body\n",
        encoding="utf-8",
    )
    old_marker = b'{"name":"demo","version":"1"}'
    (marker_root / "demo.json").write_bytes(old_marker)
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: demo\nversion: '2'\ndescription: new\n---\nnew body\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(installer, "PLUGIN_DIR", plugin_root)
    monkeypatch.setattr(installer, "INSTALLED_MARKER", marker_root)
    result = installer.install_from_local(source, transactional=True)
    assert "new body" in (old / "SKILL.md").read_text("utf-8")

    assert installer.rollback_install(result)["ok"] is True
    assert "old body" in (old / "SKILL.md").read_text("utf-8")
    assert (marker_root / "demo.json").read_bytes() == old_marker
