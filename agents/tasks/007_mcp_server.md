# Task: Sacred Brain MCP server

## Context

Today agents reach Sacred Brain through three different paths:
- `sacred-search` CLI (documented at user-scope in `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md`).
- `governor_context.sh` pre-session pull into `CONTEXT_MEMORY.md` (via bridges).
- Direct REST against Hippocampus / Governor (bots, OpenClaw's `hippocampus_query.sh` shim).

All three work but share the same failure mode: the agent has to *know* the tool exists. User-level instruction files try to fix this, but they're per-agent-convention and not all agents load them reliably.

The Model Context Protocol solves this at the plumbing layer: MCP servers advertise their tools to the agent at connection time, with typed schemas and structured returns. Any MCP-speaking agent — Claude Desktop, Claude Code, Codex, Cursor, Zed, OpenCode, most of the ACP agent list — discovers them automatically. This is the right layer for "agent consults memory on demand", orthogonal to ACP (which is editor⇄agent plumbing, not agent⇄tool).

See the ecosystem survey in `docs/README.md` (Third-party integrations) and the ACP vs. MCP separation discussion — ACP doesn't replace this; it sits above it.

## Blocked by

Nothing. Hippocampus and Governor REST APIs are stable; this is a thin adapter layer.

## Goal

Expose Sacred Brain as an MCP server so any MCP-speaking agent discovers memory tools automatically without per-agent instruction files or CLI pre-install. Read-first in v1; writes gated to v2 after we see usage patterns.

Transport: both stdio (for local sub-process agents like Claude Desktop) and HTTP/SSE (for networked agents over Tailscale). Same inner handlers.

## Requirements

### Tool surface (v1, read-only)

- `search_memory(query: str, user_id?: str, limit?: int = 5)` — wraps Hippocampus `GET /memories/{user_id}?query=…`. Default `user_id` from server config. The workhorse — covers what `sacred-search` does today.
- `recall_scope(scope: str, limit?: int = 10)` — wraps Governor `POST /recall`. Hierarchical ancestor-matching. On-demand equivalent of `governor_context.sh`.

### Resources (v1)

- `memory://scopes` — list known scopes (Governor `GET /scopes`).
- `memory://scope/{scope_path}` — top-K for a scope, same payload as CONTEXT_MEMORY.md but as a fetched resource.

### Tool surface (v2, write path — not in this task)

Documented so the v1 schema doesn't box us in:
- `log_memory(text, user_id, metadata?)` → `POST /memories`.
- `record_observation(text, source, salience?)` → Governor `/observe`.
- `mark_outcome(memory_id, outcome)` → Governor `/outcome`.

Don't implement in v1. Note in the README that these are intentionally absent pending v2.

### Transports

- **stdio wrapper** — `services/sacred_mcp/stdio.py`, uses the official `mcp` Python SDK. One process per agent. User binds `user_id` + REST URLs + API key via env (reuses `~/.config/hippocampus.env`).
- **HTTP/SSE mount** — `services/sacred_mcp/http.py`, mounted as a FastAPI sub-app. Runs at `:54324/mcp` (new port, kept separate from Hippocampus `:54321` and Governor `:54323` so auth and logging stay clean). Uses `X-API-Key` same as the other services.

Both share a single `handlers.py` with the tool-call implementations. The transport files are thin shells.

### user_id binding

- **stdio**: bind `user_id` at launch via `SACRED_MCP_DEFAULT_USER_ID` env. `user_id` arg on each tool call becomes optional (defaults to the bound persona).
- **HTTP/SSE**: `user_id` is required on every call. No implicit binding — the server is shared across callers.

Document both modes in the README.

### Config / install

- `services/sacred_mcp/` — new package, mirrors the layout of existing FastAPI services.
- `services/sacred_mcp/pyproject.toml` or extend the root one — add `mcp` SDK dep.
- `ops/sacred_mcp/install.sh` — optional symlink into `~/.local/bin/sacred-mcp-stdio` for agents that want a stdio sub-process.
- `ops/sacred_mcp/sacred-mcp.service` — systemd unit for the HTTP/SSE variant on homer. Installed as part of the standard stack, not via this task's installer.
- Per-agent config snippets in `docs/SACRED_MCP.md` showing how to wire it into Claude Desktop, Cursor, Zed, Claude Code (if/when CC gets MCP support).

### Docs

- `docs/SACRED_MCP.md` — new doc. Sections: what it is, why not just ACP, tool surface, resources, stdio vs. HTTP/SSE, per-client config examples, relationship to `sacred-search` (complementary: MCP for MCP-speaking agents, CLI for humans + non-MCP contexts).
- `docs/README.md` — add `SACRED_MCP.md` under "REST API reference" (or a new "MCP" heading if we expect more MCP docs).
- `docs/APP_ONBOARDING.md` — §3 gets a new subsection 3.5 "MCP client integration" with the config snippet for agents that prefer MCP over sacred-search.
- User-level instruction files (`~/.claude/CLAUDE.md` etc.) get a short note: "If this agent supports MCP, prefer the sacred-brain MCP server over sacred-search CLI." Don't remove the sacred-search doc — CLI stays as fallback.

Must NOT:
- Re-implement search ranking — this is a thin adapter over existing REST endpoints.
- Implement writes in v1 (`log_memory`, `record_observation`, `mark_outcome`). Read-only until we see how agents actually use the read path.
- Add auth beyond the existing `X-API-Key` header. Per-client MCP tokens are a v2+ concern tied to per-app API keys (already flagged in `APP_ONBOARDING.md` Future section).
- Duplicate `sacred-search`'s formatting logic. MCP returns structured JSON; formatting is the agent's concern.

## Suggested Steps

1. Scaffold `services/sacred_mcp/` with `handlers.py`, `stdio.py`, `http.py`, and a minimal `pyproject.toml` (or extend root deps).
2. Implement `handlers.search_memory` + `handlers.recall_scope` against the existing REST clients. Reuse whatever httpx/requests helpers already exist in the Governor service.
3. Implement `stdio.py` — MCP SDK boilerplate + call into handlers.
4. Implement `http.py` — FastAPI sub-app + MCP SDK HTTP/SSE wiring.
5. Add systemd unit for the HTTP variant; wire into INSTALL.md's service list.
6. Smoke-test stdio mode against Claude Desktop or any MCP Inspector: list tools, call `search_memory`, confirm structured return.
7. Smoke-test HTTP mode: `curl` the MCP endpoint, confirm the handshake, call `search_memory` via MCP Inspector pointed at the HTTP URL.
8. Write `docs/SACRED_MCP.md`; update `docs/README.md` and `docs/APP_ONBOARDING.md`.
9. Commit as one reviewable PR. Do not deploy to other machines in this PR — homer-only for v1.

## Validation

- `mcp-inspector` (or equivalent) connects to both stdio and HTTP transports and lists both tools + both resources.
- `search_memory("chatgpt", "david", 3)` over MCP returns the same memory IDs as `sacred-search "chatgpt" david 3`.
- `recall_scope("project:sacred-brain/user:sam", 5)` returns the same payload a fresh `governor_context.sh --target agents` would have written.
- stdio variant respects `SACRED_MCP_DEFAULT_USER_ID`; calling `search_memory` without `user_id` returns that persona's memories.
- HTTP variant 400s on calls missing `user_id`.
- `systemctl status sacred-mcp` is green after install.
- Existing tests still pass (`pytest`). New tests: handler-level unit tests for `search_memory` and `recall_scope` with mocked REST clients.

## References

- `docs/API.md` — Hippocampus REST (`search_memory` wraps `GET /memories/{user_id}`)
- `docs/MEMORY_GOVERNOR_v2.md` §3 — scope hierarchy (`recall_scope` semantics)
- `docs/SACRED_SEARCH.md` — the CLI this complements
- `docs/APP_ONBOARDING.md` — where the new MCP subsection lands
- https://modelcontextprotocol.io — spec and Python SDK
- https://agentclientprotocol.com — orthogonal layer; not a replacement
