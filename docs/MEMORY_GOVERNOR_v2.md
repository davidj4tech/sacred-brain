# Memory Governor v2 — Proposal

Additive proposal on top of the v0.3.0 Governor (`memory_governor/`). Nothing here removes existing behaviour; each section can land independently.

## 0. What v1 already does (for reference)

- `/observe` — salience classify → working store (TTL `MG_WORKING_TTL_HOURS=24`), promote to candidate if salient
- `/remember` — explicit, canonicalized, confidence `0.95`
- `/recall` — Hippocampus search + local rerank `0.7 * confidence + 0.3 * recency`, recency linear over ~30d
- `/consolidate` — working → episodic/semantic/procedural; confidence tiers 0.5–0.7 from `mem_policy.consolidate_events`
- Timers: `memory-governor-consolidate.timer` hourly, `hippocampus-auto-prune.timer` daily 04:15, `governor-digest.timer` nightly 03:20
- Tiers: `safe` / `raw` (privacy). Scopes: `{kind: user|room|global, id}`

## 1. Retrieval extends life

Today `/recall` is read-only — a memory that's hit 50 times decays at the same rate as one never touched. Borrow hippo-memory's core move: **recall is a positive signal, write it back.**

### Change

- `store.py`: add `memories_recall_stats(memory_id, last_recalled_at, recall_count)` table (Governor-side, not Hippocampus — keeps Hippocampus pure semantic store).
- `/recall`: after ranking, enqueue a background `recall_hit` job for each returned `memory_id`.
- Worker: increments `recall_count`, sets `last_recalled_at=now`, optionally PATCHes Hippocampus metadata with bumped `salience` (salience += 0.05, clamped ≤ 1.0).
- Rerank formula in `app.py:_score`: add `+ 0.15 * recall_boost` where `recall_boost = min(1.0, recall_count / 10)`.
- Auto-prune timer honours `last_recalled_at` when deciding eviction (recalled-within-N-days → protected).

### Why

Stops the Governor quietly deleting memories the system is actively relying on. Cheap: one extra SQLite table, one worker job type.

## 2. Outcome feedback

Today the only confidence signals are heuristic (keyword match, phrase shape). Add a downstream signal: **did acting on this memory turn out well?**

### Change

- New endpoint `POST /outcome`:
  ```json
  {"memory_id": "…", "user_id": "sam", "outcome": "good" | "bad" | "stale",
   "note": "optional free text", "source": "claude-code"}
  ```
- Effects:
  - `good` → confidence += 0.05 (clamped ≤ 0.99), salience += 0.05
  - `bad` → confidence *= 0.7, tag `disputed=true` in metadata; if confidence < 0.2 after, enqueue deletion
  - `stale` → confidence unchanged, tag `stale=true`, exclude from `/recall` unless `filters.include_stale=true`
- Log every outcome to `stream_log` for the nightly digest ("memories that turned out wrong today").
- Add `confidence_history` array in metadata (bounded, last 10 deltas) so we can see why a memory's score drifted.

### Why

Closes the loop. Without this, a hallucinated/obsolete memory only gets corrected when a human manually deletes it.

## 3. Hierarchical scopes

Today `Scope = {kind: user|room|global, id}` is flat. For Claude Code / OpenCode, scopes need a project/topic dimension — "remember this for the sacred-brain repo, not globally for Sam."

### Change

- Extend `schemas.Scope`:
  ```python
  class Scope(BaseModel):
      kind: Literal["user", "room", "global", "project", "topic"]
      id: str
      parent: "Scope" | None = None   # optional chain
  ```
- Recall with scope `project:sacred-brain` walks parents: project → user → global (most-specific wins on ties).
- `MG_CONSOLIDATE_SCOPES` already parses comma-separated `kind:id`; extend parser to accept `project:sacred-brain@user:sam` syntax for explicit parents.
- Governor gains a `/scopes` list endpoint so clients (CLAUDE.md generator) can discover what scopes exist without guessing.

### Why

Claude Code already has project-scoped memory files (`.claude/...`). OpenCode uses `AGENTS.md` per repo. Without project scopes, every memory leaks across contexts.

## 4. Claude Code integration

Two surfaces: a **hook pair** for automatic ingest/recall, and an **MCP server** for in-session tool access.

