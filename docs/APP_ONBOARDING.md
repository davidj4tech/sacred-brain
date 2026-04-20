# App Onboarding — giving a new app memory access

This is the canonical checklist for wiring a new app into Sacred Brain so it can read and/or write long-term memory. Written from the Sacred Brain side: what the operator needs to decide, what to provision, and what to point the app at.

Scope (v1):
- **Coding agents** — Claude Code, Codex, OpenCode, and future ones (Cursor, Aider, …)
- **Bot stack** — Clawdbot / OpenClaw workspace bots, Baibot, Maubot, Matrix bots generally

Out of scope for now (will be covered later): purpose-built external services that talk to Hippocampus over the network from another host without operator setup.

---

## 1. Decide up front

Before touching any config, answer these. Getting them wrong later means re-tagging memories, which is painful.

### 1.1 What `user_id` will the app write under?

Personas vs. humans — David's Sacred Brain convention (see `MEMORY.md` in agent memory stores):

| `user_id` | What it represents | Typical use |
|-----------|--------------------|-------------|
| `david` | David-the-human | ChatGPT-extracted memories, cross-persona facts |
| `sam` | Sam persona (bot) | Default for homer, sp4r, p8ar coding agents; Clawdbot |
| `mel` | Mel persona (bot) | Default for melr |
| *(new persona)* | If adding a new bot persona | Reserve the name first; don't retrofit later |

Rule of thumb: **if a human might later want to attribute memories to themselves**, use a human `user_id`. If it's clearly the bot's voice/state, use a persona. Don't conflate.

### 1.2 Does the app need to *read*, *write*, or both?

- **Read-only** (most coding agents) — just needs `sacred-search` + API key.
- **Write-only** (ingest bots like Maubot) — POSTs to `/memories` or `/ingest`, no search required.
- **Both** (Clawdbot in main-session mode) — full env + tools.

### 1.3 What host is the app on?

Drives the Hippocampus URL:

| Host | `HIPPOCAMPUS_URL` | Notes |
|------|-------------------|-------|
| homer | `http://127.0.0.1:54321` | Services run here; always localhost |
| sp4r, melr, p8ar | `http://100.125.48.108:54321` | Reach homer via Tailscale |
| Other Tailscale node | `http://100.125.48.108:54321` | Same as above |
| Non-Tailscale | Not supported in v1 | See "Future" at bottom |

---

## 2. Provision the env file

Sacred Brain tools (`sacred-search`, the bridge scripts, `governor_context.sh`, etc.) read `~/.config/hippocampus.env` at the app's OS user's home. One env file per OS user, per machine.

### 2.1 Retrieve the API key

On **homer** only:

```
grep ^HIPPOCAMPUS_API_KEY= /home/ryer/.config/hippocampus.env
```

This is the authoritative key. Treat it like a shared secret: scoped to the internal Tailscale network, but still not to be committed, logged, or pasted into chat transcripts that leave the machine.

### 2.2 Place the env file

On the target host, as the target OS user:

```
mkdir -p ~/.config && chmod 700 ~/.config
cat > ~/.config/hippocampus.env <<EOF
HIPPOCAMPUS_URL=<url from table above>
HIPPOCAMPUS_API_KEY=<key from 2.1>
HIPPOCAMPUS_USER_ID=<user_id from 1.1>
EOF
chmod 600 ~/.config/hippocampus.env
```

For apps that run as a different OS user (e.g. `openclaw`, `sam`, `mel`), drop the file at *that* user's `~/.config/hippocampus.env` with ownership to match. The `sacred-brain` Governor service has its own env at `/etc/sacred-brain/hippocampus.env` — don't conflate.

### 2.3 Transferring the key between machines

Manual is fine:

```
scp ~/.config/hippocampus.env user@host:~/.config/hippocampus.env
ssh user@host chmod 600 ~/.config/hippocampus.env
```

…then edit the URL on the remote to use the Tailscale IP. **Do not commit the env file** and do not put the key in any config that goes into git.

---

## 3. Install the tools

### 3.1 `sacred-search` (all apps with shell access)

The on-demand memory-search CLI. See `docs/SACRED_SEARCH.md` for the full reference.

```
# Either symlink from the live tree (homer):
ln -sf /opt/sacred-brain/scripts/sacred-search ~/.local/bin/sacred-search

# Or scp the script to a remote and mark executable:
scp /opt/sacred-brain/scripts/sacred-search host:~/.local/bin/
ssh host chmod +x ~/.local/bin/sacred-search
```

Self-contained — only needs `curl` + `python3`. No repo clone required on remotes.

Verify: `sacred-search "test" david 1` should return a memory or `No memories found.`, not a network/auth error.

### 3.2 Coding-agent bridges (optional — for Claude Code / Codex / OpenCode)

If the app is one of the supported coding agents and you want pre-session memory dumps + outcome tracking (not just on-demand search), install its bridge:

| Agent | Installer | Doc |
|-------|-----------|-----|
| Claude Code | `./ops/claude/install_hooks.sh` | `docs/CLAUDE_CODE_BRIDGE.md` |
| OpenCode | `./ops/opencode/install.sh` | `docs/OPENCODE_BRIDGE.md` |
| Codex | `./ops/codex/install.sh` | `docs/CODEX_BRIDGE.md` |

