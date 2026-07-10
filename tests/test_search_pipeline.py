"""Regression tests for Exa ranking, caching, and search-tool safety."""

from __future__ import annotations

import asyncio
import importlib
import json
from email.message import Message

from infrastructure.tools.core import ToolContext
from infrastructure.tools.http_client import FetchedResource


class _Pool:
    def __init__(self) -> None:
        self.successes = []
        self.failures = []

    def snapshot(self):
        return {"configured": 1, "available": 1, "keys": []}

    def acquire(self):
        return "exa-test-key"

    def report_success(self, key):
        self.successes.append(key)

    def report_failure(self, key, kind, message=""):
        self.failures.append((key, kind, message))


class _Response:
    status_code = 200
    text = ""

    def json(self):
        return {
            "requestId": "request-test",
            "costDollars": {"total": 0.007, "search": {"neural": 0.007}},
            "results": [
                {
                    "title": "落憾：名称与相关资料",
                    "url": "https://example.com/luohan?utm_source=test",
                    "highlights": ["落憾相关正文证据，介绍名称来源和公开资料。"],
                    "author": "Example Author",
                },
                {
                    "title": "落憾重复链接",
                    "url": "https://example.com/luohan",
                    "highlights": ["重复结果"],
                },
                {
                    "title": "无关页面",
                    "url": "https://other.example/news",
                    "highlights": ["普通新闻内容"],
                },
            ],
        }


def test_exa_search_reranks_deduplicates_and_caches(monkeypatch):
    from infrastructure.tools.builtin.search import exa

    calls = []
    pool = _Pool()
    exa.SEARCH_CACHE.clear()
    monkeypatch.setenv("EXA_CACHE_TTL", "300")
    monkeypatch.setenv("EXA_SEARCH_TYPE", "auto")
    monkeypatch.setattr(exa, "KEY_POOL", pool)
    monkeypatch.setattr(exa, "enrich_results", lambda *_args, **_kwargs: None)

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(exa.requests, "post", post)
    first = exa.search_once(query="落憾", top_k=8, timeout_seconds=20)
    second = exa.search_once(query="落憾", top_k=8, timeout_seconds=20)

    assert first["ok"] is True
    assert first["results"][0]["title"].startswith("落憾")
    assert first["results"][0]["source_id"] == 1
    assert first["results"][0]["url"] == "https://example.com/luohan"
    assert first["returned"] == 2
    assert second["cached"] is True
    assert len(calls) == 1
    assert first["request_id"] == "request-test"
    assert first["cost_dollars"]["total"] == 0.007
    assert calls[0][1]["json"]["type"] == "auto"
    assert calls[0][1]["json"]["numResults"] == 8
    assert calls[0][1]["json"]["contents"] == {"highlights": True}
    assert calls[0][1]["json"]["moderation"] is False
    assert calls[0][1]["headers"]["x-api-key"] == "exa-test-key"
    assert pool.successes == ["exa-test-key"]
    exa.SEARCH_CACHE.clear()


def test_search_tool_propagates_backend_failure(monkeypatch):
    search_module = importlib.import_module("infrastructure.tools.builtin.search.search")
    monkeypatch.setattr(
        search_module,
        "search_once",
        lambda **_kwargs: {"ok": False, "message": "quota exhausted"},
    )

    result = asyncio.run(search_module.search(ToolContext(user_id=1), "search", query="落憾"))
    payload = json.loads(result.content)
    assert result.ok is False
    assert payload["error"]["code"] == "search_failed"
    assert "quota exhausted" in payload["error"]["message"]


def test_search_instruction_requires_citations_and_treats_web_as_untrusted():
    search_module = importlib.import_module("infrastructure.tools.builtin.search.search")
    instruction = search_module.SEARCH_INSTRUCTION.lower()
    assert "untrusted" in instruction
    assert "cite sources" in instruction


def test_page_content_extraction_removes_scripts_and_navigation(monkeypatch):
    from infrastructure.tools.builtin.search import content

    headers = Message()
    headers["Content-Type"] = "text/html; charset=utf-8"
    resource = FetchedResource(
        data=(
            "<html><nav>菜单</nav><script>ignore me</script>"
            "<article><h1>落憾</h1><p>这是正文证据。</p></article></html>"
        ).encode(),
        final_url="https://example.com/luohan",
        content_type="text/html; charset=utf-8",
        headers=headers,
    )
    monkeypatch.setattr(content, "download_url", lambda *_args, **_kwargs: resource)
    text = content.fetch_page_text("https://example.com/luohan")
    assert "落憾" in text
    assert "这是正文证据" in text
    assert "菜单" not in text
    assert "ignore me" not in text


def test_key_pool_detects_runtime_key_changes(monkeypatch):
    from infrastructure.tools.builtin.search.keypool import KeyPool

    monkeypatch.setenv("EXA_API_KEYS", "key-a")
    pool = KeyPool()
    assert pool.acquire() == "key-a"
    monkeypatch.setenv("EXA_API_KEYS", "key-b")
    assert pool.acquire() == "key-b"


def test_tool_round_limit_forces_a_final_request(monkeypatch):
    generate = importlib.import_module("adapters.telegram.handlers.messages.chat.generate")
    tools_module = importlib.import_module("infrastructure.tools")
    tool_calls_seen = []
    process_calls = []

    class ToolCall:
        def __init__(self, identifier: str):
            self.id = identifier
            self.name = "search"
            self.arguments = '{"action":"search","query":"落憾"}'

    responses = [
        ("", {}, 0.0, "tool_calls", "", [ToolCall("call-1")]),
        ("", {}, 0.0, "tool_calls", "", [ToolCall("call-2")]),
        ("done", {}, 0.0, "stop", "", []),
    ]

    async def fake_stream(*_args, **kwargs):
        tool_calls_seen.append(kwargs.get("tools"))
        return responses.pop(0)

    async def fake_process(*_args, **_kwargs):
        process_calls.append(True)
        return [{"role": "tool", "tool_call_id": "call-1", "content": '{"ok":true}'}]

    class Pump:
        async def drain(self):
            return None

    class Outbound:
        async def deliver_final(self, _text):
            return True

    class Runtime:
        render_pump = Pump()
        outbound = Outbound()
        tool_event_callback = None

        async def stream_update(self, _text):
            return True

        async def status_update(self, _text):
            return True

        def clear_placeholder(self):
            return None

    monkeypatch.setattr(generate, "stream_response", fake_stream)
    monkeypatch.setattr(generate, "MAX_TOOL_ROUNDS", 1)
    monkeypatch.setattr(tools_module, "get_all_tools", lambda **_kwargs: [{"type": "function"}])
    monkeypatch.setattr(tools_module, "process_tool_calls", fake_process)

    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "落憾"}]
    result = asyncio.run(
        generate.generate_with_tools(
            client=object(),
            messages=messages,
            settings={"model": "test", "temperature": 0.2},
            user_id=1,
            ctx="test",
            runtime=Runtime(),
        )
    )
    assert result["final_text"] == "done"
    assert process_calls == [True]
    assert tool_calls_seen == [[{"type": "function"}], [{"type": "function"}], []]
    assert any("tool_round_limit" in message.get("content", "") for message in messages)
