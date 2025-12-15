#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -z "${VIRTUAL_ENV:-}" && -f ".venv/bin/activate" ]]; then
  # Prefer the repo's virtualenv so uvicorn/deps are available.
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

if ! command -v uvicorn >/dev/null 2>&1; then
  echo "uvicorn is not installed. Activate your virtualenv and run 'pip install -r requirements.txt'." >&2
  exit 1
fi

export HIPPOCAMPUS_CONFIG=${HIPPOCAMPUS_CONFIG:-config/hippocampus.toml}

exec python -m uvicorn brain.hippocampus.app:app \
  --host 0.0.0.0 \
  --port 54321 \
  --reload
