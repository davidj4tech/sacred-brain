# Pi bridge

Wires [pi](https://github.com/badlogic/pi-mono) (the `pi-coding-agent` TUI) to
the Memory Governor. Unlike Codex/OpenCode/Claude Code — which expose
shell-hook config slots — pi has a first-class typed extension API
(`pi.on("session_start", ...)`, `pi.on("session_before_compact", ...)`, etc.),
so the bridge is a single TypeScript module instead of a launcher wrapper.

## How it works

The bridge subscribes to four pi lifecycle events:

| Event | What the bridge does |
|---|---|
| `session_start`        | POST `/recall` for `project:<basename(cwd)>/user:$GOVERNOR_USER_ID`, write the result to `.agents/CONTEXT_MEMORY.md`, and cache it in memory. |
| `before_agent_start`   | Append the cached memory block to `event.systemPrompt`. Stable text → friendly to provider prompt-cache. Disable with `PI_BRIDGE_INJECT=0`. |
| `session_before_compact` | POST the to-be-summarised tail to `/observe` with `source: "pi:precompact"`. Salience is capped at 0.35 in `mem_policy.LOW_SALIENCE_SOURCES`. |
| `session_shutdown`     | Drain `~/.cache/sacred-brain/pi-pending-outcome.jsonl` to `/outcome`. Failed lines stay queued for next time. |

`.agents/CONTEXT_MEMORY.md` uses the same agent-neutral format as the
OpenCode/Codex bridges, so a workspace switching between agents sees a
consistent file.

## Install (per machine)

```sh
./ops/pi/install.sh
```

Symlinks `extensions/pi-bridge.ts` into `~/.pi/agent/extensions/sacred-brain-bridge.ts`.
Pi auto-discovers extensions in that directory and loads them via its bundled
jiti — no compilation step, no `npm install`.

The extension uses Node's built-in `fetch` and reads env from process and
`~/.config/hippocampus.env` (same convention as the other bridges). Zero npm
dependencies.

## Per-machine env

Put in `~/.config/hippocampus.env` or your shell profile:

```sh
GOVERNOR_URL=http://127.0.0.1:54323     # or a Tailscale IP for off-host pi
GOVERNOR_API_KEY=…
GOVERNOR_USER_ID=sam
```

`HIPPOCAMPUS_*` names are accepted as fallbacks for parity with the older
bridges. If you only set `HIPPOCAMPUS_URL`, make sure it points at the
**Governor** (`:54323`) — not raw Hippocampus (`:54321`) — since `/recall`
lives on the Governor.

Authoritative per-machine values: [`user-config/machines.md`](user-config/machines.md).

## Configuration knobs

| Variable | Default | Meaning |
|---|---|---|
| `PI_BRIDGE_DISABLE` | unset | Set to `1` to disable the whole bridge |
| `PI_BRIDGE_INJECT`  | enabled | Set to `0` to skip system-prompt injection (file-only mode) |
| `PI_BRIDGE_K`       | `20` | Top-K memories to recall |

## Outcomes

Same convention as the sibling bridges. Append JSON lines matching the
Governor `/outcome` body to `~/.cache/sacred-brain/pi-pending-outcome.jsonl`.
The bridge drains them on `session_shutdown`. Failed posts stay queued.

```json
{"memory_id": "m_123", "outcome": "used", "session_id": "…"}
```

## Disabling

Two options:
- Quick toggle for one session: `PI_BRIDGE_DISABLE=1 pi`
- Permanent: `rm ~/.pi/agent/extensions/sacred-brain-bridge.ts` (the symlink
  itself; the source in the repo stays intact)

## Logs

- `~/.cache/sacred-brain/claude-bridge.log` — shared bridge log; pi-bridge
  events are tagged `pi-bridge`.
- Governor stream log — all `/observe` and `/outcome` events.

## Troubleshooting

- **`.agents/CONTEXT_MEMORY.md` empty or stale.** Check `GOVERNOR_URL`
  reachable: `curl $GOVERNOR_URL/health`. The recall has a 2 s timeout and
  graceful-degrades on error. Watch `~/.cache/sacred-brain/claude-bridge.log`
  for `pi-bridge recall: …` lines.
- **`recall: http 404`.** You're hitting Hippocampus (`:54321`) instead of
  the Governor (`:54323`). Set `GOVERNOR_URL` explicitly.
- **System prompt not getting the memory block.** `PI_BRIDGE_INJECT=0` may
  be in the env, or `session_start` may have failed (no cache). Check log.
- **Extension not loading at all.** Run `pi --extension /opt/sacred-brain/extensions/pi-bridge.ts`
  for a one-shot test; pi prints load errors on stderr. The auto-discovery
  path is `~/.pi/agent/extensions/*.ts`.

## Comparison with the other bridges

| Aspect | Claude Code | Codex | OpenCode | **Pi** |
|---|---|---|---|---|
| Hook surface | Settings JSON `Stop`/`PreCompact` hooks | `config.toml` command pipe | Launcher wrapper / native pre-session hook | TS extension API |
| Pre-session pull | SessionStart hook → `governor_context.sh` | Wrapper `exec` → `governor_context.sh` | Wrapper `exec` → `governor_context.sh` | `pi.on("session_start")` |
| PreCompact ingest | `governor_precompact.sh` posts transcript tail | (no compaction hook yet) | (no compaction hook yet) | `pi.on("session_before_compact")` |
| Outcome drain | (TODO — see task 004) | `trap EXIT` in wrapper | `trap EXIT` in wrapper | `pi.on("session_shutdown")` |
| System-prompt injection | n/a (hook-based) | n/a (file-based only) | n/a (file-based only) | optional, on top of file |

The pi bridge is the most natural fit because pi exposes the lifecycle the
other agents only approximate via wrappers and shell hooks.

## Related

- `docs/MEMORY_GOVERNOR_v2.md` §5 (design)
- `docs/CODEX_BRIDGE.md`, `docs/OPENCODE_BRIDGE.md`, `docs/CLAUDE_CODE_BRIDGE.md`
- `agents/tasks/010_pi_bridge.md` (this task)
