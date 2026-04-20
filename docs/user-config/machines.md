# Machines

Authoritative per-machine values for `~/.config/hippocampus.env`. All Sacred Brain tools that talk to Hippocampus / the Governor (`sacred-search`, `governor_context.sh`, bridge installers, `_outcome_drain.sh`) load this env at runtime.

| Machine | Tailscale IP | OS user | `HIPPOCAMPUS_URL` | `GOVERNOR_USER_ID` |
|---------|--------------|---------|-------------------|--------------------|
| homer | 100.125.48.108 | ryer | `http://127.0.0.1:54321` | `sam` |
| sp4r | 100.104.214.49 | ryer | `http://100.125.48.108:54321` | `sam` |
| melr | 100.94.154.59 | mel | `http://100.125.48.108:54321` | `mel` |
| p8ar | 100.94.14.59 | u0_a2 (Termux) | `http://100.125.48.108:54321` | `sam` |

The Governor URL is the same pattern — replace `:54321` with `:54323`.

## Notes

- **homer** is the only machine with Hippocampus / Governor running locally. Everyone else reaches them over Tailscale.
- **melr** is the only machine with a persona override — memories written without explicit scope default to `user:mel`, not `user:sam`.
- **p8ar** (phone, Termux) runs on port 8022 for SSH but the Hippocampus URL is the same as other remotes — it reaches homer outbound over Tailscale.
- The API key is shared across all machines in v1. Per-machine/per-app revocation is a future feature; see `docs/APP_ONBOARDING.md` §5.

## Provisioning

To wire a new machine, follow `docs/APP_ONBOARDING.md` §2 using the row above for its values.

## Adding a machine

1. Pick Tailscale IP + persona `user_id` (usually `sam` unless it's a persona-specific host like `melr`).
2. Add a row above.
3. Update `~/.ssh/config.d/shared` with the hostname ↔ IP mapping.
4. Provision `~/.config/hippocampus.env` and `sacred-search` per `APP_ONBOARDING.md`.
