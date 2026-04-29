# Task: Pi bridge (in progress)

## Context
The Memory Governor already has bridges for Claude Code, OpenCode, and Codex
(`docs/{CLAUDE_CODE,OPENCODE,CODEX}_BRIDGE.md`). Pi (the `pi-coding-agent`
TUI from `@mariozechner/pi-coding-agent`) is now a daily driver but has no
bridge. Unlike the other CLIs, pi exposes a typed extension API
(`pi.on("session_start"/"before_agent_start"/"session_before_compact"/"session_shutdown", ...)`)
rather than a shell-hook config slot, so the natural integration is a TS
extension instead of a launcher wrapper.

## Goal
Pi sessions automatically:
1. Pull recalled memories for `project:<basename(cwd)>/user:$GOVERNOR_USER_ID`
   into `.agents/CONTEXT_MEMORY.md` and into the system prompt at session start.
2. POST the to-be-summarised tail to `/observe` with source `pi:precompact`
   on compaction (capped at 0.35 salience, parallel to the other agents).
3. Drain `~/.cache/sacred-brain/pi-pending-outcome.jsonl` to `/outcome` on
   session shutdown.

## Requirements
- Single-file TS extension at `extensions/pi-bridge.ts` in the repo, installed
  to `~/.pi/agent/extensions/sacred-brain-bridge.ts` per machine.
- Zero npm dependencies — use Node's built-in `fetch` and `node:fs`/`node:os`.
- All bridge operations must swallow errors (TTY/agent flow must never be
  broken by a Governor outage).
- Env loading mirrors the bash bridges: `process.env` → `~/.config/hippocampus.env`
  → `~/.config/sacred-brain.env`. Accept both `GOVERNOR_*` and `HIPPOCAMPUS_*`
  variable names with `GOVERNOR_*` taking precedence.
- Add `"pi:precompact": 0.35` to `LOW_SALIENCE_SOURCES` in
  `memory_governor/mem_policy.py`.
- Logs go to `~/.cache/sacred-brain/claude-bridge.log` (the shared bridge log,
  same as the other bridges).
- Backwards compat: must not change wire formats; `/recall`, `/observe`,
  `/outcome` request bodies match what the existing scripts send.

## Suggested Steps
1. Author `extensions/pi-bridge.ts` with the four lifecycle handlers above.
2. Author `ops/pi/install.sh` (idempotent symlink/copy into
   `~/.pi/agent/extensions/`).
3. Add `pi:precompact` salience cap to `memory_governor/mem_policy.py` and a
   regression test in `tests/`.
4. Author `docs/PI_BRIDGE.md` mirroring the structure of `CODEX_BRIDGE.md`.
5. Add a `### Pi` section to root `AGENTS.md` per-agent quirks block.

## Validation
- `node` smoke test loads the extension via pi's bundled jiti and exercises
  each handler against a live local Governor (`session_start` writes a
  non-empty `.agents/CONTEXT_MEMORY.md`; `before_agent_start` returns a
  longer `systemPrompt`; `session_before_compact` POSTs `/observe` 200;
  `session_shutdown` drains the queue).
- `pytest tests/` passes, including a new test for the `pi:precompact`
  salience cap.

## References
- `extensions/pi-bridge.ts`
- `ops/pi/install.sh`
- `docs/PI_BRIDGE.md`
- `docs/CODEX_BRIDGE.md` (sibling)
- `docs/MEMORY_GOVERNOR_v2.md` §5 (design)
- `memory_governor/mem_policy.py` (`LOW_SALIENCE_SOURCES`)
