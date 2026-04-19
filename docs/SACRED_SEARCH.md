# `sacred-search` — on-demand memory search for coding agents

Thin CLI over Hippocampus's `GET /memories/{user_id}` endpoint. Lets any shell-capable agent (Claude Code, Codex, OpenCode, etc.) pull specific memories mid-session instead of relying on the pre-session context dump.

## Usage

```
sacred-search <query> [user_id] [limit]
```

Defaults: `user_id=sam`, `limit=5`.

## Examples

```
sacred-search "raspberry pi setup"
sacred-search "matrix bridge config" sam 10
sacred-search "xmpp bot" david           # ChatGPT-extracted memories (user:david)
```

## What it hits

- Endpoint: `GET $HIPPOCAMPUS_URL/memories/{user_id}?query=...&limit=...`
- Port 54321 (Hippocampus), **not** the Governor's `/recall` on 54323.
- This is deliberate: ChatGPT archive memories (source `chatgpt_export` / `chatgpt-export`) are suppressed by the Governor's archive filter when called via `/recall`. Hitting Hippocampus directly bypasses that, which is the point — agents often *want* the archive.

## Environment

Loaded from `~/.config/hippocampus.env` or `~/.config/sacred-brain.env`:

| Var | Default | Notes |
|-----|---------|-------|
| `HIPPOCAMPUS_URL` | `http://127.0.0.1:54321` | On non-homer machines, point at homer via Tailscale: `http://100.125.48.108:54321` |
| `HIPPOCAMPUS_API_KEY` | — | Required when Hippocampus auth is enabled (it is, on homer). |

## user_id cheatsheet

| `user_id` | What's there |
|-----------|--------------|
| `sam` | Sam persona memories, incl. raw ChatGPT conversation exports (cron-imported by `chatgpt_export_to_hippocampus.py` at src=`chatgpt_export`) |
| `david` | Memories extracted from ChatGPT history by `scripts/import_chatgpt.py` — typed (`preference`, `project`, `decision`, `fact`, `todo`, etc.) with confidences |
| `mel` | Mel persona |

If you're looking for "that thing I discussed with ChatGPT", try both `sam` (raw transcript chunks) and `david` (distilled structured memories).

## Install

Already installed on homer (symlink at `~/.local/bin/sacred-search` → `/opt/sacred-brain/scripts/sacred-search`). For other machines:

```
ln -sf /opt/sacred-brain/scripts/sacred-search ~/.local/bin/sacred-search
```

…or include `/opt/sacred-brain/scripts/` in your `$PATH`.

## How agents discover it

The pointer line in the repo-root `AGENTS.md` tells any reading agent (Codex, OpenCode, Claude Code) that `sacred-search` exists and when to use it. No additional wiring needed.

## Troubleshooting

- **`401 Unauthorized`** — `HIPPOCAMPUS_API_KEY` missing or wrong. Check `~/.config/hippocampus.env`.
- **`Connection refused`** — Hippocampus isn't running, or `HIPPOCAMPUS_URL` points at the wrong host. On homer: `systemctl --user status hippocampus` or `curl $HIPPOCAMPUS_URL/health`.
- **No memories found** — try a different `user_id` (see cheatsheet), broaden the query, or increase the limit.

## Related

- `docs/API.md` §`GET /memories/{user_id}` — the underlying endpoint
- `docs/CHATGPT_IMPORT.md` — how ChatGPT memories get into Hippocampus
- `scripts/hippocampus_query.sh` in `sam-runtime` / `openclaw/workspace` — prior art this was adapted from
