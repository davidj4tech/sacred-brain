# Task: Dreaming sweep — scored promotion + REM reflection

## Context

Today's `/consolidate` is rule-based: regex keyword matching in `mem_policy.consolidate_events` assigns fixed confidences (0.5/0.6/0.7) by bucket. There's no ranking, no reflection, and no way to explain why a candidate did or didn't get promoted.

OpenClaw's `dreaming` feature (`/opt/openclaw/docs/concepts/dreaming.md`) ships three useful moves we want to adopt while rejecting its phase metaphor and markdown-as-substrate model:

1. **Weighted multi-signal scoring** with a breakdown you can audit.
2. **A reflection step** that produces a human-readable narrative (`DREAMS.md`).
3. **A `promote-explain` surface** so scoring is legible.

What we keep from sacred-brain's existing design: Hippocampus + SQLite as substrate, explicit `{kind,id}` scopes, safe/raw tiers, systemd as scheduler. Markdown is an output view, not the source of truth.

## Goal

A nightly sweep that: rolls up recall stats, scores promotion candidates with a weighted multi-signal function, promotes those above threshold, and writes a narrative reflection to a configurable `DREAMS.md` path. Operators and agents can ask "why did/didn't this get promoted?" and get a signal-by-signal answer.

## Dependencies

- **Task 001 (recall extends life)** must land first. The scoring function's `frequency` and `relevance` signals read from `recall_stats`; without it those signals are zero and scoring degenerates to recency+tags.
- Tasks 002 (scopes) and 004 (outcome feedback) are orthogonal. If 004 lands before this, add outcome as a 7th signal; if after, wire it in as a follow-up.

## Requirements

### 1. Scoring function

New `memory_governor/mem_policy.py:score_candidate(candidate, stats, ctx) -> ScoreResult`.

```python
class ScoreResult(BaseModel):
    score: float               # [0, 1]
    signals: dict[str, float]  # each signal's contribution, pre-weight
    weighted: dict[str, float] # each signal's contribution, post-weight
    passed: bool               # score >= threshold
    threshold: float
    reasons: list[str]         # human-readable: "below min_recall_count (2 < 3)"
```

Six signals, matching OpenClaw's weights as a starting point (tune later):

| Signal | Weight | Source |
|---|---|---|
| frequency | 0.24 | `recall_stats.recall_count`, log-scaled `min(1.0, log2(1+n)/log2(11))` |
| relevance | 0.30 | avg of `/recall` rerank scores recorded in `stream_log` for this memory_id |
| query_diversity | 0.15 | distinct query strings (or day contexts) that surfaced it |
| recency | 0.15 | time-decayed: `exp(-age_days / 14)` |
| consolidation | 0.10 | distinct UTC-days on which it was recalled |
| conceptual_richness | 0.06 | tag/scope density: `min(1.0, (len(tags) + scope_depth) / 6)` |

Gate thresholds (env-tunable, put in `config.py`):
- `MG_DREAM_MIN_SCORE` default `0.35`
- `MG_DREAM_MIN_RECALL_COUNT` default `2`
- `MG_DREAM_MIN_UNIQUE_QUERIES` default `2`

Backwards compat: `consolidate_events` keeps working as today. Scoring is invoked by the new sweep, not by the hourly `/consolidate` timer. We may fold later.

### 2. `promote-explain` endpoint + CLI

- `POST /promote-explain` — body `{text_or_id, scope?}`. Returns `ScoreResult` plus the candidate's current metadata and a boolean indicating whether it would promote in the next sweep.
- CLI wrapper in `scripts/`: `sacred-brain-explain "router vlan"` → pretty-prints signals, weights, thresholds, gating reasons. Mirrors OpenClaw's `openclaw memory promote-explain`.

### 3. REM reflection + `DREAMS.md`

Nightly subagent turn using Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) with prompt caching on the system prompt and scoring rubric.

- Input: last 24h of `stream_log` entries + today's promoted memories + top-K by recall_count.
- Output: short narrative (~300–600 words) describing themes, recurring ideas, and what the system learned today. No promotion happens here — reflection is read-only on the memory store.
- Write target is configurable via `dreams.output_path` in governor config and `DREAMS_OUTPUT_PATH` env:
  - Sacred-brain default: `/opt/sacred-brain/var/dreams/YYYY-MM-DD.md`, plus rolling symlink `var/dreams/latest.md`.
  - Per-package default override: any downstream package (e.g., a workspace-scoped install) can set the default to `$WORKSPACE_ROOT/DREAMS.md`. The mental model is **workspace = its own git repo**; each repo that wants dreams about itself gets them at its own root.
  - Resolution order: env `DREAMS_OUTPUT_PATH` > config `dreams.output_path` > package default > sacred-brain default.
