# Sacred Brain MCP server

Exposes Sacred Brain as a Model Context Protocol server so any MCP-speaking agent — Claude Code, Claude Desktop, Cursor, Zed, Codex, OpenCode, most of the [ACP agent list](https://agentclientprotocol.com/get-started/agents) — discovers memory tools automatically, without per-agent instruction files or CLI pre-install.

**Relationship to `sacred-search`:** complementary, not a replacement. MCP is for MCP-speaking agents; the CLI stays for humans and non-MCP contexts (shell scripts, bots, `hippocampus_query.sh`). Both hit the same Hippocampus + Governor REST backends.

**Relationship to ACP:** orthogonal. ACP is editor⇄agent plumbing. MCP is agent⇄tool plumbing. An ACP agent that also speaks MCP (most do) uses this server as one of its tools.

## Tool surface

### Read

- **`search_memory(query, user_id?, limit?)`** — free-text search over Hippocampus. The workhorse. Defaults `user_id` to this server instance's bound read-persona if set (typically `sam`).
- **`recall_scope(scope, query?, user_id?, limit?)`** — hierarchical scope-aware recall via the Governor. `scope` is slash-joined, leftmost = most specific (e.g. `project:sacred-brain/user:sam`).

### Write

- **`log_memory(text, user_id?, kind?, scope?, source?, metadata?)`** — deliberate save via Governor `/remember`. Defaults `user_id` to the server's bound **write-persona** (typically `coding_agent`), which is deliberately separate from the read-persona so coding-agent writes don't pollute chat-persona scopes. `scope` defaults to `user:<user_id>`. Tagged `source="mcp:sacred-brain"` by default.

`record_observation` (event-stream writes) and `mark_outcome` (feedback for ranking) remain deferred to a later iteration; they're different shapes and deserve their own design pass.

## Resources

- **`memory://scopes`** — list of known scopes.

## Transports

- **stdio** — sub-process per agent. Binds a persona via env. Works with Claude Desktop, Claude Code, Cursor, and any MCP client that spawns stdio servers.
- **HTTP/SSE** — deferred. `sacred-search` already covers cross-machine use over Tailscale; HTTP MCP will land once a specific client wants it.

## Install (stdio, homer)

The launcher `scripts/sacred-mcp-stdio` sources `~/.config/hippocampus.env`, activates the repo checkout, and execs the server. Symlink it into `~/.local/bin/`:

```
ln -sf /opt/sacred-brain/scripts/sacred-mcp-stdio ~/.local/bin/sacred-mcp-stdio
```

Requires `mcp>=1.27.0` importable from the system Python (already in `pyproject.toml`).

## Per-client wiring

### Claude Code

```
claude mcp add -s user sacred-brain ~/.local/bin/sacred-mcp-stdio \
  -e SACRED_MCP_DEFAULT_USER_ID=sam
```

Verify with `claude mcp list` — should show `sacred-brain: ✓ Connected`. Restart any open Claude Code session to pick up the new server.

### Claude Desktop

`~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "sacred-brain": {
      "command": "/home/ryer/.local/bin/sacred-mcp-stdio",
      "env": { "SACRED_MCP_DEFAULT_USER_ID": "sam" }
    }
  }
}
```

### Cursor / Zed / others

Any MCP client that takes a command path and env map works the same way — point it at the launcher and set `SACRED_MCP_DEFAULT_USER_ID` to the persona for that host.

## Env reference

The launcher sources `~/.config/hippocampus.env` first, so the names below all fall back to the values already provisioned there.

| Env var | Fallback | Meaning |
|---|---|---|
| `SACRED_MCP_HIPPOCAMPUS_URL` | `HIPPOCAMPUS_URL` | Hippocampus base URL |
| `SACRED_MCP_GOVERNOR_URL` | `GOVERNOR_URL` | Governor base URL |
| `SACRED_MCP_API_KEY` | `HIPPOCAMPUS_API_KEY` | `X-API-Key` for both backends |
| `SACRED_MCP_DEFAULT_USER_ID` | `HIPPOCAMPUS_USER_ID` / `GOVERNOR_USER_ID` | **Read** persona bound to this server instance |
| `SACRED_MCP_DEFAULT_WRITE_USER_ID` | — | **Write** persona for `log_memory`. Launcher defaults to `coding_agent`. |

Per-machine defaults for the backing URLs live in [`user-config/machines.md`](user-config/machines.md).

## Smoke test

```
python3 -m services.sacred_mcp.stdio < /dev/null  # exits immediately — expected
```

For an interactive check, spawn the server with the official MCP Inspector (`npx @modelcontextprotocol/inspector ~/.local/bin/sacred-mcp-stdio`) and call `search_memory({"query": "chatgpt", "user_id": "david", "limit": 2})`. The result should match `sacred-search "chatgpt" david 2`.

## Related

- `docs/SACRED_SEARCH.md` — the CLI this complements
- `docs/API.md` — the underlying Hippocampus REST
- `docs/MEMORY_GOVERNOR_v2.md` §3 — scope hierarchy (`recall_scope` semantics)
- `agents/tasks/007_mcp_server.md` — the plan