Run on homer only if editing the sacred-brain repo from homer. For other machines, copy the scripts over or run the installer from a checkout of sacred-brain on that machine.

### 3.3 User-level instruction file (coding agents)

So the agent discovers `sacred-search` without a per-project pointer. Drop one file per agent at its user-level instructions path:

| Agent | Path |
|-------|------|
| Claude Code | `~/.claude/CLAUDE.md` |
| Codex | `~/.codex/AGENTS.md` |
| OpenCode | `~/.config/opencode/AGENTS.md` |

Contents (identical across agents — keep in sync):

```markdown
# Global instructions

## Long-term memory

To search David's long-term memory on demand, run:

    sacred-search <query> [user_id] [limit]

Defaults: `user_id=sam`, `limit=5`. Use `user_id=david` to search memories extracted from David's ChatGPT conversation history.

This hits Sacred Brain's Hippocampus store directly. Use it when a query is likely to reference something David has discussed before (past decisions, project context, ChatGPT conversations) rather than guessing from context alone.

See `/opt/sacred-brain/docs/SACRED_SEARCH.md` for details.
```

For Claude Code, this auto-loads. For Codex and OpenCode, loading at user-scope is by convention — verify once per version by asking a fresh session "what is sacred-search?" outside any project.

### 3.4 Bot stack integrations (read the relevant doc, don't freelance)

These bots already have integration patterns. Follow their docs rather than inventing new ones:

| Bot | Doc | What it integrates |
|-----|-----|-------------------|
| Maubot | `docs/MAUBOT_INGEST.md` | Matrix event → `/ingest` writer |
| Matrix bridges (meta, signal, telegram, …) | `docs/MATRIX_BRIDGES.md` | via Maubot / Hippocampus ingest |
| Baibot | `docs/BAIBOT.md` | TTS/STT, not a memory client |
| Clawdbot / OpenClaw workspace bots | `/var/lib/openclaw/workspace/AGENTS.md` + `docs/MEMORY_SYNC.md` | File-based memory synced to Hippocampus via `hippocampus_memory_sync.py` |
| ChatGPT export importer | `docs/CHATGPT_IMPORT.md` | One-shot memory import |

For a **new bot** not in this list: use an existing one as a template. Writers hit `/memories` or `/ingest`; readers hit `/memories/{user_id}?query=...` via `sacred-search` or direct curl.

---

## 4. Verify

### 4.1 Auth + connectivity

```
curl -s -H "X-API-Key: $HIPPOCAMPUS_API_KEY" $HIPPOCAMPUS_URL/health
# {"status":"ok"}
```

401 → API key wrong. Connection refused → URL wrong or Hippocampus not running.

### 4.2 Read path

```
sacred-search "chatgpt" david 3
```

Should return ChatGPT-extracted memories. If `No memories found.`, try a broader query or `sam` user_id.

### 4.3 Write path (if applicable)

```
curl -s -H "X-API-Key: $HIPPOCAMPUS_API_KEY" -H "Content-Type: application/json" \
  -X POST $HIPPOCAMPUS_URL/memories \
  -d '{"user_id":"<user_id>","text":"onboarding smoke test","metadata":{"source":"onboarding"}}'
```

Check the response contains a `memory.id`. Clean up with `DELETE /memories/{id}` if the test memory shouldn't persist.

### 4.4 Agent integration (coding agents)

On the target host, start a fresh session outside any project with its own AGENTS.md, and ask:

> "What is sacred-search, and when would you use it?"

A correct answer cites the usage, both default user_ids (`sam` / `david`), and describes it as on-demand long-term memory. If the agent shrugs, the user-level instruction file isn't loading — check the path for that agent's version.

---

## 5. Cleanup / offboarding

To revoke an app's access:

1. Delete `~/.config/hippocampus.env` on its host (as its OS user).
2. If the app is on its own host, that's enough — without the env it can't auth.
3. If other apps on the same OS user still need access, instead just rotate the shared API key on Hippocampus (see `docs/INSTALL.md` for auth config) and re-provision only the apps that should keep access.

Sacred Brain does not (yet) have per-app API keys. If you need per-app revocation, that's a feature request — file it in `agents/tasks/` before adding more apps that would suffer from its absence.

---

## Future (v2 scope — not yet implemented)

- **Per-app API keys** — so an app can be revoked without rotating the global key.
- **External-host onboarding** — Sacred Brain exposed beyond the Tailscale network, with per-client certs or scoped tokens.
- **Onboarding script** — an interactive `scripts/onboard_app.sh` that walks through this checklist. Documented first, scripted when the pattern has stabilised over ≥3 real onboardings.
- **Scope-aware memory provisioning** — pre-seeding project scopes during onboarding so the first `governor_context.sh` pull isn't empty.

---

## Related

- `docs/STACK.md` — port map and running services
- `docs/API.md` — Hippocampus REST API reference
- `docs/MEMORY_GOVERNOR_v2.md` — scopes, tiers, and the Governor's policy layer
- `docs/SACRED_SEARCH.md` — on-demand search tool
- `docs/CLAUDE_CODE_BRIDGE.md` / `docs/OPENCODE_BRIDGE.md` / `docs/CODEX_BRIDGE.md` — per-coding-agent bridges
