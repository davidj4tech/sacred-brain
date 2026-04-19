# Task: Claude Code bridge

## Context
Claude Code already has an auto-memory system — frontmatter-typed Markdown files under `~/.claude/projects/<slug>/memory/` with a `MEMORY.md` index — but it's a per-machine, per-project silo with no link to the Governor. Meanwhile the Governor holds the authoritative cross-device memory and will know about project scopes after task 002 ships.

This task wires the two together so Claude Code sessions start with relevant Governor memories in context, and anything Claude Code chooses to remember becomes visible to every other client.

Implements `docs/MEMORY_GOVERNOR_v2.md` §4a (hook pair) and §4b (auto-memory bridge). The Stop/outcome hook half of §4a is deferred to task 004 because it depends on the `/outcome` endpoint.

## Blocked by
- `agents/tasks/002_hierarchical_scopes.md` — without `project:` scopes, recall either leaks across projects or is useless. This task assumes `GET /scopes` and ancestor-matching recall exist.

## Goal
On every Claude Code `SessionStart`, a `.claude/CONTEXT_MEMORY.md` file is written with the top-K Governor memories for the current project + user. Before transcript compaction, the tail is `POST`ed to `/observe` so salient bits survive. A one-shot sync script mirrors `~/.claude/projects/*/memory/*.md` into the Governor with correct scope and kind mapping.

## Requirements

### Scripts live in the repo

Install from `/opt/sacred-brain/scripts/`:

- `scripts/governor_context.sh` — generic context puller. Parameterised:
  ```
  governor_context.sh --target claude|opencode [--scope <path>] [--k 20] [--out <path>]
  ```
  - Reads `GOVERNOR_URL`, `GOVERNOR_API_KEY` from env (fall back to `HIPPOCAMPUS_URL` / `HIPPOCAMPUS_API_KEY` for parity with existing `~/.config/hippocampus.env`).
  - Default scope: `project:$(basename "$PWD")/user:$GOVERNOR_USER_ID`.
  - Default output: `.claude/CONTEXT_MEMORY.md` for `--target claude`.
  - POSTs to `/recall` with `filters.scope`, `min_confidence=0.5`, `k` items; formats results as a markdown bullet list with provenance comments.
  - Exits 0 on empty recall (no memories yet is not an error).
  - Idempotent: overwrites its own output file only; never appends.

- `scripts/governor_precompact.sh` — called by Claude Code's `PreCompact` hook. Reads the transcript path from the hook input ($CLAUDE_TRANSCRIPT or arg), extracts the last ~2000 tokens, POSTs to `/observe` with `source="claude-code:precompact"` and scope matching the current project. Never fails loudly (logs to `~/.cache/sacred-brain/claude-bridge.log`); compaction must proceed regardless.

- `scripts/sync_claude_memory.py` — one-shot sync of Claude Code's auto-memory dir into the Governor.
  - Walks `~/.claude/projects/*/memory/*.md` (path configurable via `--root`).
  - Parses YAML frontmatter; maps `type` → Governor `kind` and default confidence per this table:

    | Claude Code `type` | Governor `kind` | Default `confidence` |
    |---|---|---|
    | `user`      | `semantic`   | 0.80 |
    | `feedback`  | `procedural` | 0.85 |
    | `project`   | `episodic`   | 0.70 |
    | `reference` | `semantic`   | 0.75 |

  - Scope: `project:<dirname-of-projects-subdir>/user:$GOVERNOR_USER_ID` for files under that subdir. Files with `type: user` or `type: reference` also get a duplicate post at bare `user:$GOVERNOR_USER_ID` so they surface in non-project sessions too.
  - Idempotency: local ledger at `~/.cache/sacred-brain/claude-sync-ledger.json` mapping `{absolute_path: sha256(frontmatter+body)}`. Only POST when hash changes. `--force` re-sends everything.
  - `--dry-run` prints what it would POST without hitting the network.
  - `--watch` mode uses `inotifywait` (graceful skip if not installed) to mirror edits live.

### Per-machine install

Do not ship `settings.json` in the repo. Instead:

- `ops/claude/install_hooks.sh` — interactive-friendly installer that:
  - Copies `scripts/governor_context.sh` and `scripts/governor_precompact.sh` to `~/.local/bin/` (symlink if already there).
  - Merges two entries into `~/.claude/settings.json` under `hooks`:
    - `SessionStart` → runs `governor_context.sh --target claude`
    - `PreCompact` → runs `governor_precompact.sh`
  - Preserves any existing hook entries (pattern: read with `jq`, splice, write back; never overwrite wholesale).
  - Emits the exact snippet to `ops/claude/example-settings.json` for manual install as a fallback.
