# LiteLLM Proxy (canonical gateway)

Run LiteLLM as the single front door to LLM providers. The supplied systemd unit
runs the proxy on `127.0.0.1:4000` by default.

## Install
Use the repo venv:
```bash
cd /opt/sacred-brain
source .venv/bin/activate
pip install "litellm[proxy]"
```

## Config
- Main config: `ops/litellm/config.yaml` (placeholder models/routing; edit as
  needed).
- Env files for secrets:
  - `/etc/default/litellm` (or)
  - `/etc/litellm.env`
  - Docker Compose env: `/etc/litellm/litellm.env`

Typical env vars:
```
OPENAI_API_KEY=sk-...
GROQ_API_KEY=...
# Any other provider keys as needed.
```

## Run (manual)
```bash
source /opt/sacred-brain/.venv/bin/activate
litellm --config /opt/sacred-brain/ops/litellm/config.yaml --port 4000 --host 127.0.0.1
```

## Systemd (Docker Compose)
- Compose file: `ops/compose/litellm/docker-compose.yml` (binds 127.0.0.1:4000,
  mounts `ops/litellm/config.yaml` read-only, env from `/etc/litellm/litellm.env`,
  image `ghcr.io/berriai/litellm-proxy:1.53.7`; bump tag after reviewing releases).
- Systemd unit: `ops/systemd/litellm-compose.service`.

Install/enable (as root):
```bash
sudo mkdir -p /etc/litellm
sudo touch /etc/litellm/litellm.env   # add provider keys here
sudo cp /opt/sacred-brain/ops/systemd/litellm-compose.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now litellm-compose.service
```

Sample `/etc/litellm/litellm.env`:
```
OPENAI_API_KEY=sk-...
GROQ_API_KEY=...
```
## Test
```bash
curl http://127.0.0.1:4000/v1/models
curl http://127.0.0.1:4000/health
# Chat completion example (OpenAI-compatible):
curl -X POST http://127.0.0.1:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

## Smoke checks (copy/paste)
- List models: `curl http://127.0.0.1:4000/v1/models`
- Simple chat completion:  
  `curl -X POST http://127.0.0.1:4000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Say hi"}]}'`

## Usage
- Point OpenWebUI (or any client) at `http://127.0.0.1:4000` as the OpenAI-compatible base URL.
- Keep Hippocampus independent: memory calls still go to `http://localhost:54321`.

## Quotas, keys, and logging

### Virtual keys (per-user/per-key limits)
- Use LiteLLM’s virtual key feature to issue per-user keys and set limits:
  - `litellm --config ... --virtual-keys` (or define in YAML per LiteLLM docs).
  - Map `Virtual-Key` to underlying provider keys; set per-key rate/usage limits.
- Rotation: generate a new virtual key and update clients; keep the old one valid
  briefly if you need overlap, then revoke it. No proxy restart needed if you
  manage keys via LiteLLM’s admin APIs or hot-reloadable config.

### Budgets
- Configure `max_budget` per key/user in the LiteLLM config or via admin API.
- Recommended default: set a low global max (e.g., daily/weekly) and raise only
  for trusted keys.
- Track spend with LiteLLM’s built-in usage accounting; alert or throttle on
  budget exhaustion.

### Logging
- Enable LiteLLM request/response logging (e.g., `general_settings.request_logging: true`)
  and rotate logs via systemd logrotate or an external collector.
- Keep PII out of logs; prefer redaction or minimal request metadata.

### Key rotation without downtime
- Keep `litellm` running; update virtual keys/budgets via:
  - Admin API (preferred) or
  - Hot-reloadable config + SIGHUP/reload (if supported in your setup).
- Update clients with the new key, then revoke the old one once migrated.
