# Task: Outcome feedback (core done; Stop-hook deferred with task 003)

## Context
The Governor's confidence scores come from heuristics applied at write time (keyword match, phrase shape, explicit `/remember`). There is no downstream signal telling the system whether acting on a memory *actually worked*. A hallucinated or obsolete memory stays at its initial confidence until a human deletes it.

This task closes the loop: introduce an `/outcome` endpoint and the per-memory overlay that feeds it into ranking, pruning, and the nightly digest. Also lands the Stop-hook half of the Claude Code bridge that was deferred from task 003.

Implements `docs/MEMORY_GOVERNOR_v2.md` §2. Completes §4a.

## Blocked by
- `agents/tasks/001_recall_extends_life.md` — establishes the Governor-side overlay-table pattern (`recall_stats`) that this task reuses. Landing 001 first avoids schema churn.
- `agents/tasks/003_claude_code_bridge.md` — the Stop hook installer plumbing lives alongside the SessionStart/PreCompact ones.

## Goal
A client can mark a specific memory `good`, `bad`, or `stale` via `POST /outcome`. Effects are visible in the very next `/recall`: good memories rank higher, bad ones are soft-deleted if they fall below a threshold, stale ones disappear from normal recall but remain in the store. A short audit trail is kept per memory. The nightly digest surfaces the day's outcomes.

## Requirements

### API

- New endpoint `POST /outcome`:
  ```json
  {
    "memory_id": "…",           // required
    "user_id":   "sam",          // required
    "outcome":   "good" | "bad" | "stale",   // required
    "note":      "optional freeform text",
    "source":    "claude-code" | "opencode" | "manual" | …
  }
  ```
  Response:
  ```json
  {
    "status": "ok",
    "memory_id": "…",
    "confidence_after": 0.72,
    "action":   "noop" | "deleted"   // "deleted" when bad pushes confidence < threshold
  }
  ```
  - Validate `outcome` against the three allowed values; reject others with 422.
  - Unknown `memory_id`: return 404, do not create shadow rows.

### Storage overlay (Governor-side)

Follow the task-001 pattern: Hippocampus stays pure; the Governor keeps an overlay table.

- New SQLite table `memory_outcomes`:
  ```sql
  CREATE TABLE IF NOT EXISTS memory_outcomes (
      memory_id          TEXT PRIMARY KEY,
      confidence_delta   REAL NOT NULL DEFAULT 0.0,   -- sum of all applied deltas
      salience_delta     REAL NOT NULL DEFAULT 0.0,
      disputed           INTEGER NOT NULL DEFAULT 0,  -- bool
      stale              INTEGER NOT NULL DEFAULT 0,  -- bool
      last_outcome       TEXT,                        -- "good" | "bad" | "stale"
      last_outcome_ts    INTEGER,
      history_json       TEXT NOT NULL DEFAULT '[]'   -- bounded list, last 10 events
  );
  ```
- `history_json` entries: `{ts, outcome, source, note?, confidence_before, confidence_after}`. Cap at 10; drop oldest.

### Effect rules

On successful `POST /outcome`, apply atomically:

- `good`:
  - `confidence_delta += 0.05`, clamp effective confidence ≤ 0.99
  - `salience_delta += 0.05`, clamp effective salience ≤ 1.0
  - Clear `disputed` if previously set by a since-superseded `bad`? No — disputed stays sticky until an explicit human action. Document this.
- `bad`:
  - `confidence_delta = (new_effective_confidence * 0.7) - base_confidence` (apply as a 0.7× multiplier on the current effective, stored as a delta)
  - `disputed = 1`
  - If effective confidence after < `MG_OUTCOME_DELETE_THRESHOLD` (default `0.2`), return `action: "deleted"` and enqueue a delete job through the existing worker. Do NOT delete synchronously — reuse `DurableQueue`.
- `stale`:
  - No confidence change.
  - `stale = 1`.
- Always: append to `history_json`, update `last_outcome` and `last_outcome_ts`.
- Always: append a record to `StreamLog` with `source="governor:outcome"` so the nightly digest can surface it.

### Ranking integration

Extend `app.py:_score` and `app.py:recall` filter logic:

- `effective_confidence = stored_confidence + confidence_delta` (clamped `[0.0, 0.99]`).
- `effective_salience` similarly.
- By default, exclude rows where `memory_outcomes.stale = 1`. Opt back in with `RecallFilters.include_stale: bool` (new, defaults `False`).
- Disputed memories are NOT auto-hidden — they're recallable but `RecallItem` gains an optional `disputed: bool` field in the response so callers can flag them.

