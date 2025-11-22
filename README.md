# Sacred Brain – Hippocampus Service (v0)

A lightweight FastAPI microservice that wraps a Mem0 memory backend and exposes
simple HTTP endpoints for storing, querying, and summarising memories.

## Features

- Store “experiences” (text + metadata) per user.
- Query user memories using semantic/full-text lookups via Mem0.
- Delete memories when they are no longer relevant.
- Summarise multiple memories into a compact form.
- Designed for self-hosted Mem0 deployments on a private LAN/Tailscale network.
- Automatically falls back to the local in-memory store (or optional SQLite mode) when Mem0 is unreachable.
- Minimal configuration via TOML + environment variables.
- Ready-to-run with `uvicorn`, includes tests and ops scaffolding.

## Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export HIPPOCAMPUS_CONFIG=config/hippocampus.toml
uvicorn brain.hippocampus.app:app --reload
```

If Mem0 is offline (or not yet installed), the service automatically falls back
to an in-memory store, ensuring Hippocampus keeps accepting requests. You can
also opt into the bundled SQLite backend for persistence if desired.

## Configuration

Configuration is loaded from `config/hippocampus.toml` and can be overridden
with environment variables prefixed by `HIPPOCAMPUS_` (for example,
`HIPPOCAMPUS_MEM0_BACKEND_URL`). See `brain/hippocampus/config.py` for the full
set of options. The default expectation is that you self-host Mem0 on the same
LAN/VPN:

```toml
[mem0]
enabled = true
backend = "remote"          # or "memory"/"sqlite"
backend_url = "http://localhost:7700"
api_key = ""                # optional, for your self-hosted deployment
```

If `enabled = false` (or the remote host fails), the adapter falls back to the
in-memory store so Hippocampus remains responsive. The SQLite backend is still
available for teams that want persistence without Mem0.

## Running Tests

```bash
source .venv/bin/activate
pytest
```

## Ops

- `ops/scripts/dev_run.sh` starts the app with sensible defaults.
- `ops/systemd/hippocampus.service` can be dropped into `/etc/systemd/system`
  as a starting point for Raspberry Pi deployments.

## Next Steps

- Add authentication and per-caller access control.
- Replace the naive summary helper with an LLM-backed summariser.
- Expand metrics/observability once the core API is validated.
