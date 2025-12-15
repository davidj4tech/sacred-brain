# Mem0 Self-Hosting Guide

Deploying Hippocampus with a live Mem0 backend unlocks semantic querying and
long-term retention while still retaining the automatic in-memory fallback when
Mem0 is unavailable. This guide walks through running Mem0 locally (Pi-friendly)
with Docker Compose, wiring Hippocampus, and validating failover behaviour.

> Reference: upstream Mem0 documentation – https://github.com/mem0ai/mem0

## 1. Run Mem0 Locally

Requirements:

- Docker Engine ≥ 24 (or Docker Desktop / rootless Docker). Works on Raspberry
  Pi OS Bullseye with the official `docker-ce` packages.
- Git access to clone the official Mem0 repository.
- OpenAI API key for embeddings (Mem0’s default configuration).

Steps:

```bash
cd ops/mem0
./prepare_mem0_source.sh          # clones/updates ../ext/mem0
cd ../../ext/mem0/server
cp .env.example .env              # edit OPENAI_API_KEY, MEM0_API_KEY, etc.
OPENAI_API_KEY=sk-yourkey docker compose up -d
docker compose logs -f mem0      # follow logs until you see "server started"
```

The upstream Compose stack exposes `http://127.0.0.1:8888` (Mem0) and brings up
Postgres + Neo4j automatically. Manage it with:

```bash
docker compose stop
docker compose start
docker compose down
```

## 2. Configure Hippocampus

Copy `config/hippocampus.toml` and override the Mem0 block:

```toml
[mem0]
enabled = true
backend = "remote"
backend_url = "http://127.0.0.1:8888"
api_key = "" # set only if MEM0_API_KEY is enforced
```

Export the config via env vars (Pi-friendly):

```bash
export HIPPOCAMPUS_CONFIG=/home/pi/sacred-brain/config/hippocampus.toml
export HIPPOCAMPUS_MEM0_ENABLED=true
export HIPPOCAMPUS_MEM0_BACKEND=remote
export HIPPOCAMPUS_MEM0_BACKEND_URL=http://127.0.0.1:8888
export HIPPOCAMPUS_MEM0_API_KEY="${MEM0_API_KEY:-}"
```

Then start Hippocampus (see `ops/scripts/dev_run.sh` or your systemd unit).

If you want to lock down the Hippocampus API, set `[auth].enabled = true` (or export `HIPPOCAMPUS_AUTH_API_KEYS` with a comma-separated list). Every request must then send the configured header, so include the same key in your client or monitoring scripts.

The Mem0 SDK requires Hippocampus to have that API key (via `[mem0].api_key` or
`HIPPOCAMPUS_MEM0_API_KEY`). If the key is missing, the adapter immediately
falls back to the SQLite/in-memory stores even if the remote server is running.

## 3. Health Checks

Mem0 does not currently expose a `/health` route; instead, hit `/docs` or call
`/memories` (e.g., `curl http://127.0.0.1:8888/memories?user_id=demo`) to verify
the server is online.

## 4. Verify Remote/Fallback Behaviour

Hippocampus must continue running even if Mem0 stops. Follow these steps to
prove the remote adapter + fallback logic are wired correctly:

1. **Start Mem0** – `cd ops/mem0 && ./prepare_mem0_source.sh && docker compose up -d`.
2. **Confirm health** – `./ops/scripts/check_mem0.sh`.
3. **Start Hippocampus** – `source .venv/bin/activate && HIPPOCAMPUS_MEM0_ENABLED=true uvicorn brain.hippocampus.app:app`.
4. **Create/query a memory** – `curl -X POST http://127.0.0.1:54321/memories ...`
   and observe logs showing `Using remote Mem0 backend`.
5. **Simulate outage** – `docker compose stop mem0`.
6. **Call the API again** – Hippocampus should still return results using the
   in-memory fallback. Logs emit a warning similar to `Primary backend failed ... falling back to in-memory`.
7. **Restore Mem0** – `docker compose start mem0` and rerun the health check.
8. **Confirm remote mode resumes** – New requests should succeed without the
   warning, and logs note that Mem0 is available again.

Because the adapter wraps Mem0 calls and traps exceptions, Hippocampus continues
serving traffic throughout the stop/start cycle. The health check script plus
docker-compose commands provide a reproducible way for new operators to validate
the behaviour on Raspberry Pi hardware (or any Linux host).

## Troubleshooting

- `check_mem0.sh` exits `1`: inspect `docker compose logs mem0` and ensure port
  `8888` is free.
- Hippocampus still uses fallback when Mem0 is up: confirm `mem0.enabled=true`
  and the `backend_url` matches the reachable host/IP. Look for warnings in
  `uvicorn` output to spot authentication errors or DNS issues.
- Want a non-Docker deployment? Consult the Mem0 docs to run the Python package
  under systemd with `mem0 serve --host 0.0.0.0 --port 8888`, then reuse the
  same health checks/config above.
