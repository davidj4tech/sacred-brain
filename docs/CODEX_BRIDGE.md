# Codex bridge

Wires Codex (OpenAI's CLI coding agent) to the Memory Governor. Codex reads `AGENTS.md` as its primary instruction surface, and the pointer line there already tells any reading agent to treat `.agents/CONTEXT_MEMORY.md` as recalled memory. The bridge's job is just to populate that file and drain pending outcomes on exit.

For the agent-neutral design details — why the drop-file is shared across OpenCode / Codex / future agents — see `docs/OPENCODE_BRIDGE.md`. The install story and conventions here are intentionally parallel.

## How it works

1. **Pre-session context pull** → `governor_context.sh --target codex` writes the top-K memories for `project:<basename>/user:$GOVERNOR_USER_ID` to `.agents/CONTEXT_MEMORY.md`. Same output as `--target opencode` and `--target agents`; they're aliases.
2. **Session exit** → the launcher wrapper drains `~/.cache/sacred-brain/codex-pending-outcome.jsonl` via `trap EXIT`.
3. **PreCompact** → if Codex gains a compaction hook, posts tagged `codex:precompact` are already salience-capped at 0.35 in `mem_policy.LOW_SALIENCE_SOURCES`.

## Install (per machine)

```
./ops/codex/install.sh
```

Symlinks `scripts/governor_context.sh`, `scripts/codex-with-governor`, and `scripts/_outcome_drain.sh` into `~/.local/bin/`. Idempotent. No Codex config splice — the hook API isn't stable enough to pin.

## Usage

### Launcher wrapper (recommended)

```
codex-with-governor [codex args...]
```

Or alias in your shell rc:

```
alias codex=codex-with-governor
```

The wrapper runs `governor_context.sh --target codex`, `exec`s `codex` with the original argv, and drains pending outcomes on exit.

## Per-machine env

Same pattern as the Claude and OpenCode bridges. Put in `~/.config/hippocampus.env`; authoritative values in [`user-config/machines.md`](user-config/machines.md) — use the Governor URL (`:54323`) column.

## Outcomes

Queue outcome events as JSON lines into `~/.cache/sacred-brain/codex-pending-outcome.jsonl`; the launcher wrapper drains them on exit. Each line matches the `/outcome` request body. Failed POSTs stay queued for the next drain.

## Disabling

Stop invoking `codex-with-governor` (remove the alias if you added one). The symlinks in `~/.local/bin/` can stay — nothing runs them unless asked.

## Logs

- `~/.cache/sacred-brain/claude-bridge.log` — shared bridge log; `_outcome_drain.sh` writes drain results here.
- Governor stream log — all `/observe` and `/outcome` events.

## Troubleshooting

- **`.agents/CONTEXT_MEMORY.md` missing or empty.** Check `GOVERNOR_URL` reachable (`curl $GOVERNOR_URL/health`). The pull has a 2s timeout and graceful-degrades on error.
- **Wrapper runs but `codex` not found.** Wrapper `exec`s `codex` from `$PATH`. Install Codex CLI first.
- **Drain never fires.** Ensure you went through the wrapper. To drain manually: `. ~/.local/bin/_outcome_drain.sh && drain_outcomes codex-pending-outcome.jsonl`.

## Related

- `docs/MEMORY_GOVERNOR_v2.md` §5 (design)
- `docs/OPENCODE_BRIDGE.md` (sibling bridge; same file-drop convention)
- `agents/tasks/006_codex_bridge.md` (this task)
