"""Sacred Brain MCP server — stdio transport.

Runs as a sub-process under an MCP-speaking agent (Claude Desktop, Claude Code,
Cursor, etc.). Binds a persona via env so tool calls can omit `user_id`.

Env:
  SACRED_MCP_HIPPOCAMPUS_URL   — default http://127.0.0.1:54321
  SACRED_MCP_GOVERNOR_URL      — default http://127.0.0.1:54323
  SACRED_MCP_API_KEY           — shared with X-API-Key auth
  SACRED_MCP_DEFAULT_USER_ID   — persona bound to this instance (e.g. "sam")

For HIPPOCAMPUS_URL / HIPPOCAMPUS_API_KEY compatibility with the existing
`~/.config/hippocampus.env`, those names are honoured as fallbacks.
"""
from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from services.sacred_mcp.handlers import (
    SacredBrainConfig,
    list_scopes as _list_scopes,
    log_memory as _log_memory,
    recall_scope as _recall_scope,
    search_memory as _search_memory,
)


def _load_config() -> SacredBrainConfig:
    hippocampus_url = (
        os.environ.get("SACRED_MCP_HIPPOCAMPUS_URL")
        or os.environ.get("HIPPOCAMPUS_URL")
        or "http://127.0.0.1:54321"
    )
    governor_url = (
        os.environ.get("SACRED_MCP_GOVERNOR_URL")
        or os.environ.get("GOVERNOR_URL")
        or "http://127.0.0.1:54323"
    )
    api_key = (
        os.environ.get("SACRED_MCP_API_KEY")
        or os.environ.get("HIPPOCAMPUS_API_KEY")
    )
    default_user_id = (
        os.environ.get("SACRED_MCP_DEFAULT_USER_ID")
        or os.environ.get("HIPPOCAMPUS_USER_ID")
        or os.environ.get("GOVERNOR_USER_ID")
    )
    default_write_user_id = os.environ.get("SACRED_MCP_DEFAULT_WRITE_USER_ID")
    return SacredBrainConfig(
        hippocampus_url=hippocampus_url,
        governor_url=governor_url,
        api_key=api_key,
        default_user_id=default_user_id,
        default_write_user_id=default_write_user_id,
    )


mcp = FastMCP("sacred-brain")
_cfg = _load_config()


@mcp.tool()
async def search_memory(
    query: str, user_id: str | None = None, limit: int = 5
) -> dict[str, Any]:
    """Search Sacred Brain long-term memory for the given query string.

    Use this when a question likely references prior discussions, past
    decisions, or imported ChatGPT conversation history. Returns memory
    records ordered by relevance.

    Args:
        query: free-text search string.
        user_id: persona whose memories to search. Defaults to this server's
            bound persona if set, otherwise required. Common values:
            "sam" (bot persona), "david" (ChatGPT-imported), "mel".
        limit: max number of memories to return. Default 5.
    """
    return await _search_memory(_cfg, query=query, user_id=user_id, limit=limit)


@mcp.tool()
async def recall_scope(
    scope: str, query: str = "", user_id: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Recall memories for a specific scope with hierarchical ancestor matching.

    Scopes are slash-joined segments, leftmost = most specific. Example:
    "project:sacred-brain/user:sam" returns sacred-brain-project memories
    filtered to the sam persona, falling back up the hierarchy.

    Args:
        scope: scope path like "project:foo/user:sam" or "user:sam".
        query: optional free-text filter; pass "" for a general pull.
        user_id: persona. Defaults to bound persona.
        limit: max results. Default 10.
    """
    return await _recall_scope(
        _cfg, scope=scope, query=query, user_id=user_id, limit=limit
    )


@mcp.tool()
async def log_memory(
    text: str,
    user_id: str | None = None,
    kind: str = "semantic",
    scope: str | None = None,
    source: str = "mcp:sacred-brain",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a memory to Sacred Brain for future recall.

    Use when something is worth keeping across sessions: a user preference, a
    decision and its reasoning, a non-obvious fact about the codebase, a lesson
    from a bug. Prefer granular saves at moments of insight over bulk dumps.

    Args:
        text: the memory content. Write it so a future session can understand
            it cold — include the *why*, not just the *what*.
        user_id: bucket owner. Defaults to the server's bound write-persona
            (typically "coding_agent" for dev-tool writes). Leave unset unless you
            have a specific reason to target another persona.
        kind: "semantic" (facts), "episodic" (events), or "procedural" (rules).
            Defaults to "semantic".
        scope: slash-joined scope path like "project:sacred-brain/user:coding".
            Defaults to "user:<user_id>" if omitted.
        source: provenance tag; default "mcp:sacred-brain".
        metadata: extra fields merged onto the memory record.
    """
    return await _log_memory(
        _cfg,
        text=text,
        user_id=user_id,
        kind=kind,
        scope=scope,
        source=source,
        metadata=metadata,
    )


@mcp.resource("memory://scopes")
async def scopes_resource() -> dict[str, Any]:
    """List all known memory scopes."""
    return await _list_scopes(_cfg)


def run() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
