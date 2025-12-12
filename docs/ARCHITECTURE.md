# Architecture

The target shape is “clients → LiteLLM gateway → providers”, with Hippocampus as
an independent memory service.

- **Clients**: Matrix bots, OpenWebUI (optional), CLI tools, and scripts.
- **Gateway (LiteLLM)**: Canonical front door for model calls; fans out to
  Ollama/Groq/OpenAI/etc. Configure OpenWebUI to use LiteLLM as its provider
  endpoint instead of talking to providers directly.
- **Providers**: Ollama, Groq, OpenAI, HF, etc. managed behind LiteLLM.
- **Memory**: Hippocampus + Mem0 adapter (independent of LiteLLM); any client
  may call `/memories` directly or via their own logging hook.

## Application Layer (`brain.hippocampus.app`)

Defines the FastAPI instance, routes, and dependency wiring. It loads
configuration, sets up logging, initialises the Mem0 adapter, and exposes the
HTTP interface consumed by external callers.

## Configuration (`brain.hippocampus.config`)

Parses TOML configuration files with environment overrides. The settings are
dataclasses that can be extended by future stories.

## Adapter (`brain.hippocampus.mem0_adapter`)

Thin abstraction on top of the Mem0 SDK. It hides SDK specifics and provides a
predictable interface for the rest of the codebase. The default deployment
assumes Mem0 is self-hosted on the same LAN (or reachable via Tailscale); if the
remote backend cannot be reached, the adapter automatically falls back to the
local in-memory store (with an optional SQLite mode when persistence is needed).

## Models (`brain.hippocampus.models`)

Pydantic schemas for requests/responses. These models keep the API surface
self-documenting and consistent with FastAPI's OpenAPI docs.

## Operations (`ops/`)

Helper scripts and systemd units for Hippocampus and the optional webhook.

## Tests (`tests/`)

`pytest` suite covering both the Mem0 adapter behaviour and the FastAPI routes.
The in-memory and SQLite adapters support deterministic testing without network calls.
