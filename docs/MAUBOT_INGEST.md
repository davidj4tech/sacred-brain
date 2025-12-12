# Maubot Ingest Plugin

Logs Matrix `m.room.message` events to the Hippocampus ingest service.

## What it does
- Listens for `m.text` messages (skips the bot’s own messages).
- POSTs to the ingest service (default `http://127.0.0.1:54322/ingest`) with:
  ```json
  {
    "source": "matrix",
    "user_id": "<sender mxid>",
    "text": "<message body>",
    "metadata": {
      "room_id": "<room>",
      "event_id": "<event>",
      "timestamp": "<event ts>",
      "displayname": "<sender display name if available>"
    }
  }
  ```
- Optional dedupe (event_id cache) to avoid duplicates on retries.
- Optional reaction ✅ on success.

## Config (`config.schema.json`)
- `ingest_url` (default `http://127.0.0.1:54322/ingest`)
- `rooms_allowlist` (optional list of room IDs; if set, only these are logged)
- `react_success` (bool, default `false`)
- `log_level` (default `INFO`)
- `cache_ttl_seconds` (default `300`)
- `cache_max_size` (default `1024`)

## Build / Upload
```bash
cd maubot/ingest
mbc build   # produces org.sacredbrain.ingest-v0.1.0.mbp
```
Upload the `.mbp` via Maubot admin UI, enable the plugin, and configure the
values above. If Maubot needs extra deps, set `MAUBOT_EXTRA_PIP_PACKAGES=httpx`
in the Maubot container (already done in our compose).

Maubot version: tested against 0.6.0; manifest pins `maubot: 0.6.0`.

## Notes
- Uses async HTTP client with a 2s timeout; logs errors but never replies in
  room on failure.
- Dedupe cache prevents repeated ingest of the same `event_id`.
> Note: When Memory Governor is enabled, point the ingest plugin to `http://127.0.0.1:54323/observe` (instead of `/ingest`) so the governor decides what becomes durable. Legacy `/ingest` remains available.

### Commands (Memory Governor)
- `!remember <text>`: forwards to Memory Governor `/remember` with scope set to the room.
- `!recall <query>`: forwards to `/recall` (defaults to semantic/procedural, top 5) and replies with bullet results.
- Configure `governor_url` (default `http://127.0.0.1:54323`) and `recall_top_k` in the plugin config.
