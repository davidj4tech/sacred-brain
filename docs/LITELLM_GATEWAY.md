# LiteLLM Gateway (Canonical Path)

All client LLM traffic should flow through LiteLLM as the single gateway to
providers (Ollama, Groq, OpenAI, etc.). OpenWebUI is optional and should be
configured to point at LiteLLM rather than providers directly.

## Minimal LiteLLM setup
Example using the LiteLLM proxy:
```bash
pip install litellm[proxy]
export LITELLM_PROXY_PORT=4000           # choose your port
export LITELLM_LOG=info
# provider keys as needed, e.g.:
# export OPENAI_API_KEY=sk-...
# export GROQ_API_KEY=...
litellm --config configs/litellm.yaml    # supply a provider routing config
```

Example `configs/litellm.yaml`:
```yaml
model_list:
  - model_name: "gpt-4o-mini"
    litellm_params:
      model: "openai/gpt-4o-mini"
  - model_name: "llama3-8b"
    litellm_params:
      model: "groq/llama3-8b-8192"
  - model_name: "ollama:llama3"
    litellm_params:
      model: "ollama/llama3"
      api_base: "http://localhost:11434"
```

Run the proxy, then use the OpenAI-compatible endpoint:
```
base_url = http://localhost:4000
```

## OpenWebUI configuration (optional)
- Set OpenWebUI’s provider base URL to the LiteLLM proxy (e.g.,
  `http://host.docker.internal:4000`).
- Do not point OpenWebUI directly at Groq/Ollama/etc.; keep LiteLLM as the
  single gateway so routing/policy stays centralized.

## Hippocampus remains independent
Hippocampus (memory API) is not behind LiteLLM; clients call it directly:
`http://localhost:54321/memories` et al. Use your client’s logging hooks to send
memories; see `docs/LOGGING_TO_HIPPOCAMPUS.md`.
