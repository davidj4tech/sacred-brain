# (Deprecated) OpenWebUI Auto-Logging to Hippocampus

Deprecated: use client-agnostic logging via `/ingest` (see `docs/INGEST.md`) or
LiteLLM tools. The `/webhook` path has been removed; point any automation to `/ingest`.

## Quick start

1) Point OpenWebUI (or any client) to POST to `/ingest` on the ingestion service:
```
curl -X POST http://localhost:54322/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"openwebui","user_id":"alice","text":"hello","metadata":{}}'
```
Env vars (ingest service):
- `HIPPOCAMPUS_URL` (default `http://localhost:54321`)
- `HIPPOCAMPUS_API_KEY` (optional header if Hippocampus auth is enabled)

## Notes
- Hippocampus must be reachable at `HIPPOCAMPUS_URL` (defaults to
  `http://localhost:54321`).
- If your OpenWebUI build lacks webhook support, proxy via any automation that
  posts the same payload to `/ingest` after each user message.