Updated rerank (merging task 001's `recall_boost` with outcome-derived values):
```
score = effective_confidence * 0.6
      + recency                * 0.2
      + recall_boost           * 0.1
      + outcome_bonus          * 0.1
where outcome_bonus = 1.0 if last_outcome == "good" else 0.0
```
Confidence weight drops from 0.65 → 0.6; everything else shifts by 0.05 or adds a new 0.1 term. Document the formula in `docs/MEMORY_GOVERNOR.md`.

### Auto-prune interaction

- `hippocampus-auto-prune.timer` prune query: include memories whose effective confidence is below `MG_PRUNE_CONFIDENCE_FLOOR` (new env, default `0.15`) and whose `disputed = 1`. Disputed-and-floored goes first; untagged low-confidence still protected by the task-001 `MG_RECALL_PROTECT_DAYS` window.
- Never prune a memory where `last_outcome_ts` is within the last 7 days, regardless of confidence — gives the loop time to receive a corrective `good` before deletion.

### Claude Code Stop hook

Deferred from task 003. Pure transport; the brains live in the endpoint.

- `scripts/governor_outcome.sh`:
  ```
  governor_outcome.sh --memory-id <id> --outcome good|bad|stale [--note <text>] [--source <src>]
  ```
  Uses `GOVERNOR_URL` / `GOVERNOR_API_KEY` like the other scripts.

- `scripts/governor_session_outcome.sh` (invoked by Claude Code's `Stop` hook):
  - Passive by default. Reads `~/.cache/sacred-brain/claude-pending-outcome.jsonl` — one line per pending outcome, written during the session by explicit user commands.
  - Each line is the full `/outcome` request body. Script POSTs each, then truncates the file on success.
  - If the file is absent or empty: exit 0 silently. No automatic outcome inference in this task — defer that to a later task.
  - Logs to `~/.cache/sacred-brain/claude-bridge.log` (same log as task 003 hooks).

- Extend `ops/claude/install_hooks.sh` (from task 003) to also splice a `Stop` entry for `governor_session_outcome.sh`. Stay idempotent.

- Document a simple manual ritual in `docs/CLAUDE_CODE_BRIDGE.md`: how to queue an outcome from inside a Claude Code session (write a JSON line to the pending file). A slash command for this is *not* in scope here — belongs with task 006 MCP work if/when that lands.

### Nightly digest

- Extend the existing `governor-digest.timer` output: add a section "Outcomes today" summarising counts by (outcome, source) and listing up to 10 deleted memories (id + first 80 chars of text) so there's a recoverable audit trail before the prune timer clears them.

### Config

Add to `memory_governor/config.py` and document in `docs/MEMORY_GOVERNOR.md`:
- `MG_OUTCOME_DELETE_THRESHOLD` (float, default `0.2`)
- `MG_PRUNE_CONFIDENCE_FLOOR` (float, default `0.15`)
- `MG_OUTCOME_GRACE_DAYS` (int, default `7`) — prune protection window after any outcome

Must NOT:
- Mutate Hippocampus memory rows directly. All deltas stay in the Governor overlay.
- Delete synchronously inside the `/outcome` handler. Use the existing `DurableQueue`.
- Auto-mark outcomes on Stop without an explicit signal. Keep this task conservative; aggressive auto-classification is a separate, later task.
- Break the task-001 `recall_stats` reads — the two overlay tables live side by side and are both merged in `_score`.

## Suggested Steps

1. Add `memory_outcomes` table and helpers to `memory_governor/store.py` (`apply_outcome`, `get_effective(memory_id)`, `stale_ids()`, `eligible_for_prune()`).
2. Add `POST /outcome` handler in `app.py`. Wire delete-via-queue path. Unit test each of the three outcome paths.
3. Extend `_score` and the `recall` filter to consult the overlay. Add `include_stale` to `RecallFilters` in `schemas.py`. Add `disputed` to `RecallItem`.
4. Update `hippocampus-auto-prune.*` service/query under `ops/systemd/` to honour `MG_PRUNE_CONFIDENCE_FLOOR` and `MG_OUTCOME_GRACE_DAYS`.
5. Extend the digest script to emit the "Outcomes today" section.
6. Write `scripts/governor_outcome.sh` and `scripts/governor_session_outcome.sh`.
7. Extend `ops/claude/install_hooks.sh` to add the Stop hook; regenerate `ops/claude/example-settings.json`.
8. Update `docs/MEMORY_GOVERNOR.md` (endpoint, formula, env vars) and `docs/CLAUDE_CODE_BRIDGE.md` (Stop hook, pending-outcome ritual).

## Validation

- `pytest` green including new tests in `tests/`:
  - `test_outcome_good_bumps_confidence` — two successive `good` posts raise effective confidence by ~0.10.
  - `test_outcome_bad_multiplies` — a memory with base confidence 0.7 drops to ~0.49 after one `bad`.
  - `test_outcome_bad_triggers_delete` — crossing `MG_OUTCOME_DELETE_THRESHOLD` enqueues a delete job and returns `action: "deleted"`.
  - `test_outcome_stale_hides_from_recall` — stale memory excluded by default, included when `filters.include_stale=true`.
  - `test_outcome_history_bounded` — 15 outcomes leaves exactly 10 entries in `history_json`.
  - `test_recall_merges_both_overlays` — a memory with one `recall_hit` AND one `good` outcome ranks above a bare memory of equal base confidence.
  - `test_prune_respects_grace_days` — a disputed-and-low memory within `MG_OUTCOME_GRACE_DAYS` is not pruned.
- `just smoke` passes.
- Manual:
  - `curl -X POST /outcome` on a real memory, then `curl /recall` — confirm ranking shift.
  - Invoke `scripts/governor_outcome.sh` against a known memory id on homer; inspect `sqlite3 <db_path> "SELECT * FROM memory_outcomes"`.
  - Queue a pending outcome into `claude-pending-outcome.jsonl`, end a Claude Code session, confirm the file is drained and the outcome landed.
  - Next morning: nightly digest shows an "Outcomes today" section.

## References

- `docs/MEMORY_GOVERNOR_v2.md` §2 and §4a (Stop-hook portion)
- `agents/tasks/001_recall_extends_life.md` (overlay-table pattern this task follows)
- `agents/tasks/003_claude_code_bridge.md` (installer and log conventions)
- `memory_governor/app.py` (`recall`, `_score`, new `/outcome` handler)
- `memory_governor/store.py` (new table + helpers)
- `memory_governor/schemas.py` (`RecallFilters.include_stale`, `RecallItem.disputed`)
- `memory_governor/config.py` (three new env vars)
- `ops/systemd/hippocampus-auto-prune.*`, `ops/systemd/governor-digest.*`
- `ops/claude/install_hooks.sh` (extend from task 003)
