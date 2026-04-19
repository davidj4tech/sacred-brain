# Task: OpenCode bridge (done)

## Context
OpenCode reads `AGENTS.md` as its primary instruction surface, with no auto-memory system of its own. Once tasks 001–004 land, the Governor has project scopes, retrieval feedback, and outcome-aware ranking; all that's left is getting OpenCode sessions to see the same memories Claude Code sessions do.

Most of the mechanics are already built: `scripts/governor_context.sh` from task 003 is parameterised on `--target`. This task fills in the OpenCode branch and settles the small convention questions (where the managed block lives, how the session hooks in).

Implements `docs/MEMORY_GOVERNOR_v2.md` §5.

## Blocked by
- `agents/tasks/002_hierarchical_scopes.md` — needs `project:` scopes and ancestor recall.
- `agents/tasks/003_claude_code_bridge.md` — reuses `scripts/governor_context.sh`, the log location, and the env-var conventions.

`agents/tasks/004_outcome_feedback.md` is not a blocker: OpenCode outcome hooks can use the same `scripts/governor_outcome.sh` once it exists, but absence of outcomes doesn't break the context pull.

## Goal
Starting an OpenCode session in any sacred-brain-aware project writes top-K Governor memories into a predictable file that OpenCode reads as additional context. The integration works without forking OpenCode and survives OpenCode version changes. Outcomes posted from an OpenCode session use the same endpoint as Claude Code.

## Requirements

### File layout

- Recalled memories land at `.agents/CONTEXT_MEMORY.md` in the current workspace. Mirror of the Claude Code path (`.claude/CONTEXT_MEMORY.md`) but agent-neutral so a future third agent can reuse it.
- Do NOT write into the repo's checked-in `AGENTS.md` at root — that file contains durable human-written instructions. Instead, add a single pointer line to `AGENTS.md` telling any agent that reads it: *"If `.agents/CONTEXT_MEMORY.md` exists, treat its bullet list as recalled long-term memory for this session."* This keeps the integration discoverable without coupling.
- `.agents/` is gitignored per-repo (add to `.gitignore` if not already).

### Script changes

Extend the scripts shipped in task 003:

- `scripts/governor_context.sh --target opencode`:
  - Default output `.agents/CONTEXT_MEMORY.md`.
  - Same recall call, same scope default (`project:$(basename "$PWD")/user:$GOVERNOR_USER_ID`), same 2s timeout and graceful-degrade behaviour.
  - Output format identical to the Claude target so whoever reads the file doesn't care which agent wrote it.
- Factor any format divergence behind a single `render_memories()` helper inside the script so adding future targets (Cursor, Aider) is a one-liner.

### Session entry points

OpenCode's hook API is less settled than Claude Code's. Ship TWO mechanisms; the user picks whichever their OpenCode version supports:

1. **Native hook** (preferred when available):
   - If OpenCode exposes a pre-session / config-source hook, register `governor_context.sh --target opencode` there.
   - Document the exact config stanza in `docs/OPENCODE_BRIDGE.md`. If the hook API changes upstream, update the doc — do not pin to an unreleased API.