- Each day's file has frontmatter `{date, promoted_count, reflection_model, input_event_count}` so the reader can audit provenance.

### 4. Sweep runner + systemd

New script `scripts/dream_sweep.py` runs steps in order:

1. `recall_stats_rollup` — recompute per-memory aggregates if needed (cheap).
2. `score_candidates` — for every working/candidate-tier row: compute `ScoreResult`, log to `stream_log` with event type `dream_score`.
3. `promote` — for every row that passed, promote to Hippocampus via existing promotion path (reuse the code `/consolidate` uses today).
4. `reflect` — call Haiku, write `DREAMS.md`.

Each step logs to `stream_log` so the governor digest picks it up.

New systemd units under `ops/systemd/`:
- `sacred-brain-dream.service` — oneshot, runs `scripts/dream_sweep.py`.
- `sacred-brain-dream.timer` — `OnCalendar=*-*-* 03:00:00`, `Persistent=true`.

Retain existing `memory-governor-consolidate.timer` (hourly, rule-based) for now. The nightly sweep is additive.

### 5. Must NOT change

- `/recall` wire format.
- Hippocampus schema.
- Existing `/consolidate` behavior (hourly rule-based path).
- Tier / scope code paths.

## Suggested Steps

1. Add `ScoreResult` schema to `memory_governor/schemas.py`.
2. Implement `score_candidate` in `mem_policy.py`. Pure function, unit-tested in isolation.
3. Wire batch-fetch helpers in `store.py`: `candidate_batch(scope, limit)`, `stats_for_ids(ids)`, `query_diversity_for_ids(ids, window_days)`.
4. Add `POST /promote-explain` to `app.py`. Thin wrapper around `score_candidate` + lookups.
5. Add `scripts/sacred-brain-explain` CLI (mirrors existing script style).
6. Write `scripts/dream_sweep.py`. Keep it composable — each step a callable, main is `orchestrate(steps=[...])`.
7. Add dreams output path resolver in `config.py`: `resolve_dreams_output_path() -> Path`.
8. Add Haiku-backed reflection writer. Use `anthropic` SDK with prompt caching on system + rubric blocks. Model id `claude-haiku-4-5-20251001`.
9. Add systemd unit + timer in `ops/systemd/`. Install via existing install docs path.
10. Update `docs/MEMORY_GOVERNOR.md` with the new env vars, endpoint, CLI, and sweep description. Add a short `docs/DREAMING.md` covering the output path resolution rules and the per-package default override.
11. Tests:
    - `tests/test_score_candidate.py` — signal math, threshold gating, reason strings.
    - `tests/test_promote_explain.py` — endpoint returns a full `ScoreResult` shape; unknown id returns 404.
    - `tests/test_dream_sweep.py` — end-to-end with a tmp SQLite + mocked Haiku; assert a `DREAMS.md` file is written, contains today's date, and that `stream_log` has `dream_score` + `dream_reflect` entries.
    - `tests/test_dreams_output_path.py` — env > config > package default > sacred-brain default resolution order.

## Validation

- `just smoke` passes.
- `pytest` passes including the four new test files.
- Manual: run `python scripts/dream_sweep.py --dry-run` → prints would-promote list with score breakdowns, does not write `DREAMS.md` or touch Hippocampus.
- Manual: run `sacred-brain-explain "some memory text"` → shows signal table, weights, threshold, pass/fail, reasons.
- Manual: trigger the timer (`systemctl start sacred-brain-dream.service`) → `var/dreams/latest.md` exists with today's frontmatter and ~300+ words of narrative.
- Manual: unset `DREAMS_OUTPUT_PATH`, set `dreams.output_path` in config, re-run → writes to the config path. Repeat with env var set — env wins.

## Open follow-ups (not in this task)

- Fold the hourly `/consolidate` into the nightly sweep once the scored path is proven.
- Add `outcome` as a 7th signal after Task 004 lands.
- Scope-aware reflection (one DREAMS per scope) — only if workspaces start demanding it.
- Local model (llama.cpp) as a fallback when Anthropic is unreachable.

## References

- `docs/MEMORY_GOVERNOR_v2.md` §§1–2 (recall-extends-life, outcome feedback)
- `/opt/openclaw/docs/concepts/dreaming.md` (source of the scoring weights + reflection idea)
- `/opt/openclaw/src/memory-host-sdk/dreaming.ts` (reference implementation, do not copy — substrate is different)
- `memory_governor/mem_policy.py:118` (current rule-based `consolidate_events`)
- `memory_governor/app.py` (`/consolidate`, `_score`, `GovernorRuntime`)
- `agents/tasks/001_recall_extends_life.md` (hard dependency)
