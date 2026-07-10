"""Regression tests for OpenAPI authentication and terminal identity."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_openapi_tools_fail_closed_without_token(monkeypatch):
    from adapters.http.openapi_tools.search_routes import build_search_app

    monkeypatch.delenv("OPENAPI_TOOLS_TOKEN", raising=False)
    response = TestClient(build_search_app()).post("/status", json={})
    assert response.status_code == 503


def test_openapi_tools_require_matching_bearer_token(monkeypatch):
    from adapters.http.openapi_tools.search_routes import build_search_app

    monkeypatch.setenv("OPENAPI_TOOLS_TOKEN", "secret-token")
    client = TestClient(build_search_app())
    assert client.post("/status", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/status", json={}, headers={"Authorization": "Bearer secret-token"}).status_code == 200


def test_terminal_openapi_identity_must_be_configured_admin(monkeypatch):
    import adapters.http.openapi_tools.terminal_routes as routes

    monkeypatch.delenv("OPENAPI_TOOLS_USER_ID", raising=False)
    with pytest.raises(HTTPException) as missing:
        routes._openapi_user_id()
    assert missing.value.status_code == 503

    monkeypatch.setenv("OPENAPI_TOOLS_USER_ID", "123")
    monkeypatch.setattr(routes, "is_admin", lambda _user_id: False)
    with pytest.raises(HTTPException) as forbidden:
        routes._openapi_user_id()
    assert forbidden.value.status_code == 403

    monkeypatch.setattr(routes, "is_admin", lambda user_id: user_id == 123)
    assert routes._openapi_user_id() == 123
