# Baibot TTS/STT

Lightweight speech helper running locally for Sam. Deployed via docker compose, bound to localhost, with secrets in `/etc/baibot/baibot.env`.

## Files
- `ops/compose/baibot/docker-compose.yml` – service definition (binds 127.0.0.1:5500).
- `ops/systemd/baibot-compose.service` – optional systemd wrapper for the compose stack.
- `/etc/baibot/baibot.env` – env file with API keys and model choices (not in repo).

## Example env file (`/etc/baibot/baibot.env`)
```
BAIBOT_BIND_HOST=0.0.0.0
BAIBOT_PORT=5500
BAIBOT_API_KEY=change-me-internal

# TTS config (uses LiteLLM/OpenAI-compatible endpoint)
BAIBOT_TTS_PROVIDER=litellm
BAIBOT_TTS_BASE_URL=http://127.0.0.1:4000
BAIBOT_TTS_MODEL=sam-fast
BAIBOT_TTS_API_KEY=

# STT config (examples: whisper large via LiteLLM/OpenAI compat)
BAIBOT_STT_PROVIDER=litellm
BAIBOT_STT_BASE_URL=http://127.0.0.1:4000
BAIBOT_STT_MODEL=whisper-1
BAIBOT_STT_API_KEY=

BAIBOT_LOG_LEVEL=INFO
```
Adjust provider/model to whatever your baibot image expects; the above assumes it can call OpenAI-compatible routes (via LiteLLM).

## Bring it up
```bash
sudo mkdir -p /etc/baibot
sudo tee /etc/baibot/baibot.env >/dev/null <<'EOF'
# (put the env values shown above here)
EOF

cd /opt/sacred-brain/ops/compose/baibot
docker compose up -d
```

Enable via systemd:
```bash
sudo cp /opt/sacred-brain/ops/systemd/baibot-compose.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now baibot-compose.service
```

## Smoke tests
Health:
```bash
curl -s http://127.0.0.1:5500/health
```

TTS (writes to a file):
```bash
curl -s -X POST http://127.0.0.1:5500/tts \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${BAIBOT_API_KEY}" \
  -d '{"text":"Testing TTS from Sam."}' \
  --output /tmp/baibot-tts.wav
```

STT (expects a wav; adjust path):
```bash
curl -s -X POST http://127.0.0.1:5500/stt \
  -H "X-API-Key: ${BAIBOT_API_KEY}" \
  -F "file=@/tmp/baibot-tts.wav"
```

## Hooking Sam
- Point Sam’s TTS calls to `http://127.0.0.1:5500/tts` and STT to `/stt`, include `X-API-Key`.
- Keep baibot bound to localhost; expose beyond that only via a trusted network (e.g., Tailscale) if you must.
- Start with small models (`sam-fast` for TTS) to avoid latency spikes. Enable richer voices/models later if needed.
