# Task: Script Mem0 self-host setup (Pi-friendly)

## Context
The adapter now prefers a self-hosted Mem0 backend but we lack ready-made scripts or guidance for operators to run Mem0 on the same Raspberry Pi (or nearby node) alongside Hippocampus. We also need a way to prove the remote client takes over from the in-memory fallback once Mem0 is online.

## Goal
Provide scripts/docs (systemd and docker-compose options) to boot a local Mem0 instance, wire Hippocampus environment variables, and validate the remote client is serving requests instead of the fallback.

## Requirements
- Deliver `scripts/selfhost_mem0_setup.md` (or similar) that documents two deployment paths:
  - systemd service definition suitable for Raspberry Pi/ARM.
  - docker-compose stack (Pi-compatible base image).
- Include environment variable examples for both Mem0 and Hippocampus (`mem0.enabled`, `backend=remote`, `backend_url`, API keys if needed).
- Describe health check commands (curl/HTTP) to confirm Mem0 is reachable before pointing Hippocampus at it.
- Document a verification procedure that proves Hippocampus is using the remote client (e.g., disable Mem0 to confirm fallback, re-enable to see remote responses, inspect logs).

## Suggested Steps
1. Research Mem0’s self-host install requirements (dependencies, ports, data dirs) and capture them in the doc.
2. Write the docker-compose example with persistent volumes and relevant env vars.
3. Provide a systemd unit sample referencing a shell script or binary, including ExecStart, Restart, and Environment lines.
4. Document Hippocampus env configuration snippets showing how to point to localhost/Tailscale IP.
5. Add curl-based health checks for Mem0 and sample API calls to Hippocampus before/after remote enablement.
6. Outline troubleshooting tips (logs, fallback detection).

## Validation
- Reviewers can follow the doc to start Mem0 via docker-compose and systemd.
- `curl http://<mem0-host>:7700/health` succeeds per instructions.
- Hippocampus logs show remote backend usage once Mem0 is up, and tests confirm fallback when it is stopped.

## References
- `README.md` (configuration section).
- `brain/hippocampus/mem0_adapter.py` for remote/fallback behaviour.
- `config/hippocampus.toml` for default knobs.