- Document the same for homer, sp4r, melr, p8ar in `docs/CLAUDE_CODE_BRIDGE.md` — each machine runs the installer once.

Cross-device env config (per machine, in `~/.config/hippocampus.env` or shell profile):

| Machine | `GOVERNOR_URL`              | `GOVERNOR_USER_ID` |
|---------|-----------------------------|--------------------|
| homer   | `http://127.0.0.1:54323`    | `sam`              |
| sp4r    | `http://100.125.48.108:54323` (homer via Tailscale) | `sam` |
| melr    | `http://100.125.48.108:54323` (homer via Tailscale) | `mel` |
| p8ar    | `http://100.125.48.108:54323` (homer via Tailscale) | `sam` |

The `GOVERNOR_USER_ID` split between homer/sp4r/p8ar (`sam`) and melr (`mel`) is the main reason scopes must be hierarchical (task 002). `sam` and `mel` are bot personas (both ultimately driven by david, the sole human operator) that share `project:*` ancestors but own distinct `user:*` leaves.

### Governor-side (small)

- No API changes required if task 002 landed; `/recall` with filter scope already does the work.
- Verify that `POST /observe` accepts `source="claude-code:precompact"` without classifier breakage. The salience classifier should treat PreCompact dumps conservatively — add `claude-code:precompact` to a low-salience source list in `mem_policy.classify_observation` so a long compaction tail doesn't flood working memory as candidates. Cap salience at 0.35 for that source.

Must NOT:
- Modify Claude Code's own MEMORY.md index file (read-only).
- Store Claude Code auto-memory content outside the user's stated scope (respect `type: user` vs `type: project`).
- Make Claude Code startup slower than 500ms on the Pi in the cache-warm path. `governor_context.sh` should time out at 2s and degrade gracefully to the last successful output.

## Suggested Steps

1. Write `scripts/governor_context.sh` first; test by hand against a running Governor with seed data.
2. Write `scripts/sync_claude_memory.py`; dry-run against `~/.claude/projects/`; inspect planned POSTs before doing a real sync.
3. Land the `classify_observation` low-salience source list change in `mem_policy.py` with a unit test.
4. Write `scripts/governor_precompact.sh`. Test by manually invoking with a sample transcript path.
5. Write `ops/claude/install_hooks.sh` + `ops/claude/example-settings.json`. Install in this order: homer first (verify end-to-end), then sp4r, then melr, then p8ar. Each machine gets its own `GOVERNOR_URL` / `GOVERNOR_USER_ID` per the table above.
6. Write `docs/CLAUDE_CODE_BRIDGE.md` — one page: what each hook does, how to install, how to disable, where logs go.
7. Full round-trip test (see Validation).

## Validation

- `pytest` green including a new `test_classify_claude_precompact_source` that asserts a `claude-code:precompact` observation gets salience ≤ 0.35 even for long, high-keyword text.
- `scripts/sync_claude_memory.py --dry-run` against `~/.claude/projects/` on homer enumerates the existing memory files with their correct kind/confidence/scope mappings and a stable sha256 ledger.
- Round-trip (cross-device):
  1. Run `sync_claude_memory.py` once against homer's `~/.claude/projects/`.
  2. Open a fresh Claude Code session in `/opt/sacred-brain/` on sp4r.
  3. Confirm `.claude/CONTEXT_MEMORY.md` is created at session start with memories originally written from homer (proves cross-device sync).
  4. Trigger a compaction; confirm an `/observe` entry appears in the Governor's stream log within 5 seconds.
- Round-trip (multi-persona scope isolation):
  1. From melr, `POST /remember` something scoped `project:shared-notes/user:mel`.
  2. From homer (persona `sam`), open a session in a matching project; `CONTEXT_MEMORY.md` must NOT contain mel's memory (different `user:` leaf).
  3. From melr, open a session in the same project; `CONTEXT_MEMORY.md` MUST contain it.
  4. Proves `GOVERNOR_USER_ID` correctly scopes recall per persona, even though the same human (david) is behind both.
- Manual on homer: `tail ~/.cache/sacred-brain/claude-bridge.log` shows no stack traces after a day of normal use.
- Installer idempotency: running `install_hooks.sh` twice leaves `~/.claude/settings.json` valid JSON with exactly one entry per hook type.

## References

- `docs/MEMORY_GOVERNOR_v2.md` §4 (design)
- `agents/tasks/002_hierarchical_scopes.md` (blocker — provides `project:` scope + ancestor recall)
- `memory_governor/mem_policy.py:classify_observation` (low-salience source list)
- `~/.claude/projects/<slug>/memory/` (Claude Code auto-memory layout — read-only here)
- `~/.config/hippocampus.env` (existing env convention to follow)
- MEMORY.md TTS-hook entries — install pattern across homer / sp4r / p8ar is analogous
