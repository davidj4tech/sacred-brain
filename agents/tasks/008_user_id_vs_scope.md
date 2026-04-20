# Task: Revisit user_id as a first-class dimension

## Context

When wiring the MCP `log_memory` tool (task 007), we hit the question of which `user_id` coding-agent writes should land under. The chat personas (`sam`, `mel`) are wrong — coding writes aren't *about* those personas. The ChatGPT-import bucket (`david`) is also wrong — it conflates the human with a specific archive. We settled on `user_id="coding"` as a new, purpose-built bucket, passed via `SACRED_MCP_DEFAULT_WRITE_USER_ID` in the stdio launcher.

That's a fine local answer, but it surfaces a deeper issue: **in a multi-persona, multi-context Sacred Brain, `user_id` is mostly vestigial**. The load-bearing dimension for both ranking and filtering is `scope` — `project:…/user:…/global:root` paths already carry persona *and* context *and* project. `user_id` is kept around because Hippocampus / Mem0 indexes by it at the storage layer, but semantically it's doing less work every iteration.

The sharpest form of the mismatch: **coding agents aren't personas**. Claude Code, Codex, OpenCode have no self, no voice, no identity that would "own" a memory. They're david's hands. Chat personas (`sam`, `mel`) genuinely have character and a coherent "what would Sam remember"; coding tools don't. Invoking a new `coding` bucket just papers over the fact that these writes are really *david's* memories about *david's* work, and the natural `user_id="david"` is already occupied by the ChatGPT archive.

Symptoms of the debt:
- Coding writes need their own bucket (`coding`) just to avoid poisoning chat-persona recall.
- The ChatGPT archive bucket (`david`) is suppressed by an `MG_INCLUDE_ARCHIVE` filter — per-bucket hacks compensating for what should be a scope-filter concern.
- Per-machine env plumbing (`GOVERNOR_USER_ID`, `HIPPOCAMPUS_USER_ID`) binds a persona that's increasingly just "which user_id to write under" rather than meaningful persona state.
- Multi-human readiness (flagged in auto-memory) wants `human:<name>` above `user:<persona>` — but today `user_id` *is* the persona, so there's no natural layer above it.

## Not blocked; not yet actionable

This task is a **flagged design-debt ticket**, not a current implementation. It exists so the observation isn't lost. Opening it for real waits on concrete pressure:

- Wanting to promote a memory from `user:coding` to `user:sam` and discovering there's no clean primitive.
- A multi-human access story becoming a real requirement rather than a hypothetical.
- A third purpose-built bucket appearing (`docs`? `ops`?) and the "bucket per purpose" pattern starting to feel absurd.

Until one of those bites, the `user_id="coding"` workaround is fine.

## When it's time, design questions to answer

1. Does `user_id` become purely a storage-layer key (opaque), with scope doing all semantic work?
2. How do reads union across buckets so "search all of david's knowledge" works regardless of which bucket a memory was written to?
3. Does the Mem0 backend even support a null / shared `user_id`, or is per-user-id indexing load-bearing for its embedding store?
4. Does a migration pass re-bucket existing memories under new conventions, or do we carry historical buckets forever?
5. What happens to `MG_INCLUDE_ARCHIVE` when bucket-as-archive-flag is no longer the primary mechanism?

## References

- `agents/tasks/007_mcp_server.md` — where this came up (§log_memory design)
- `docs/MEMORY_GOVERNOR_v2.md` §3 — scope hierarchy (the dimension that would absorb user_id's remaining semantics)
- `docs/user-config/personas.md` — current persona convention
- `~/.claude/projects/-home-ryer/memory/MEMORY.md` — multi-human future note
- `services/sacred_mcp/handlers.py:log_memory` — the local workaround (`default_write_user_id`)
