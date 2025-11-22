# Sacred Brain – Hippocampus Service (v0)

A lightweight FastAPI microservice that wraps a Mem0 memory backend and exposes
simple HTTP endpoints for storing, querying, and summarising memories.

## Features

- Store “experiences” (text + metadata) per user.
- Query user memories using semantic/full-text lookups via Mem0.
- Delete memories when they are no longer relevant.
- Summarise multiple memories into a compact form.
- Built-in SQLite persistence fallback when Mem0 is unavailable.
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

If you do not have a Mem0 API key yet, the service falls back to a
SQLite-backed store so your development data survives process restarts.

## Configuration

Configuration is loaded from `config/hippocampus.toml` and can be overridden
with environment variables prefixed by `HIPPOCAMPUS_` (for example,
`HIPPOCAMPUS_MEM0_API_KEY`). See `brain/hippocampus/config.py` for the full set
of options. You can set `mem0.backend` to `cloud` when you have the official
Mem0 SDK installed, or to `sqlite`/`inmemory` as needed. When using the
SQLite fallback, customise `mem0.persistence_path` to control where the DB file
is stored.

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
