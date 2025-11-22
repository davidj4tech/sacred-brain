# Codex Operating Instructions

## Initial Spec
- Build a Raspberry Pi-friendly FastAPI microservice called `hippocampus`.
- Provide REST endpoints for storing, querying, summarizing, and deleting memories using Mem0 with an in-memory fallback.
- Ship runnable code, docs, tests, and minimal ops scaffolding (systemd service + dev script).
- Keep code rooted under `brain/hippocampus/` with supporting tests/docs/config.

## Implemented Baseline (per SESSION_LOG.md)
- FastAPI app exposes `/health`, `/memories` (POST/GET), `/memories/{memory_id}` DELETE, and `/summaries`.
- Config loader, logging configuration, Mem0 adapter with automatic in-memory fallback, and Pydantic I/O models exist.
- Tooling: repo metadata, `config/hippocampus.toml`, ops scripts, and pytest suite (6 tests passing).
- Docs: architecture overview, API contract, README quickstart.

## Outstanding Directions
1. Integrate with the official Mem0 SDK and map delete/query semantics to its live API.
2. Add authentication/authorization support for multi-tenant deployments.
3. Ship persistence beyond in-memory fallback (file/db) for offline mode.
4. Enhance summarization via an external LLM-backed service.

## Workflow for Future Codex Tasks
1. Read `SESSION_LOG.md` and `codex/tasks/` to understand context and queued work.
2. Select or author a task file (see `codex/tasks/README.md` for the schema) that moves one Outstanding Direction forward.
3. Implement code/doc/test changes without regressing existing functionality.
4. Update the session log if major milestones are reached and mark tasks as done when merged.

## Task Artifacts
- Task files live in `codex/tasks/` and should follow the format documented in `codex/tasks/README.md`.
- Keep task names sequential (e.g., `001_mem0_sdk.md`) so progress is easy to track.
- Each task should end with clear validation steps and references to affected files or docs.
