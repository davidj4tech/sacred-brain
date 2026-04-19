# OpenCode bridge

Wires OpenCode (the CLI agent) to the Memory Governor. OpenCode reads `AGENTS.md` as its primary instruction surface and has no auto-memory system of its own, so the bridge just needs to drop recalled memories into a file OpenCode already reads.

1. **Pre-session context pull** → `governor_context.sh --target opencode` writes the top-K memories for the current `project:<basename>/user:$GOVERNOR_USER_ID` scope to `.agents/CONTEXT_MEMORY.md` in the workspace. The pointer in the repo-root `AGENTS.md` tells any reading agent to treat that file as recalled memory.
2. **Session exit** → the launcher wrapper drains `~/.cache/sacred-brain/opencode-pending-outcome.jsonl` to `/outcome` via `trap EXIT`, so outcomes queued during the session aren't lost if OpenCode doesn't expose a Stop-equivalent hook.
3. **PreCompact** → if/when OpenCode gains a compaction hook, scripts would POST to `/observe` with source `opencode:precompact`; `mem_policy.classify_observation` already caps that source at 0.35 salience.

`.agents/CONTEXT_MEMORY.md` is agent-neutral — the same file format (only the header comment differs) is used by Claude Code at `.claude/CONTEXT_MEMORY.md`. A future third agent can reuse the same path without more plumbing.

## Install (per machine)

```
./ops/opencode/install.sh
```

The installer symlinks `scripts/governor_context.sh`, `scripts/opencode-with-governor`, and `scripts/_outcome_drain.sh` into `~/.local/bin/`. Idempotent.

It does **not** edit any OpenCode config file — the OpenCode hook API is still in flux. Pick whichever entry point your version supports:

### Option A — launcher wrapper (always works)

```
opencode-with-governor [opencode args...]
```

Optionally alias in your shell rc (`~/.zshrc` or `~/.bashrc`):

```
alias opencode=opencode-with-governor
```

The wrapper runs `governor_context.sh --target opencode`, then `exec`s `opencode` with the original argv, and drains pending outcomes on exit.

### Option B — native pre-session hook (if your OpenCode supports it)

See `ops/opencode/example-config.json` for the config stanza. OpenCode's hook key names may differ between versions — treat the example as a template, not an API contract.

## Per-machine env

Put in `~/.config/hippocampus.env` (the scripts source this if present):

| Machine | `GOVERNOR_URL` | `GOVERNOR_USER_ID` |
|---------|----------------|--------------------|
| homer   | `http://127.0.0.1:54323` | `sam` |
| sp4r    | `http://100.125.48.108:54323` | `sam` |
| melr    | `http://100.125.48.108:54323` | `mel` |

p8ar (phone) is skipped until OpenCode's Termux story is clearer.

## Outcomes

No OpenCode-specific script. Agents queue outcome events as JSON lines into `~/.cache/sacred-brain/opencode-pending-outcome.jsonl`; the launcher wrapper drains on exit. Each line matches the `/outcome` request body:

```json
{"memory_id": "m_123", "outcome": "used", "session_id": "…"}
```

Lines that fail to POST are kept for the next drain.

## Disabling

Stop invoking `opencode-with-governor` (remove the alias if you added one). The symlinks in `~/.local/bin/` can stay — nothing runs them unless you ask.

## Logs

- `~/.cache/sacred-brain/claude-bridge.log` — shared bridge log; `_outcome_drain.sh` writes drain results here regardless of caller.
- Governor stream log — all `/observe` and `/outcome` events.

## Troubleshooting

- **`.agents/CONTEXT_MEMORY.md` missing or empty.** Check `GOVERNOR_URL` reachable (`curl $GOVERNOR_URL/health`). The pull has a 2s timeout and graceful-degrades on error — a missing file means either the call timed out or no memories exist for the scope.
- **Wrapper runs but `opencode` not found.** The wrapper `exec`s `opencode` from `$PATH`. Make sure it's installed and on `$PATH` before the alias.
- **Drain never fires.** The drain runs via `trap EXIT` inside the wrapper. If you invoke `opencode` directly (bypassing the wrapper), queued outcomes stay queued. Run `. ~/.local/bin/_outcome_drain.sh && drain_outcomes opencode-pending-outcome.jsonl` manually.

## Related

- `docs/MEMORY_GOVERNOR_v2.md` §5 (design)
- `docs/CLAUDE_CODE_BRIDGE.md` (sibling bridge; shared scripts and conventions)
- `agents/tasks/005_opencode_bridge.md` (this task)
