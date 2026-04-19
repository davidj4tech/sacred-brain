# Task: Recall extends life

## Context
Today the Governor's `/recall` endpoint is read-only. A memory recalled 50 times decays at exactly the same rate as one never touched. The auto-prune timer can delete memories the system is actively relying on.

Implements `docs/MEMORY_GOVERNOR_v2.md` §1.

## Goal
A memory that is successfully recalled gains durability: its salience is boosted, its last-recalled timestamp is recorded, and the auto-prune timer treats recently-recalled memories as protected. Recall ranking rewards repeatedly-used memories.

## Requirements

- Governor-side only. Hippocampus stays a pure store — no schema change there.
- Backwards-compatible: existing `/recall` response shape is unchanged; no new required request fields.
- New SQLite table in the Governor's working DB (`store.py`):
  ```sql
  CREATE TABLE IF NOT EXISTS recall_stats (
      memory_id    TEXT PRIMARY KEY,
      last_recalled_at INTEGER NOT NULL,
      recall_count INTEGER NOT NULL DEFAULT 0
  );
  ```
- New internal job type `recall_hit` handled by the existing worker loop in `app.py:GovernorRuntime._process_job`. One job per returned `memory_id`.
- On `recall_hit`:
  - `UPSERT` into `recall_stats`: increment `recall_count`, set `last_recalled_at = now()`.
  - Optionally `PATCH` Hippocampus metadata with `salience = min(1.0, current + 0.05)`. If Hippocampus lacks a patch endpoint, defer this half and note it — the SQLite stats alone are enough for ranking and prune.
- Update rerank in `app.py:_score`:
  ```
  score = confidence*0.65 + recency*0.25 + recall_boost*0.10
  where recall_boost = min(1.0, recall_count / 10)
  ```
  (confidence weight drops from 0.7 → 0.65, recency 0.3 → 0.25, new term 0.10)
- Update `hippocampus-auto-prune.timer`'s prune query: exclude rows where `last_recalled_at` is within the last `MG_RECALL_PROTECT_DAYS` days (default 30, configurable via env).
- Expose a read-only debug endpoint `GET /recall_stats/{memory_id}` returning `{recall_count, last_recalled_at}` — useful for digest output and debugging.

Must NOT change:
- The `/recall` request/response wire format.
- Hippocampus's API or schema.
- The existing tier / scope / consolidation code paths.

## Suggested Steps

1. Add the `recall_stats` table + helpers to `memory_governor/store.py` (`bump_recall`, `get_recall_stats`, `recently_recalled_ids(since_ts)`).
2. Enqueue `recall_hit` jobs from `app.py:recall` after ranking (use existing `runtime.enqueue_memory` plumbing or add a parallel `enqueue_stat`).
3. Extend `_process_job` to dispatch the new job type.
4. Rework `_score` to read `recall_count` for each candidate (batch-fetch by id into a dict; avoid per-row queries).
5. Wire `MG_RECALL_PROTECT_DAYS` into `config.py` and the prune timer's query/service file under `ops/systemd/`.
6. Add `GET /recall_stats/{memory_id}`.
7. Tests: new unit test in `tests/` covering bump-on-recall, ranking lift for repeatedly-recalled rows, and prune protection.
8. Update `docs/MEMORY_GOVERNOR.md` with the new env var and endpoint.

## Validation

- `just smoke` passes.
- `pytest` passes including a new test `test_recall_extends_life.py` that:
  - POSTs `/remember`, then calls `/recall` five times for that text, then asserts `recall_count == 5` via `GET /recall_stats/{id}`.
  - Asserts that between two candidates with identical confidence/recency, the one with higher `recall_count` ranks first.
- Manual: after one recall, `sqlite3 <db_path> "SELECT * FROM recall_stats"` shows the bumped row.
- Manual: set `MG_RECALL_PROTECT_DAYS=1`, insert an old low-salience memory, recall it, run prune — memory must survive.

## References

- `docs/MEMORY_GOVERNOR_v2.md` §1 (design)
- `memory_governor/app.py` (`recall`, `_score`, `GovernorRuntime._process_job`)
- `memory_governor/store.py` (add table + helpers here)
- `memory_governor/config.py` (new env var)
- `ops/systemd/hippocampus-auto-prune.*` (prune query update)