2. **Launcher wrapper** (always works):
   - `scripts/opencode-with-governor` — a small POSIX shell wrapper:
     ```
     #!/bin/sh
     set -e
     governor_context.sh --target opencode || true
     exec opencode "$@"
     ```
   - Install to `~/.local/bin/` via `ops/opencode/install.sh`.
   - Suggest shell alias `alias opencode=opencode-with-governor` in the doc, but do NOT auto-install it (user's shell config is their territory).

### Outcome posting

- No new script needed. `scripts/governor_outcome.sh` from task 004 is reusable as-is.
- Document the same pending-outcome-file convention as Claude Code (`~/.cache/sacred-brain/opencode-pending-outcome.jsonl`, drained by a Stop-equivalent hook if OpenCode supports one, otherwise drained manually or by the launcher wrapper's `trap EXIT`).
- The launcher wrapper gains a `trap` handler that drains the pending file on session exit:
  ```
  trap 'drain_outcomes opencode-pending-outcome.jsonl' EXIT
  ```
  Source a shared `scripts/_outcome_drain.sh` so the same drain logic is available to both bridges.

### Installer

- `ops/opencode/install.sh` — interactive-friendly, idempotent:
  - Copies/symlinks `governor_context.sh` and `opencode-with-governor` to `~/.local/bin/`.
  - If OpenCode's config file is detected, offers to splice a hook entry; otherwise just prints the alias suggestion and exits clean.
  - Never overwrites user config wholesale (same `jq`-splice pattern as the Claude installer).
- `ops/opencode/example-config.<ext>` — whatever OpenCode's config format is at the time — with the native-hook snippet, as a fallback for manual install.

### Governor-side

Zero changes. Task 003's `claude-code:precompact` low-salience source list in `mem_policy.classify_observation` should be generalised to a list — add `opencode:precompact` if/when OpenCode gains a compaction hook. Do this as a one-line edit *in this task*; tests from task 003 carry over.

Must NOT:
- Edit the repo's checked-in `AGENTS.md` beyond adding the single pointer line to `.agents/CONTEXT_MEMORY.md`.
- Assume OpenCode has any specific hook API surface. All design decisions must work against the launcher-wrapper fallback first; native hooks are a bonus.
- Duplicate logic from task 003. If something's worth doing in both bridges, it lives in a shared script or helper.

## Suggested Steps

1. Extend `scripts/governor_context.sh` to handle `--target opencode` (should be a trivial case statement + output path selection).
2. Add `.agents/` to the project `.gitignore` and append the one-line pointer to the repo-root `AGENTS.md`.
3. Write `scripts/opencode-with-governor` and `scripts/_outcome_drain.sh` (factor from the Claude-side drain so both can share it).
4. Generalise the low-salience source list in `mem_policy.py`; update the task-003 test.
5. Write `ops/opencode/install.sh` + an example config snippet.
6. Write `docs/OPENCODE_BRIDGE.md`: what the bridge does, the two install paths (native hook vs wrapper), how outcomes work, how to disable.
7. Install on homer (primary Pi), sp4r (laptop), and melr; leave p8ar (phone) until OpenCode's Termux story is clearer. Per-machine env config (`GOVERNOR_URL`, `GOVERNOR_USER_ID`) follows the same table as task 003 — melr uses `user_id=mel`, the others use `sam`.
8. End-to-end test (see Validation).

## Validation

- `pytest` green; the generalised `test_classify_*_source` covers both `claude-code:precompact` and `opencode:precompact`.
- `scripts/governor_context.sh --target opencode` invoked manually in a project directory creates `.agents/CONTEXT_MEMORY.md` with the expected bullet list and a timestamp comment.
- Launcher wrapper round-trip:
  1. `opencode-with-governor` in `/opt/sacred-brain/` on sp4r.
  2. Session starts; `.agents/CONTEXT_MEMORY.md` is fresh.
  3. Write a pending outcome line into `~/.cache/sacred-brain/opencode-pending-outcome.jsonl` during the session.
  4. Exit OpenCode; the drain fires via `trap EXIT`; the file is truncated; `/outcome` shows the posted event.
- Cross-bridge parity: running `governor_context.sh` with `--target claude` and then `--target opencode` against the same scope produces two files whose bullet lists are identical (only the header comment differs).
- `ops/opencode/install.sh` is idempotent — two runs leave the same end state.
- A fresh OpenCode session on a machine without the bridge installed still works — the pointer line in `AGENTS.md` is a no-op when the file it points to is absent.

## References

- `docs/MEMORY_GOVERNOR_v2.md` §5 (design)
- `agents/tasks/002_hierarchical_scopes.md` (project scopes)
- `agents/tasks/003_claude_code_bridge.md` (shared scripts, installer pattern, log location)
- `agents/tasks/004_outcome_feedback.md` (shared outcome endpoint and drain script)
- `scripts/governor_context.sh` (extend)
- `memory_governor/mem_policy.py:classify_observation` (generalise source list)
- Repo-root `AGENTS.md` (add pointer line only)
- Repo-root `.gitignore` (add `.agents/`)
