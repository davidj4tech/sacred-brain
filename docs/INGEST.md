# Hippocampus Ingestion Service

Generic HTTP ingestion endpoint to log events/messages into Hippocampus, without
tying to a specific client. Route:
- `POST /ingest` – simple, client-agnostic payload.

## Payloads

### /ingest
```json
{
  "source": "matrix",
  "user_id": "alice",
  "text": "Met Bob today about the demo",
  "timestamp": "2025-01-10T12:34:56Z",
  "metadata": {
    "room_id": "!abc:example.org",
    "event_id": "$xyz"
  }
}
```

## Running

```bash
cd /opt/sacred-brain
source .venv/bin/activate
uvicorn ingest.hippocampus_ingest:app --host 0.0.0.0 --port 54322
```

Env vars:
- `HIPPOCAMPUS_URL` (default `http://localhost:54321`)
- `HIPPOCAMPUS_API_KEY` (optional auth header)

## Examples

Matrix/n8n/CLI can all POST to `/ingest`:
```bash
curl -X POST http://localhost:54322/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"matrix","user_id":"alice","text":"demo note","metadata":{"room_id":"!abc"}}'
```

## Systemd

Use a systemd unit pointing to `ingest.hippocampus_ingest:app`. Set the port and env vars as
needed; see README or existing unit examples for pattern.
