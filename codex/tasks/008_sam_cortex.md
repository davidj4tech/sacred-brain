## Task 008: Sam Cortex (LLM-backed responses)

Goals
- Add an LLM-backed “cortex” so Sam can generate responses and lightweight relevance judgments.
- Keep it minimal, swappable, and safe (feature-flagged).

Status
- [x] Add LLM client module (LiteLLM/OpenAI-compatible) with env loader.
- [x] Add Sam system prompt file.
- [x] Extend config with Sam LLM/reflection settings + env overrides.
- [ ] Wire LLM into response pipeline (memory pack, fallback message).
- [ ] Add tests for LLM enabled/disabled, reflection behavior, fallback.
- [ ] Add README/docs snippet for tuning and how to point at LiteLLM.
- [ ] Optional health/doctor check for LiteLLM reachability.

Notes
- Current defaults: LLM enabled=true, base_url=http://127.0.0.1:4000, model=gpt-4o-mini, reflection enabled=true.
- Reflection currently deterministic; rerank is optional/independent.
