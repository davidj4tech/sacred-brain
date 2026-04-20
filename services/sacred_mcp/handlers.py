"""Transport-agnostic handlers for the Sacred Brain MCP server.

These functions wrap Hippocampus and Governor REST calls. They return plain
dicts/lists — MCP transport code is responsible for shaping the response.

Design:
- v1 is read-only. search_memory + recall_scope + two resource fetchers.
- Writes (log_memory, record_observation, mark_outcome) are deferred to v2
  once we see how agents use the read path.
- No ranking/formatting logic lives here — Hippocampus and the Governor
  already handle that. This is glue.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class SacredBrainConfig:
    """Connection settings for the REST backends.

    `default_user_id` is the read-side fallback (e.g. "sam"). `default_write_user_id`
    is the write-side fallback, deliberately separate because coding-agent writes
    belong in a different bucket than chat-persona reads. Both only apply when the
    transport has bound a persona (stdio mode); HTTP/SSE transports should leave
    them None and require `user_id` on every call.
    """

    hippocampus_url: str
    governor_url: str
    api_key: str | None = None
    default_user_id: str | None = None
    default_write_user_id: str | None = None
    timeout: float = 10.0


def _headers(cfg: SacredBrainConfig) -> dict[str, str]:
    return {"X-API-Key": cfg.api_key} if cfg.api_key else {}


def _parse_scope_path(path: str) -> dict[str, Any]:
    """Parse 'project:foo/user:sam' into the nested Scope dict the Governor wants.

    Leftmost segment is the most-specific; subsequent segments become `parent`.
    """
    parts = [p for p in path.split("/") if p]
    if not parts:
        raise ValueError("scope path must be non-empty")
    nodes: list[dict[str, Any]] = []
    for part in parts:
        if ":" not in part:
            raise ValueError(f"scope segment missing ':': {part!r}")
        kind, _, ident = part.partition(":")
        nodes.append({"kind": kind, "id": ident})
    # Chain parents: leaf → ... → root
    result: dict[str, Any] | None = None
    for node in reversed(nodes):
        node["parent"] = result
        result = node
    assert result is not None
    return result


async def search_memory(
    cfg: SacredBrainConfig,
    query: str,
    user_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search memories for a user via Hippocampus GET /memories/{user_id}."""
    uid = user_id or cfg.default_user_id
    if not uid:
        raise ValueError("user_id required (no default bound to this server)")
    url = f"{cfg.hippocampus_url.rstrip('/')}/memories/{uid}"
    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.get(
            url,
            params={"query": query, "limit": limit},
            headers=_headers(cfg),
        )
        resp.raise_for_status()
        data = resp.json()
    return {"user_id": uid, "query": query, "memories": data.get("memories", [])}


async def recall_scope(
    cfg: SacredBrainConfig,
    scope: str,
    query: str = "",
    user_id: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Scope-aware recall via Governor POST /recall with hierarchical filter."""
    uid = user_id or cfg.default_user_id
    if not uid:
        raise ValueError("user_id required (no default bound to this server)")
    scope_obj = _parse_scope_path(scope)
    payload = {
        "user_id": uid,
        "query": query,
        "k": limit,
        "filters": {"scope": scope_obj},
    }
    url = f"{cfg.governor_url.rstrip('/')}/recall"
    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.post(url, json=payload, headers=_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    return {"scope": scope, "user_id": uid, "results": data.get("results", [])}


async def log_memory(
    cfg: SacredBrainConfig,
    text: str,
    user_id: str | None = None,
    kind: str = "semantic",
    scope: str | None = None,
    source: str = "mcp:sacred-brain",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deliberate write via Governor POST /remember.

    Scope defaults to 'user:<user_id>' when omitted. The Governor canonicalizes
    text, assigns salience=1.0 + confidence=0.95, and enqueues the Hippocampus
    write through its durable queue.
    """
    uid = user_id or cfg.default_write_user_id or cfg.default_user_id
    if not uid:
        raise ValueError("user_id required (no write-default bound to this server)")
    scope_obj = _parse_scope_path(scope) if scope else {"kind": "user", "id": uid, "parent": None}
    payload: dict[str, Any] = {
        "source": source,
        "user_id": uid,
        "text": text,
        "kind": kind,
        "scope": scope_obj,
        "metadata": metadata or {},
    }
    url = f"{cfg.governor_url.rstrip('/')}/remember"
    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.post(url, json=payload, headers=_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    return {
        "status": data.get("status", "stored"),
        "memory_id": data.get("memory_id"),
        "user_id": uid,
        "scope": scope or f"user:{uid}",
        "kind": kind,
    }


async def list_scopes(cfg: SacredBrainConfig, prefix: str | None = None) -> dict[str, Any]:
    """Governor GET /scopes — for the memory://scopes resource."""
    url = f"{cfg.governor_url.rstrip('/')}/scopes"
    params = {"prefix": prefix} if prefix else None
    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.get(url, params=params, headers=_headers(cfg))
        resp.raise_for_status()
        return resp.json()
