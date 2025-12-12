# v0.2.0-litellm-ingest
- LiteLLM is now the canonical gateway with config at `ops/litellm/config.yaml`, compose stack `ops/compose/litellm/docker-compose.yml`, and systemd unit `ops/systemd/litellm-compose.service`; default bind 127.0.0.1:4000 (see `docs/LITELLM.md`, `docs/LITELLM_GATEWAY.md`).
- Generic ingestion service updated at `ingest/hippocampus_ingest.py` with API key forwarding; docs in `docs/INGEST.md`; systemd unit `ops/systemd/hippocampus-ingest.service`.
- Maubot ingest plugin added under `maubot/ingest/` with packaged `org.sacredbrain.ingest-v0.1.0.mbp`; docs `docs/MAUBOT_INGEST.md`; posts Matrix `m.room.message` events to ingest with dedupe/allowlist/reactions.
- Logging docs streamlined: OpenWebUI-specific autolog docs deprecated in favor of clients→gateway→providers architecture and Hippocampus logging (`docs/LOGGING_TO_HIPPOCAMPUS.md`, `docs/OPENWEBUI_AUTOLOG.md`).
- Hippocampus API unchanged: POST `/memories` and GET `/memories/{user_id}?query=...` require `X-API-Key`.
