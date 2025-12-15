# Matrix Mention Bot (`matrix-nio`)

Legacy mention/DM bot. It now supports:
- Text replies via Sacred Brain `/matrix/respond` (Sam through LiteLLM).
- Optional TTS on replies (LiteLLM `/v1/audio/speech`).
- Optional STT for received voice notes (LiteLLM `/v1/audio/transcriptions`).

## Configuration
Create `/opt/sacred-brain/.env.matrix` (or export env vars). Key vars:
```
MATRIX_HOMESERVER=https://matrix.ryer.org
MATRIX_USER=@sam:ryer.org
MATRIX_PASSWORD=...
MATRIX_MENTION=Sam
SACRED_BRAIN_URL=http://localhost:54321/matrix/respond
SACRED_BRAIN_API_KEY=...

# TTS (LiteLLM speech)
BAIBOT_TTS_ENABLED=true
BAIBOT_TTS_URL=http://127.0.0.1:4000/v1/audio/speech
BAIBOT_TTS_MODEL=gpt-4o-mini-tts
BAIBOT_TTS_VOICE=shimmer
BAIBOT_TTS_FORMAT=mp3
BAIBOT_API_KEY=

# STT (LiteLLM whisper)
BAIBOT_STT_ENABLED=true
BAIBOT_STT_URL=http://127.0.0.1:4000/v1/audio/transcriptions
BAIBOT_STT_MODEL=whisper-1
BAIBOT_STT_API_KEY=
BAIBOT_STT_TIMEOUT=20.0
```

## Running locally
```bash
cd /opt/sacred-brain
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # includes matrix-nio, httpx
python bots/matrix/mention_bot.py
```

## Systemd
1) Copy `ops/systemd/matrix-bot.service` to `/etc/systemd/system/`.
2) `sudo systemctl daemon-reload && sudo systemctl enable --now matrix-bot.service`
3) Logs: `journalctl -u matrix-bot.service -f`

## Notes / troubleshooting
- TTS requires LiteLLM speech; STT requires LiteLLM whisper and the voice note mxc to be downloadable (non-404). Element voice notes are often opus; the bot tags them as ogg for OpenAI whisper.
- If media download fails (404), check Synapse media retention/quarantine or send a fresh unencrypted voice note.
- Baibot (if used) points its agents at LiteLLM via `host.docker.internal:4000`; the mention bot calls LiteLLM directly at `127.0.0.1:4000`.
