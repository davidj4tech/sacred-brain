# Logging to Hippocampus (Independent of OpenWebUI)

Use the Hippocampus HTTP API directly to log user messages or events into Mem0.
This works from any client (Matrix bots, CLIs, LiteLLM tools, etc.) without
OpenWebUI involvement.

## Endpoints
- `POST /memories` — store a memory.
- `GET /memories/{user_id}?query=...&limit=...` — search.
- `POST /summaries` — summarize a list of texts.

Base URL defaults to `http://localhost:54321`.

## Examples
Health:
```bash
curl http://localhost:54321/health
```

### cURL
```bash
curl -X POST http://localhost:54321/memories \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HIPPO_API_KEY" \
  -d '{"user_id": "alice", "text": "Met Bob today about the demo", "metadata": {"source": "cli"}}'
```

### Python snippet
```python
import httpx

resp = httpx.post(
    "http://localhost:54321/memories",
    json={
        "user_id": "alice",
        "text": "Met Bob today about the demo",
        "metadata": {"source": "cli"},
    },
    headers={"X-API-Key": "your-key"}  # omit if auth disabled
)
resp.raise_for_status()
print(resp.json())
```

## Hooking other clients
- **Matrix bots**: call `/memories` after each user message; include `room_id`,
  `event_id` in metadata.
- **LiteLLM tools**: add a simple tool that POSTs to `/memories`; call it from
  your prompts/policies.
- **OpenWebUI (optional)**: if you still want auto-logging, point its webhook to
  your own logger that POSTs to Hippocampus (the legacy webhook is deprecated;
  see note below).

## Deprecation note
The previous OpenWebUI-specific auto-logging webhook is deprecated. Prefer
calling Hippocampus directly from your client or via a LiteLLM tool hook.
