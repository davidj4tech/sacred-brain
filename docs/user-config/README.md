# User config

Everything here is specific to David's Sacred Brain deployment — personas, machines, persona-specific tunings. Platform docs (in `docs/` proper) reference this directory for concrete values but stay deployment-agnostic.

If you're spinning up your own Sacred Brain, replace the contents of this directory with your own values. The platform code should keep working; only the operator-facing values change.

## Contents

- [`personas.md`](personas.md) — `user_id` conventions: `david` (human), `sam` / `mel` (bot personas), when to use which.
- [`machines.md`](machines.md) — per-machine Tailscale IPs, default `GOVERNOR_USER_ID`, and the `HIPPOCAMPUS_URL` values that appear in `~/.config/hippocampus.env`.
- [`SAM_LLM.md`](SAM_LLM.md) — Sam persona's LLM routing config (`SAM_LLM_*` env vars, system prompt path).
- [`SAM_ASTROLOGY.md`](SAM_ASTROLOGY.md) — Sam persona's optional astrology-derived bias signals.

## What's still deployment-specific in platform docs

As of this commit, some tables duplicate values that live here. Over time these should migrate to reference `user-config/` instead of copying. Known duplication:

- `APP_ONBOARDING.md` — persona + machine tables (now linked to `user-config/`).
- `CLAUDE_CODE_BRIDGE.md`, `OPENCODE_BRIDGE.md`, `CODEX_BRIDGE.md` — per-machine env tables (now linked to `user-config/machines.md`).
- `MEMORY_SYNC.md` — references `/opt/sam/` paths directly.

## Future

- Genericise `SAM_LLM` / `SAM_ASTROLOGY` to per-persona config templates (the mechanism is generic; the current env-var names are Sam-specific).
- Consider splitting this subdirectory into its own repo if sharing Sacred Brain without David's specifics becomes a real goal.
