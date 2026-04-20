"""Unit tests for the Sacred Brain MCP handlers (transport-agnostic)."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from services.sacred_mcp.handlers import (
    SacredBrainConfig,
    _parse_scope_path,
    list_scopes,
    log_memory,
    recall_scope,
    search_memory,
)


def _cfg(**overrides):
    base = dict(
        hippocampus_url="http://hippo.test",
        governor_url="http://gov.test",
        api_key="test-key",
    )
    base.update(overrides)
    return SacredBrainConfig(**base)


def _patch_client(monkeypatch, handler):
    """Monkeypatch httpx.AsyncClient to use a MockTransport with `handler`."""
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def _factory(**kw):
        kw.setdefault("transport", transport)
        return original(**kw)

    monkeypatch.setattr(httpx, "AsyncClient", _factory)


def test_search_memory_uses_bound_user_id(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query_params"] = dict(request.url.params)
        captured["api_key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json={"memories": [{"id": "m1", "text": "hello"}]})

    _patch_client(monkeypatch, handler)

    cfg = _cfg(default_user_id="sam")
    out = asyncio.run(search_memory(cfg, query="hi", limit=3))

    assert captured["path"] == "/memories/sam"
    assert captured["query_params"]["query"] == "hi"
    assert captured["query_params"]["limit"] == "3"
    assert captured["api_key"] == "test-key"
    assert out["user_id"] == "sam"
    assert out["memories"][0]["id"] == "m1"


def test_search_memory_requires_user_id_when_unbound():
    cfg = _cfg()
    with pytest.raises(ValueError, match="user_id required"):
        asyncio.run(search_memory(cfg, query="hi"))


def test_search_memory_explicit_user_overrides_default(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"memories": []})

    _patch_client(monkeypatch, handler)

    cfg = _cfg(default_user_id="sam")
    asyncio.run(search_memory(cfg, query="x", user_id="david"))
    assert captured["path"] == "/memories/david"


def test_recall_scope_builds_nested_scope(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": [{"text": "a"}]})

    _patch_client(monkeypatch, handler)

    cfg = _cfg(default_user_id="sam")
    asyncio.run(recall_scope(cfg, scope="project:sacred-brain/user:sam", limit=5))

    body = captured["body"]
    assert body["user_id"] == "sam"
    assert body["k"] == 5
    scope = body["filters"]["scope"]
    assert scope["kind"] == "project"
    assert scope["id"] == "sacred-brain"
    assert scope["parent"]["kind"] == "user"
    assert scope["parent"]["id"] == "sam"
    assert scope["parent"]["parent"] is None


def test_parse_scope_path_single_segment():
    node = _parse_scope_path("user:sam")
    assert node == {"kind": "user", "id": "sam", "parent": None}


def test_parse_scope_path_rejects_empty():
    with pytest.raises(ValueError):
        _parse_scope_path("")


def test_parse_scope_path_rejects_malformed():
    with pytest.raises(ValueError, match="missing ':'"):
        _parse_scope_path("project/user:sam")


def test_log_memory_uses_write_default(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "stored", "memory_id": "m42"})

    _patch_client(monkeypatch, handler)

    cfg = _cfg(default_user_id="sam", default_write_user_id="coding")
    out = asyncio.run(log_memory(cfg, text="remember this"))

    assert captured["path"] == "/remember"
    body = captured["body"]
    assert body["user_id"] == "coding"
    assert body["text"] == "remember this"
    assert body["kind"] == "semantic"
    assert body["source"] == "mcp:sacred-brain"
    assert body["scope"] == {"kind": "user", "id": "coding", "parent": None}
    assert out["memory_id"] == "m42"
    assert out["user_id"] == "coding"


def test_log_memory_explicit_scope_overrides_default(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "stored", "memory_id": "m7"})

    _patch_client(monkeypatch, handler)

    cfg = _cfg(default_user_id="sam", default_write_user_id="coding")
    asyncio.run(
        log_memory(
            cfg,
            text="t",
            scope="project:sacred-brain/user:coding",
            kind="episodic",
        )
    )
    scope = captured["body"]["scope"]
    assert scope["kind"] == "project"
    assert scope["parent"]["kind"] == "user"


def test_log_memory_prefers_write_default_over_read_default(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "stored", "memory_id": "x"})

    _patch_client(monkeypatch, handler)

    cfg = _cfg(default_user_id="sam", default_write_user_id="coding")
    asyncio.run(log_memory(cfg, text="t"))
    assert captured["body"]["user_id"] == "coding"


def test_log_memory_falls_back_to_read_default(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "stored", "memory_id": "x"})

    _patch_client(monkeypatch, handler)

    cfg = _cfg(default_user_id="sam")
    asyncio.run(log_memory(cfg, text="t"))
    assert captured["body"]["user_id"] == "sam"


def test_log_memory_requires_user_id_when_no_defaults():
    cfg = _cfg()
    with pytest.raises(ValueError, match="user_id required"):
        asyncio.run(log_memory(cfg, text="t"))


def test_list_scopes_forwards_prefix(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"scopes": ["user:sam"]})

    _patch_client(monkeypatch, handler)

    cfg = _cfg()
    out = asyncio.run(list_scopes(cfg, prefix="project:"))
    assert captured["path"] == "/scopes"
    assert captured["params"] == {"prefix": "project:"}
    assert out == {"scopes": ["user:sam"]}
