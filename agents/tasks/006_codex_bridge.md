# Task: Codex bridge (done)

## Context
Codex (OpenAI's CLI coding agent) reads `AGENTS.md` as its primary instruction surface, same as OpenCode. The repo-root `AGENTS.md` already carries the pointer line telling any reading agent to treat `.agents/CONTEXT_MEMORY.md` as recalled long-term memory. That means once a pre-session pull populates that file, Codex picks it up for free — no forking, no plugin API.

What's missing is the entry point: there's no wrapper to trigger the pull, no documented install path, and no outcome-drain on exit.

Design note: OpenCode (task 005) and Codex share the same file-drop convention. Rather than stamping out a new `--target codex` arm that behaves identically to `--target opencode`, this task introduces a neutral `--target agents` alias that both point at, and keeps thin per-agent wrappers for ergonomics. Future agents (Cursor, Aider) slot into the same surface.

## Blocked by
- `agents/tasks/005_opencode_bridge.md` — reuses `scripts/governor_context.sh`, `.agents/CONTEXT_MEMORY.md` convention, `_outcome_drain.sh`, and the `AGENTS.md` pointer line.

## Goal
Starting a Codex session in any sacred-brain-aware project writes top-K Governor memories into `.agents/CONTEXT_MEMORY.md`, which Codex loads as additional context. Outcomes queued during the session drain on exit. Zero Codex version pinning — if Codex's hook story changes, only the wrapper needs updating.

## Requirements

### Script changes

- `scripts/governor_context.sh`: add `--target codex` and `--target agents` as aliases for the existing `opencode` branch (same output path, same scope default, same format). The `agents` name is the agent-neutral canonical form; `opencode` and `codex` become thin aliases. Document at the top of the script that `agents` is preferred for new integrations.
- No new `render_*` helper needed — output format is already identical across targets per task 005.

### Launcher wrapper

- `scripts/codex-with-governor` — POSIX sh, mirror of `scripts/opencode-with-governor`:
  - Pre-pull via `governor_context.sh --target codex` (or `--target agents`).
  - Source `_outcome_drain.sh`; `trap 'drain_outcomes codex-pending-outcome.jsonl' EXIT`.
  - `exec codex "$@"`.
- Do NOT auto-install the shell alias; document it.

### Installer

- `ops/codex/install.sh` — symlinks `governor_context.sh`, `codex-with-governor`, and `_outcome_drain.sh` into `~/.local/bin/`. Idempotent. No config splice (same reason as OpenCode: Codex's hook API isn't stable enough to pin).
- `ops/codex/example-config.*` — if Codex has a canonical config format at the time, include a native-hook snippet; otherwise skip this file and note in the docs.

### Governor-side

- Add `codex:precompact` to `LOW_SALIENCE_SOURCES` in `memory_governor/mem_policy.py` as a one-line edit, for the day Codex grows a compaction hook. Extend the existing `test_classify_*_source` fixture to cover it (copy/paste of the opencode test, rename).

### Docs

- `docs/CODEX_BRIDGE.md` — install path, per-machine env table (same one used in 003/005), launcher wrapper usage, outcome drain, troubleshooting. Cross-link to `docs/OPENCODE_BRIDGE.md` rather than duplicating the agent-neutral bits.
- Update the `### Codex` subsection in repo-root `AGENTS.md` to note the bridge exists and points at the same `.agents/CONTEXT_MEMORY.md` file everyone else uses. Keep it short — the file is instruction surface, not documentation.

### Historical notes

- Do NOT touch `codex/tasks/001`–`009`. Those are frozen historical records.
- `codex/instructions.md` stays superseded. The bridge does not revive it.

Must NOT:
- Introduce a Codex-specific CONTEXT_MEMORY path. `.agents/CONTEXT_MEMORY.md` is the shared drop-point; diverging here fragments future agents.
- Duplicate `render_memories` or drain logic. If behavior differs between OpenCode and Codex, factor into a shared helper first.
- Assume any particular Codex version's hook API. Wrapper-first; native hooks are bonus only.

## Suggested Steps

1. Extend `scripts/governor_context.sh` with `codex` and `agents` target aliases.
2. Write `scripts/codex-with-governor` (copy of opencode wrapper, two-line diff).
3. Add `codex:precompact` to `mem_policy.LOW_SALIENCE_SOURCES`; add the test.
4. Write `ops/codex/install.sh`.
5. Write `docs/CODEX_BRIDGE.md`; update the `### Codex` section in `AGENTS.md`.
6. Install on homer; smoke-test the wrapper in `/tmp/test-codex/`.
7. Commit as one reviewable PR.

## Validation

- `pytest` green; `test_classify_codex_precompact_source_capped` exists.
- `scripts/governor_context.sh --target codex` in a fresh project directory creates `.agents/CONTEXT_MEMORY.md`.
- Cross-target parity: `--target claude`, `--target opencode`, and `--target codex` against the same scope produce bullet lists that differ only in the header comment.
- `ops/codex/install.sh` is idempotent — two runs leave the same end state.
- Launcher wrapper round-trip on homer: queue an outcome line, exit, confirm drained via Governor stream log.

## References

- `docs/MEMORY_GOVERNOR_v2.md` §5 (shared design)
- `agents/tasks/005_opencode_bridge.md` (pattern to copy)
- `docs/OPENCODE_BRIDGE.md` (cross-link target)
- `scripts/governor_context.sh` (extend)
- `scripts/opencode-with-governor` (mirror)
- `memory_governor/mem_policy.py:classify_observation` (one-line edit)
- Repo-root `AGENTS.md` § Codex (short update)
