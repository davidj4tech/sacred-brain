# Stack at a glance

- Matrix bot: `bots/matrix/mention_bot.py` (matrix-nio), managed by `matrix-bot.service`. Optional TTS/STT via LiteLLM.
- Hippocampus: `brain/hippocampus/app.py`, config `config/hippocampus.toml`, serves `/matrix/respond` for Sam.
- Sam pipeline: `sacred_brain/sam_pipeline.py`, `sacred_brain/llm_client.py`, routing in `sacred_brain/routing.py`.
- LiteLLM proxy: `ops/litellm/config.yaml`, compose in `ops/compose/litellm` (port 4000). Models include `sam-*`, `gpt-4o-mini-tts`, `whisper-1`.
- Baibot: `ops/compose/baibot/config.yml` (agents point to LiteLLM at `host.docker.internal:4000`); mainly for Matrix-side persona, not required for the nio bot.

Ports (local)
- LiteLLM: 4000
- Hippocampus: 54321
- Baibot: 5500 (HTTP, not used for TTS now)

Notes
- TTS: LiteLLM `/v1/audio/speech` using `gpt-4o-mini-tts` (voice shimmer).
- STT: LiteLLM `/v1/audio/transcriptions` using `whisper-1`; requires the voice note mxc to download (404s mean missing media/quarantine).
- Keep `matrix-bot.service` running until maubot migration is complete and parity-tested.
