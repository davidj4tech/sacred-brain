# Docs index

Landing page for everything in `docs/`. Grouped by what you'd actually come here looking for, not alphabetical.

**New here?** Start with `ARCHITECTURE.md` + `STACK.md`, then jump to whatever slice you need.

**Onboarding a new app?** → [`APP_ONBOARDING.md`](APP_ONBOARDING.md).

---

## Start here

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the live picture: services, data flow, what owns what.
- [`STACK.md`](STACK.md) — services, ports, and where things run at a glance.
- [`INSTALL.md`](INSTALL.md) — fresh-machine bring-up.
- [`APP_ONBOARDING.md`](APP_ONBOARDING.md) — give a new app (coding agent or bot) memory access.

## Memory system

- [`MEMORY_GOVERNOR.md`](MEMORY_GOVERNOR.md) — Governor service (v1 baseline).
- [`MEMORY_GOVERNOR_v2.md`](MEMORY_GOVERNOR_v2.md) — v2 design: scopes, tiers, retrieval-extends-life, outcomes. Active roadmap.
- [`MEMORY_SYNC.md`](MEMORY_SYNC.md) — markdown → Hippocampus sync (`memory_sync.py`).
- [`REFLECTION.md`](REFLECTION.md) — reflection / consolidation pass.
- [`SACRED_SEARCH.md`](SACRED_SEARCH.md) — on-demand memory search CLI for agents.
- [`CHATGPT_IMPORT.md`](CHATGPT_IMPORT.md) — importing ChatGPT conversation exports.

## REST API reference

- [`API.md`](API.md) — Hippocampus endpoints (`/memories`, `/summaries`, …).
- [`INGEST.md`](INGEST.md) — ingest service (`:54322`) for event-stream writes.

## Coding-agent bridges

Each bridge pre-pulls memory into a workspace file at session start and (for Claude Code) writes salient transcript tails back.

- [`CLAUDE_CODE_BRIDGE.md`](CLAUDE_CODE_BRIDGE.md) — SessionStart + PreCompact hooks; full two-way integration.
- [`OPENCODE_BRIDGE.md`](OPENCODE_BRIDGE.md) — launcher wrapper + `.agents/CONTEXT_MEMORY.md`.
- [`CODEX_BRIDGE.md`](CODEX_BRIDGE.md) — mirror of the OpenCode bridge for Codex.

## Matrix / bots / ingest

- [`MATRIX_BRIDGES.md`](MATRIX_BRIDGES.md) — mautrix-meta / signal / telegram / etc.
- [`MAUBOT_INGEST.md`](MAUBOT_INGEST.md) — Matrix `m.room.message` → Hippocampus ingest.
- [`BAIBOT.md`](BAIBOT.md) — Baibot TTS/STT (not a memory client).
- [`VOICE_CALLS.md`](VOICE_CALLS.md) — Asterisk voice-call integration.

## Third-party integrations

- [`LITELLM.md`](LITELLM.md) / [`LITELLM_GATEWAY.md`](LITELLM_GATEWAY.md) — LLM proxy at `:4000`.
- [`OPENWEBUI_INTEGRATION.md`](OPENWEBUI_INTEGRATION.md) / [`OPENWEBUI_AUTOLOG.md`](OPENWEBUI_AUTOLOG.md) — Open WebUI wiring and auto-logging.
- [`LOGGING_TO_HIPPOCAMPUS.md`](LOGGING_TO_HIPPOCAMPUS.md) — getting external apps to log into Hippocampus.
- [`MEM0_SELF_HOSTING.md`](MEM0_SELF_HOSTING.md) / [`MEM0_ORG_ROAM.md`](MEM0_ORG_ROAM.md) — Mem0 backend notes.

## User config (deployment-specific)

Everything specific to David's Sacred Brain deployment — personas, machines, Sam-persona tunings. Siloed so platform docs stay deployment-agnostic. See [`user-config/README.md`](user-config/README.md) for the full index.

- [`user-config/personas.md`](user-config/personas.md) — `user_id` conventions (human vs. persona).
- [`user-config/machines.md`](user-config/machines.md) — per-machine Tailscale IPs, default `GOVERNOR_USER_ID`, and `HIPPOCAMPUS_URL` values.
- [`user-config/SAM_LLM.md`](user-config/SAM_LLM.md) — Sam persona's LLM routing / model config.
- [`user-config/SAM_ASTROLOGY.md`](user-config/SAM_ASTROLOGY.md) — Sam astrology integration.

---

## Conventions

- Docs describe *what* and *why*. Disposable task files live in `agents/tasks/` instead.
- When adding a doc, add a line here under the closest heading — keep this file in sync.
- If a doc becomes stale, prefer deleting or rewriting over adding a new one alongside it.
