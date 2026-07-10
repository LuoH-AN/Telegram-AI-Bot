"""Regression tests for safe URL fetching."""

from __future__ import annotations

import pytest

from infrastructure.tools.builtin.send_file import sources


class _Response:
    headers = {"Content-Length": "2", "Content-Type": "text/plain"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return b"ok"

    def geturl(self):
        return "https://cdn.example.com/file.txt"


class _Opener:
    def open(self, _request, timeout):
        assert timeout == 30
        return _Response()


def test_fetch_url_validates_initial_and_final_url(monkeypatch):
    checked: list[str] = []
    monkeypatch.setattr(sources, "_assert_safe_url", checked.append)
    monkeypatch.setattr(sources.urllib.request, "build_opener", lambda *_args: _Opener())

    data, name = sources.fetch_url("https://example.com/start", kind="document")
    assert data == b"ok"
    assert name == "file.txt"
    assert checked == ["https://example.com/start", "https://cdn.example.com/file.txt"]


def test_redirect_handler_rejects_unsafe_target_before_follow(monkeypatch):
    def reject(_url):
        raise ValueError("blocked redirect")

    monkeypatch.setattr(sources, "_assert_safe_url", reject)
    handler = sources._SafeRedirectHandler()
    with pytest.raises(ValueError, match="blocked redirect"):
        handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/private")
