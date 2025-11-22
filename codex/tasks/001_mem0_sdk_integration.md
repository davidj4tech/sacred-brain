# Task: Integrate official Mem0 SDK for persistence

## Context
The current adapter wraps Mem0 behavior manually and falls back to an in-memory store. SESSION_LOG.md lists "Integrate with the official Mem0 SDK" as the top outstanding direction so that the public API matches the live service semantics.

## Goal
Adopt the real Mem0 Python SDK for create/query/delete/summarize operations while preserving the in-memory fallback for offline mode.

## Requirements
- Add the official Mem0 SDK dependency (pin a version) and load credentials/config from `HIPPOCAMPUS_CONFIG` or env vars.
- Extend `brain/hippocampus/adapters/memories.py` (or the appropriate adapter module) to delegate to the SDK when configured, falling back to the current in-memory pathway when the SDK is unavailable or misconfigured.
- Align API semantics with Mem0 responses (IDs, error handling, pagination) without breaking existing request/response models.
- Update docs (`docs/API.md`, README) to describe configuration knobs and expected behavior when Mem0 cloud is enabled/disabled.
- Ensure existing tests keep passing and add targeted tests that mock the SDK to exercise the new branch of logic.

## Suggested Steps
1. Research the Mem0 SDK usage patterns (auth, client creation, CRUD calls) and document any assumptions inside the adapter.
2. Add the dependency to `pyproject.toml`/`requirements.txt` and gate import errors gracefully.
3. Refactor the adapter to instantiate a Mem0 client if credentials/config are provided; otherwise fall back to the current in-memory backend.
4. Mirror create/query/delete calls through the SDK while keeping summaries functional (call SDK summaries or continue using local logic if unavailable).
5. Expand tests using dependency injection or mocking to validate both SDK-enabled and fallback code paths.
6. Refresh docs to instruct operators how to configure Mem0 access and what happens when it is offline.

## Validation
- `pytest` returns green (existing suite plus any new tests).
- Manual smoke: run `uvicorn` locally with Mem0 config enabled and confirmed POST/GET/DELETE flows hitting the SDK (can rely on mocked/stubbed client if live service is unavailable).
- Manual smoke: run without Mem0 config and verify fallback still works.

## References
- SESSION_LOG.md (Outstanding Directions section).
- `brain/hippocampus/adapters/` modules for current memory handling.
- `docs/API.md`, README for operator-facing updates.
