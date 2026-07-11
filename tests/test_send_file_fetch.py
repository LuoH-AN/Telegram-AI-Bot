"""Regression tests for safe URL fetching."""

from __future__ import annotations

import pytest

from infrastructure.tools import http_client
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
    monkeypatch.setattr(http_client, "assert_safe_url", checked.append)
    monkeypatch.setattr(http_client.urllib.request, "build_opener", lambda *_args: _Opener())

    data, name = sources.fetch_url("https://example.com/start", kind="document")
    assert data == b"ok"
    assert name == "file.txt"
    assert checked == ["https://example.com/start", "https://cdn.example.com/file.txt"]


def test_redirect_handler_rejects_unsafe_target_before_follow(monkeypatch):
    def reject(_url):
        raise ValueError("blocked redirect")

    monkeypatch.setattr(http_client, "assert_safe_url", reject)
    handler = http_client.SafeRedirectHandler()
    with pytest.raises(ValueError, match="blocked redirect"):
        handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/private")


def test_send_file_schema_only_accepts_existing_sources():
    import infrastructure.tools as tool_api
    from infrastructure.tools import get_tool_instructions

    tool = next(item for item in tool_api.get_all_tools("send_file") if item["function"]["name"] == "send_file")
    parameters = tool["function"]["parameters"]["properties"]

    assert "url" in parameters
    assert "path" not in parameters
    assert "prompt" not in parameters
    assert "size" not in parameters
    assert not hasattr(sources, "generate_image")
    assert "cannot generate" in get_tool_instructions("send_file").lower()


def test_local_file_delivery_is_admin_only(monkeypatch):
    import infrastructure.tools as tool_api

    monkeypatch.setattr(tool_api, "is_admin", lambda user_id: user_id == 1)
    regular = {item["function"]["name"] for item in tool_api.get_all_tools("send_file", user_id=2)}
    admin = {item["function"]["name"] for item in tool_api.get_all_tools("send_file", user_id=1)}

    assert "send_local_file" not in regular
    assert "send_local_file" in admin