### 4a. Hook pair (no extension install required)

Drop two scripts + a `settings.json` stanza per machine. Use the existing auto-memory dir (`~/.claude/projects/<project>/memory/MEMORY.md`) as the sync surface, not as the source of truth.

- **SessionStart hook** — pulls top-K memories for the project scope, writes them into a `CLAUDE.md` fragment the harness already loads.
  ```bash
  # ~/.claude/claude-governor-pull.sh
  PROJECT=$(basename "$PWD")
  curl -s -X POST "$GOVERNOR_URL/recall" \
    -H "X-API-Key: $GOVERNOR_API_KEY" \
    -d "{\"user_id\":\"sam\",\"query\":\"\",\"k\":20,
         \"filters\":{\"scope\":{\"kind\":\"project\",\"id\":\"$PROJECT\"},
                      \"min_confidence\":0.5}}" \
    | jq -r '.results[] | "- " + .text' \
    > .claude/CONTEXT_MEMORY.md
  ```
- **Stop hook** — posts the session outcome. If tests passed or user said "thanks/good", mark last-used memories `good`; if the user corrected, mark `bad`.
- **PreCompact hook** (existing in Claude Code) — before the transcript compacts, POST `/observe` with the uncompressed tail so salient bits survive.

### 4b. Auto-memory bridge

The Claude Code auto-memory format (frontmatter `type: user|feedback|project|reference`) maps cleanly onto Governor kinds:

| Claude Code type | Governor kind | Default confidence |
|---|---|---|
| `user`      | `semantic`   | 0.8 |
| `feedback`  | `procedural` | 0.85 |
| `project`   | `episodic`   | 0.7 |
| `reference` | `semantic`   | 0.75 |

Add a one-shot sync script (`scripts/sync_claude_memory.py`) that walks `~/.claude/projects/*/memory/*.md`, parses frontmatter, and `POST /remember`s each file with scope `project:<dirname>`. Idempotent by `memory_id = sha1(path+content)`.

### 4c. MCP server (later)

Expose `/remember`, `/recall`, `/outcome` as three MCP tools. One `mcp-governor.py` process, stdio transport, one line in `~/.claude/settings.json`. Only do this after 4a/4b are proven — MCP adds install friction and the hook-based path covers 90% of the value.

## 5. OpenCode integration

OpenCode uses `AGENTS.md` as its instruction surface (same convention as Codex). Same pattern as 4a, different target file:

- SessionStart equivalent → write top-K memories into a `AGENTS.local.md` fragment (or append a `## Memory` section to `AGENTS.md` that's marked `<!-- governor:managed -->` so the writer knows what block to replace).
- Use the same `/recall` call; only the output path and file marker differ.
- Reuse the same outcome hook — it's identical shell.

Practical consequence: factor 4a's hook into `scripts/governor_context.sh --target claude|opencode` so both frameworks share one implementation.

## 6. Ordering

Recommended landing order (each a standalone PR, backwards-compatible):

1. **§1 retrieval-extends-life** — smallest surface, highest value, no API change
2. **§3 hierarchical scopes** — API-additive (old flat scopes still parse); blocks §4/§5
3. **§4a hooks + §4b auto-memory bridge** — one script, two call sites
4. **§2 outcome feedback** — new endpoint; wire to §4 hooks
5. **§5 OpenCode target** — trivial once §4 works
6. **§4c MCP server** — optional, last

## 7. Out of scope for v2

- Embedding-based recall (Hippocampus/Mem0 handles this; don't reinvent)
- Knowledge graph / temporal validity windows (MemPalace-style) — tempting but large; revisit after §1–§5 are stable
- Multi-human ACLs / auth — current `user_id` names a bot persona (sam, mel), and all personas answer to david, the sole human operator today. Multi-human access is a flagged future requirement: don't build it now, but keep the scope model open-ended (the hierarchical scheme in §3 is already forward-compatible — a `human:<name>` tier can slot above `user:<persona>` without schema changes).

## 8. Housekeeping

- `/home/ryer/projects/sacred-brain/` is a stale Nov–Dec 2025 copy (pre-Governor). Nothing in v2 depends on it; consider archiving or deleting after this proposal lands so future agents don't grep the wrong tree (as happened drafting this doc).
