# Task: Hierarchical scopes

## Context
`Scope` is flat today: `{kind: user|room|global, id}`. This is fine for Matrix rooms and single-user operation, but it cannot express "remember this for the sacred-brain *repo*, scoped under user sam" — which every coding-agent integration needs. Without it, Claude Code / OpenCode memory leaks across projects.

Blocks the planned Claude Code and OpenCode bridges (tasks 003 and 004).

Implements `docs/MEMORY_GOVERNOR_v2.md` §3.

## Goal
Scopes gain a `project` and `topic` kind and an optional `parent` chain. Recall with a narrow scope matches memories stored at that scope *or any ancestor*, with most-specific winning ties. A new `GET /scopes` endpoint lets clients discover what scopes exist.

## Requirements

- Backwards-compatible on the wire: `Scope(kind="user", id="sam")` without `parent` continues to parse and behave exactly as today. No existing caller breaks.
- Extend `memory_governor/schemas.py:Scope`:
  ```python
  class Scope(BaseModel):
      kind: Literal["user", "room", "global", "project", "topic"]
      id: str
      parent: "Scope" | None = None
  Scope.model_rebuild()  # pydantic v2 recursive model
  ```
- Introduce a canonical string form: **scope path**, newest-first separated by `/`.
  - `project:sacred-brain/user:sam/global:root` represents project `sacred-brain` owned by user `sam` under global root.
  - Use this as the `scope_key` replacement throughout `store.py`.
  - Helper `scope_path(scope: Scope) -> str` and `parse_scope_path(s: str) -> Scope` in `schemas.py` or a new `memory_governor/scopes.py`.
- Migrate `working_events` table (`memory_governor/store.py`):
  - Add column `scope_path TEXT` (idempotent `ALTER TABLE ... ADD COLUMN`, like the existing `normalized_text` pattern).
  - Backfill on startup: rows with NULL `scope_path` get `kind:id` copied from `scope_kind`/`scope_id`.
  - Add `CREATE INDEX idx_working_scope_path ON working_events(scope_path)`.
  - `recent_for_scope(scope, include_ancestors=True)` — match on `scope_path = ?` OR any ancestor path (LIKE prefix, longest-match first).
- Recall filter: extend `RecallFilters.scope` handling in `app.py:recall`.
  - If `filters.scope` is set, retain memories whose stored `scope.path` equals the filter path *or* is a prefix ancestor of it.
  - Rank lift: memories matching the exact scope get `+0.05` in `_score` (most-specific wins on ties).
- `MG_CONSOLIDATE_SCOPES` parser in `config.py`: continue to accept `user:alice,room:!abc:server`; additionally accept `@`-chained form like `project:sacred-brain@user:sam`. Unknown kinds raise at startup, not at first use.
- New endpoint `GET /scopes?prefix=<scope_path>`:
  - Enumerates distinct `scope_path` values from `working_events` and (best-effort) from recent memories via Hippocampus metadata.
  - Returns `[{"path": "...", "kind": "...", "id": "...", "count": N, "last_seen": ts}]` sorted by `last_seen` desc, capped at 200.
  - If `prefix` given, only returns paths under it.
- Hippocampus remains untouched. Scope chain is stored in each memory's `metadata.scope` dict (already happens via `payload.scope.dict()`); just ensure the new `parent` field round-trips through JSON without truncation.

Must NOT change:
- Any existing API request shape (new fields are additive and optional).
- Hippocampus schema or API.
- The `safe`/`raw` tier logic.
- Task 001's `recall_stats` work (this task merges alongside or after it; no conflicting columns).

## Suggested Steps

1. Extend `Scope` and add `scope_path` / `parse_scope_path` helpers. Unit test the round-trip: `parse_scope_path(scope_path(s)) == s`.
2. Migrate `store.py`: add column + index + backfill. Change `_scope_key` → `scope_path` everywhere it's used.
3. Teach `recent_for_scope` about ancestor matching. Parametrize the existing callers (consolidation only needs exact match; keep a flag).
4. Update `app.py:recall` filter logic and the `_score` exact-match bonus.
5. Extend `MG_CONSOLIDATE_SCOPES` parser in `config.py`. Add tests for both old and new syntax.
6. Implement `GET /scopes`. Keep it backed by a simple `SELECT scope_path, COUNT(*), MAX(ts) ... GROUP BY scope_path`.
7. Update `docs/MEMORY_GOVERNOR.md` with the new scope kinds, path syntax, and endpoint.

## Validation

- `pytest` green, including new tests in `tests/`:
  - `test_scope_path_roundtrip` — parse/serialize reflexivity for 1-, 2-, and 3-deep chains.
  - `test_scope_backcompat` — a flat `{kind:"user", id:"sam"}` request still matches memories stored the same way.
  - `test_scope_ancestor_recall` — memory stored at `global:root` recallable from `project:foo/user:sam/global:root` filter; memory stored at `project:foo/user:sam/global:root` *not* recallable from bare `global:root` filter (descendants don't match ancestors).
  - `test_scope_exact_match_bonus` — two memories identical except scope; narrow-scope filter ranks the exact match above the ancestor match.
  - `test_scopes_endpoint` — seed three scopes, assert `GET /scopes` returns them with correct counts.
- `just smoke` passes.
- Manual: `curl -s 'http://127.0.0.1:54323/scopes' | jq` returns a populated list on a running instance.
- Manual: old-format `POST /remember` with `{"scope":{"kind":"user","id":"sam"}}` succeeds and the stored `scope_path` is `user:sam`.

## References

- `docs/MEMORY_GOVERNOR_v2.md` §3 (design) and §6 (ordering — this is step 2 after task 001)
- `memory_governor/schemas.py` (Scope model)
- `memory_governor/store.py` (table migration, `recent_for_scope`, `_scope_key`)
- `memory_governor/app.py` (`recall` filter, `_score`, new `/scopes` endpoint)
- `memory_governor/config.py` (`MG_CONSOLIDATE_SCOPES` parser)
- `agents/tasks/001_recall_extends_life.md` (adjacent migration; coordinate column additions)
