# Bots overview

Active today
- `maubot/`: plugin-based bot (mautrix) for Sam mentions, TTS, and STT in encrypted rooms.

Legacy (disabled)
- `matrix/mention_bot.py` (matrix-nio): superseded by maubot for E2EE support.

Key refs
- Env: `.env.matrix` (Matrix creds, Sacred Brain URL, LiteLLM TTS/STT settings).
- Systemd: `ops/systemd/matrix-bot.service` (legacy).
- LiteLLM: `ops/litellm/config.yaml` (models), `ops/compose/litellm` (proxy on port 4000).
