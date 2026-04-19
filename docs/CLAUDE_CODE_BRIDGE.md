# Claude Code bridge

Wires Claude Code (the CLI agent) to the Memory Governor:

1. **SessionStart** → `governor_context.sh` writes the top-K memories for the current project/user scope to `.claude/CONTEXT_MEMORY.md`, which Claude Code loads into context.
2. **PreCompact** → `governor_precompact.sh` POSTs the transcript tail to `/observe` so salient pieces survive compaction. Source is tagged `claude-code:precompact`; salience is capped at 0.35 in `mem_policy.py` so dumps don't flood candidate memory.
3. **One-shot sync** → `sync_claude_memory.py` mirrors `~/.claude/projects/*/memory/*.md` into the Governor with type→kind mapping and a sha256 ledger for idempotency.

## Install (per machine)

```
./ops/claude/install_hooks.sh
```

The installer:
- symlinks `scripts/governor_context.sh` and `scripts/governor_precompact.sh` into `~/.local/bin/`
- splices SessionStart + PreCompact entries into `~/.claude/settings.json` via `jq`, preserving existing hooks. Re-running is idempotent.

Requires `jq`. Falls back to the manual snippet at `ops/claude/example-settings.json` if you'd rather edit settings by hand.

## Per-machine env

Put in `~/.config/hippocampus.env` (the scripts source this if present):

| Machine | `GOVERNOR_URL` | `GOVERNOR_USER_ID` |
|---------|----------------|--------------------|
| homer   | `http://127.0.0.1:54323` | `sam` |
| sp4r    | `http://100.125.48.108:54323` | `sam` |
| melr    | `http://100.125.48.108:54323` | `mel` |
| p8ar    | `http://100.125.48.108:54323` | `sam` |

`sam` and `mel` are bot personas; the `GOVERNOR_USER_ID` difference is why scopes are hierarchical (see `docs/MEMORY_GOVERNOR_v2.md` §3).

## Manual sync

```
scripts/sync_claude_memory.py --dry-run           # preview
scripts/sync_claude_memory.py                      # sync (ledger at ~/.cache/sacred-brain/claude-sync-ledger.json)
scripts/sync_claude_memory.py --force              # re-send everything
scripts/sync_claude_memory.py --watch              # live mirror (requires inotifywait)
```

Type mapping (from Claude Code frontmatter `type:` → Governor `kind` + default confidence):

| `type:`     | `kind:`      | confidence |
|-------------|--------------|------------|
| `user`      | `semantic`   | 0.80 |
| `feedback`  | `procedural` | 0.85 |
| `project`   | `episodic`   | 0.70 |
| `reference` | `semantic`   | 0.75 |

`type: user` and `type: reference` are also posted at bare `user:<id>` scope so they surface in non-project sessions.

## Disabling

Remove the two entries from `~/.claude/settings.json` under `hooks.SessionStart` and `hooks.PreCompact`. The symlinks in `~/.local/bin/` can stay — nothing invokes them without the settings entry.

## Logs

- `~/.cache/sacred-brain/claude-bridge.log` — PreCompact + outcome hook actions (one line per invocation).
- Governor stream log — all `/observe` and `/outcome` events, including those coming from this bridge.

## Troubleshooting

- **CONTEXT_MEMORY.md is empty.** Check `GOVERNOR_URL` reachable (`curl $GOVERNOR_URL/health`) and that memories exist under your scope (`curl $GOVERNOR_URL/scopes`).
- **PreCompact not firing.** Settings JSON invalid, or Claude Code version too old. The installer refuses to edit invalid JSON. Validate with `jq . ~/.claude/settings.json`.
- **Sync script skipping files.** Delete the ledger at `~/.cache/sacred-brain/claude-sync-ledger.json` and rerun, or use `--force`.

## Related

- `docs/MEMORY_GOVERNOR_v2.md` §4 (design)
- `agents/tasks/003_claude_code_bridge.md` (this task)
- `agents/tasks/004_outcome_feedback.md` (Stop-hook portion; TODO)
