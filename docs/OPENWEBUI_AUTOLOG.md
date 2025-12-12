# (Deprecated) OpenWebUI Auto-Logging to Hippocampus

Deprecated: use client-agnostic logging via `/ingest` (see `docs/INGEST.md`) or
LiteLLM tools. This webhook remains for compatibility but is not the recommended
path.

## Quick start

1) Run the webhook (separate from Hippocampus):
```bash
cd /opt/sacred-brain
source .venv/bin/activate
uvicorn openwebui.hippocampus_webhook:app --host 0.0.0.0 --port 54322
```
Env vars:
- `HIPPOCAMPUS_URL` (default `http://localhost:54321`)
- `HIPPOCAMPUS_API_KEY` (optional header if Hippocampus auth is enabled)

2) In OpenWebUI, configure a message webhook (if available in your build) to
POST to `http://<host>:54322/webhook` with JSON body containing the message.
Expected fields: `content` (text), plus optional `conversation_id`, `message_id`,
`user_id`/`sender`, `role`, and `metadata`.

3) Only user-role messages are logged by default; assistant messages are ignored.
Each entry stores the conversation/message IDs and sender metadata into Mem0.

## Notes
- Hippocampus must be reachable at `HIPPOCAMPUS_URL` (defaults to
  `http://localhost:54321`).
- If your OpenWebUI build lacks webhook support, you can proxy through any
  automation that posts the same payload to the webhook URL after each user
  message.
- The webhook is lightweight FastAPI; adjust the port as needed.
