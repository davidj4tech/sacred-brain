# Bots overview

Active today
- `matrix/mention_bot.py` (matrix-nio): handles Sam replies, TTS (LiteLLM speech), and STT (LiteLLM whisper) via `matrix-bot.service`.

Future path
- `maubot/`: plugin-based bot; migrate here once verified on maubot 0.6.x and parity-tested (text, TTS, STT).

Key refs
- Env: `.env.matrix` (Matrix creds, Sacred Brain URL, LiteLLM TTS/STT settings).
- Systemd: `ops/systemd/matrix-bot.service`.
- LiteLLM: `ops/litellm/config.yaml` (models), `ops/compose/litellm` (proxy on port 4000).
