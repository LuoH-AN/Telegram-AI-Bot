"""Tests for send_file source security (SSRF + path sandbox)."""

from __future__ import annotations

import pytest

from infrastructure.tools.builtin.send_file import sources


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://metadata.google.internal/",
        "ftp://example.com/x",
        "file:///etc/passwd",
        "gopher://x",
        "https://user:password@example.com/private",
    ],
)
def test_url_blocked(url):
    with pytest.raises(ValueError):
        sources._assert_safe_url(url)


def test_safe_public_url_allowed():
    # A resolvable public host that is not private/loopback; not actually fetched here.
    sources._assert_safe_url("https://example.com/image.png")


def test_path_outside_roots_blocked():
    with pytest.raises(ValueError):
        sources._assert_safe_path(__import__("pathlib").Path("/etc/passwd"))


def test_path_secret_file_blocked(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SECRET=x")
    with pytest.raises(ValueError):
        sources._assert_safe_path(env)


def test_path_inside_root_allowed(tmp_path):
    f = tmp_path / "ok.txt"
    f.write_text("hi")

    import infrastructure.tools.builtin.send_file.sources as src

    orig = src.TOOL_FILE_ROOTS
    src.TOOL_FILE_ROOTS = [tmp_path]
    try:
        resolved = src._assert_safe_path(f)
        assert resolved == f.resolve()
    finally:
        src.TOOL_FILE_ROOTS = orig
