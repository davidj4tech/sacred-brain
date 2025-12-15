# OpenWebUI Integration – Hippocampus Tool (Optional)

OpenWebUI is optional. When used, it should point at the LiteLLM gateway for
model calls, and call Hippocampus only for memory actions.

## Files
- `openwebui-tool-hippocampus.json` – tool definition with actions:
  - `create` → POST `/memories`
  - `query` → GET `/memories/{user_id}?query=...&limit=...`
  - `summarize` → POST `/summaries`

## Import steps (UI)
1. Start Hippocampus: `source .venv/bin/activate && uvicorn brain.hippocampus.app:app --host 0.0.0.0 --port 54321`
2. In OpenWebUI, go to **Tools** → **Import**, select `openwebui-tool-hippocampus.json`.
3. Configure base URL: `http://localhost:54321` (or your host).
4. If auth is enabled in Hippocampus, set the HTTP header `X-API-Key: <your key>` in the tool config.
5. Configure OpenWebUI’s model provider to use the LiteLLM proxy
   (`http://localhost:4000`) rather than providers directly, per `docs/LITELLM_GATEWAY.md`.

## Import steps (filesystem)
If you prefer file-based loading, copy the tool schema into your OpenWebUI tools
directory, e.g.:
```bash
cp openwebui-tool-hippocampus.json /srv/open-webui-main/tools/hippocampus.json
```
Restart OpenWebUI if required so it rescans tools.

## Usage hints
- Always provide `user_id` for `create` and `query`.
- `metadata` is optional on create.
- `limit` caps results on query (defaults to 5).
- `summarize` accepts `texts` (array of strings) and returns a compact summary.
