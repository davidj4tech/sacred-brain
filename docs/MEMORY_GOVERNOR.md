# Memory Governor (Agno + Mem0)

Coordinator between event sources (Matrix/maubot, n8n, CLI) and Hippocampus. It applies salience and consolidation logic (Agno + Mem0 compatible) before durable writes to Hippocampus.

```
sources (maubot/n8n/CLI) -> /observe|/remember -> memory-governor
    ├─ working/store (SQLite) + optional stream log (JSONL)
    ├─ async worker + spool -> ingest -> Hippocampus -> storage
    └─ /recall -> Hippocampus query -> filtered results
```

## Endpoints
- `POST /observe` — raw events, non-blocking; dedupe by source+event_id; optionally stream log; classifies salience.
- `POST /remember` — explicit durable write (canonicalizes text).
- `POST /recall` — query Hippocampus with filters; returns curated results with provenance.
- `POST /consolidate` — summarize working memory into episodic/semantic/procedural and write high-salience items.
- `POST /promote-explain` — Dreaming: explain the scoring breakdown for a memory id. Read-only. See [DREAMING.md](DREAMING.md).
- `GET /health`

### Example payloads
```bash
# Observe (smoke)
curl -s -X POST http://127.0.0.1:54323/observe -H "Content-Type: application/json" -d '{
  "source":"smoke",
  "user_id":"alice",
  "text":"remember that my default compose is docker compose plugin syntax",
  "timestamp":1730000000000,
  "scope":{"kind":"user","id":"alice"},
  "metadata":{"event_id":"smoke-1"}
}'

# Consolidate
curl -s -X POST http://127.0.0.1:54323/consolidate -H "Content-Type: application/json" -d '{
  "scope":{"kind":"user","id":"alice"},
  "mode":"all"
}'

# Recall
curl -s -X POST http://127.0.0.1:54323/recall -H "Content-Type: application/json" -d '{
  "user_id":"alice",
  "query":"compose syntax",
  "k":5,
  "filters":{"kinds":["semantic","procedural"],"since_days":365,"min_confidence":0.2,"scope":{"kind":"user","id":"alice"}}
}'
```

## Configuration (env)
Create `/etc/memory-governor/memory-governor.env`:
```
MG_BIND_HOST=127.0.0.1
MG_PORT=54323
INGEST_URL=http://127.0.0.1:54322/ingest
HIPPOCAMPUS_URL=http://127.0.0.1:54321
HIPPOCAMPUS_API_KEY=hippo_local_a58b583f7a844f0eb3bc02e58d56f5bd
LITELLM_BASE_URL=http://127.0.0.1:4000
LITELLM_API_KEY=
MG_STREAM_ENABLE=false
MG_STREAM_TTL_DAYS=14
MG_WORKING_TTL_HOURS=24
MG_ROOMS_SCOPE=room
MG_LOG_ASSISTANT=false
MG_CONSOLIDATE_SCOPES=user:alice,!room:scope
# Mem0/Agno passthrough (optional)
MEM0_API_KEY=
MEM0_BASE_URL=
```
State directory defaults to `var/memory-governor/` under the repo; override with `MG_STATE_DIR`.

## Systemd
`ops/systemd/memory-governor.service`
- User: `memory-governor` (create and give access to `/opt/sacred-brain` + state dir)
- EnvironmentFile: `/etc/memory-governor/memory-governor.env`
- ExecStart: `/opt/sacred-brain/.venv/bin/python -m memory_governor.app`
- After: `network-online.target litellm-compose.service hippocampus.service hippocampus-ingest.service`

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now memory-governor.service
```

### Consolidation timer
`ops/systemd/memory-governor-consolidate.service` + `.timer` (hourly default).
- Reads `MG_CONSOLIDATE_SCOPES` (comma-separated kind:id). Example: `user:alice,room:!abc:server`
- Posts `/consolidate` for each scope.

Enable:
```bash
sudo systemctl enable --now memory-governor-consolidate.timer
```

## Maubot integration
- Preferred: point ingest plugin to `http://127.0.0.1:54323/observe` (instead of `/ingest`). Governor decides what is durable.
- Legacy: keep posting to `/ingest`; optionally forward from ingest service to `/observe` (not enabled by default).
- Optional: add `!remember` / `!recall` command handlers in maubot that call governor endpoints for explicit control.

## Memory kinds
- stream (raw events; optional TTL)
- working (short-term per-scope buffer)
- episodic (event snapshots)
- semantic (facts/beliefs/preferences)
- procedural (how-tos/playbooks)

## Troubleshooting
- Health: `curl http://127.0.0.1:54323/health`
- Queue backlog: check `var/memory-governor/durable.spool`
- Logs: `journalctl -u memory-governor.service -f`
- Hippocampus reachability: `curl -G -H "X-API-Key: $HIPPOCAMPUS_API_KEY" --data-urlencode 'query=test' http://127.0.0.1:54321/memories/test`

### Full pipeline health check
```bash
# 1. All three services must be running
sudo systemctl status hippocampus hippocampus-ingest memory-governor

# 2. Health endpoints
curl -s http://127.0.0.1:54321/health   # Hippocampus
curl -s http://127.0.0.1:54323/health   # Memory Governor

# 3. End-to-end write + recall test
curl -s -X POST http://127.0.0.1:54323/remember \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","text":"pipeline smoke test","source":"smoke","kind":"episodic","scope":{"kind":"global","id":"test"}}'

sleep 2

curl -s -X POST http://127.0.0.1:54323/recall \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","query":"pipeline smoke test","k":3}'
```

### Known failure modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/recall` returns empty `{"results":[]}` | Hippocampus (54321) is down | `sudo systemctl start hippocampus` |
| `/observe` or `/remember` returns 500 | State DB not writable by `memory-governor` user | `sudo chown -R memory-governor:memory-governor /opt/sacred-brain/var/memory-governor/` |
| `/remember` returns 200 but memory never appears in `/recall` | Worker not forwarding jobs to Hippocampus (check logs for write confirmation) | Check `journalctl -u memory-governor -f` for "Memory written to Hippocampus" after a `/remember` call |
| Ingest returns 200 but Hippocampus never receives POST | Hippocampus (54321) down; ingest forwards silently fail | `sudo systemctl start hippocampus` |

### Service dependency order
```
hippocampus (54321)       ← must be running first
  ↑
hippocampus-ingest (54322) ← forwards to hippocampus
  ↑
memory-governor (54323)    ← writes via ingest, queries hippocampus directly
```

Systemd `After=` in `memory-governor.service` already declares this ordering, but note that `Restart=always` on the governor does not guarantee hippocampus is healthy — only that the governor process restarts.
