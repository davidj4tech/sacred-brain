# Architecture

The hippocampus service is intentionally small and decomposed into a few clear
components:

## Application Layer (`brain.hippocampus.app`)

Defines the FastAPI instance, routes, and dependency wiring. It loads
configuration, sets up logging, initialises the Mem0 adapter, and exposes the
HTTP interface consumed by external callers.

## Configuration (`brain.hippocampus.config`)

Parses TOML configuration files with environment overrides. The settings are
Dataclasses that can be easily extended by future stories.

## Adapter (`brain.hippocampus.mem0_adapter`)

Thin abstraction on top of the Mem0 SDK. It hides SDK specifics and provides a
predictable interface for the rest of the codebase. If a real Mem0 client is not
available, it falls back to a SQLite-backed persistent store (or an optional in-memory
implementation) that powers development and tests.

## Models (`brain.hippocampus.models`)

Pydantic schemas for requests/responses. These models help keep the API surface
self-documenting and consistent with FastAPI's OpenAPI docs.

## Operations (`ops/`)

A helper `dev_run.sh` script and a sample `systemd` unit file are provided for
local and Raspberry Pi deployments.

## Tests (`tests/`)

`pytest` suite covering both the Mem0 adapter behaviour and the FastAPI routes.
The in-memory and SQLite adapters support deterministic testing without network calls.
