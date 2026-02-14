# v0.3.0 (2026-02-15)

## Restructuring
- **Removed**: Ingest service (port 54322) — Governor now writes directly to Hippocampus.
- **Consolidated**: Single service user (`sacred`, nologin shell). Removed `memory-governor` user.
- **FHS layout**: State moved to `/var/lib/sacred-brain/`, config to `/etc/sacred-brain/`.
- **Unified config**: All inline `Environment=` vars moved to env files. Dead config files removed.
- **Hardening**: All systemd units now use `ProtectSystem=strict`, `NoNewPrivileges=true`, etc.
- **Digest timer**: `governor-digest.timer` runs nightly at 03:20, writes markdown digests to `/opt/sam/memory/memory/`.
- **Ops**: Added `/opt/sacred-brain/justfile` with recipes: `start`, `stop`, `restart`, `status`, `logs`, `health`, `timers`, `backup`, `backup-db`, `smoke`, `config-check`, `security-audit`, `remove-compat-symlinks`.
- **Cleanup**: Removed dead `ingest/` directory, orphaned `chatgpt_export_to_hippocampus.py` script, empty dirs.

| Before | After |
|--------|-------|
| 3 services (54321, 54322, 54323) | 2 services (54321, 54323) |
| 2 service users | 1 user (`sacred`, nologin) |
| State in `/opt/sacred-brain/{data,var}/` | State in `/var/lib/sacred-brain/` |
| Config in 4+ locations | Config in `/etc/sacred-brain/` |
| Zero systemd hardening | ProtectSystem=strict, NoNewPrivileges, etc. |
| Orphaned digest script | Nightly systemd timer |
| No ops tooling | justfile |

# v0.2.1-governor-fix (2026-02-14)
- **Fix**: Memory Governor `_process_job` now correctly unwraps the DurableQueue job envelope before checking job type. Previously, every enqueued memory was silently marked done without being written to Hippocampus (`memory_governor/app.py`).
- **Fix**: State directory ownership corrected (`var/memory-governor/` must be owned by `memory-governor` user, not `sacred`).
- **Ops**: Added full pipeline health check, known failure modes table, and service dependency diagram to `docs/MEMORY_GOVERNOR.md`.
- **Ops**: Added Ingest (54322) and Memory Governor (54323) ports to `docs/STACK.md`.

# v0.2.0-litellm-ingest
- LiteLLM is now the canonical gateway with config at `ops/litellm/config.yaml`, compose stack `ops/compose/litellm/docker-compose.yml`, and systemd unit `ops/systemd/litellm-compose.service`; default bind 127.0.0.1:4000 (see `docs/LITELLM.md`, `docs/LITELLM_GATEWAY.md`).
- Generic ingestion service updated at `ingest/hippocampus_ingest.py` with API key forwarding; docs in `docs/INGEST.md`; systemd unit `ops/systemd/hippocampus-ingest.service`.
- Maubot ingest plugin added under `maubot/ingest/` with packaged `org.sacredbrain.ingest-v0.1.0.mbp`; docs `docs/MAUBOT_INGEST.md`; posts Matrix `m.room.message` events to ingest with dedupe/allowlist/reactions.
- Logging docs streamlined: OpenWebUI-specific autolog docs deprecated in favor of clients→gateway→providers architecture and Hippocampus logging (`docs/LOGGING_TO_HIPPOCAMPUS.md`, `docs/OPENWEBUI_AUTOLOG.md`).
- Hippocampus API unchanged: POST `/memories` and GET `/memories/{user_id}?query=...` require `X-API-Key`.
