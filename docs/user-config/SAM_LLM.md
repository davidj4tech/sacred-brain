# Sam LLM setup

- Enable: `SAM_LLM_ENABLED=true` (env). Base URL defaults to `http://127.0.0.1:4000` (LiteLLM). Model default `gpt-4o-mini`.
- Optional: `SAM_LLM_API_KEY` if LiteLLM enforces auth.
- Temperature/top-p defaults: `SAM_LLM_TEMPERATURE=0.5`, `SAM_LLM_TOP_P=0.9`.
- Reflection toggle: `SAM_REFLECTION_ENABLED` (currently integrated in the governor reflection path).
- Memory packing: max context = `SAM_MEMORY_CONTEXT_MAX` (default 3), candidates = `SAM_MEMORY_CANDIDATES_MAX` (default 8).
- Fallback: if disabled or call fails, reply is a deterministic message about LLM not attached.
- System prompt lives in `sacred_brain/prompts/sam_system.txt`; adjust tone/rules there.

To point at LiteLLM: ensure LiteLLM is running on 127.0.0.1:4000 and set `SAM_LLM_MODEL` to a served model ID.

For direct providers with per-endpoint model IDs, set `SAM_LLM_MODEL_MAP` to a JSON map of
`base_url` → `model` (example: `{"https://llm.ryer.org/v1":"/content/models/deepseek.gguf"}`).
