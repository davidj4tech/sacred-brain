# Docker Baseline

## Intent
- Docker runs app services; Compose is the source of truth.
- UFW should not police Docker internals.

## Norms
- Validate configs before deploy:
  `docker compose config && docker compose up -d`
- Prefer healthchecks + restart policies to “it’ll be fine”.
- Avoid crash-loop storms; use limits on AI-heavy services.

## Useful commands
- Containers: `docker ps -a`
- Restart counts: (inspect loop)
- Health: `docker inspect <name> --format '{{json .State.Health}}' | jq`

## Notes
- Multiple bridge networks are normal.
- If SSH/Tailscale flaky but nginx works → suspect restart storm / network churn.

