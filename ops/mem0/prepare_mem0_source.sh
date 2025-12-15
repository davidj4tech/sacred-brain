#!/usr/bin/env bash
# Clone or update the official Mem0 repository under ext/mem0, then print usage.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_DIR="${ROOT_DIR}/ext/mem0"
REPO_URL="${MEM0_REPO_URL:-https://github.com/mem0ai/mem0.git}"

if [[ -d "${TARGET_DIR}/.git" ]]; then
  printf "Updating existing Mem0 clone at %s\n" "${TARGET_DIR}"
  git -C "${TARGET_DIR}" fetch --tags origin
  git -C "${TARGET_DIR}" pull --ff-only
else
  printf "Cloning Mem0 into %s\n" "${TARGET_DIR}"
  git clone "${REPO_URL}" "${TARGET_DIR}"
fi

cat <<EOF
Mem0 source ready at ${TARGET_DIR}.
To launch the upstream stack:

  cd ${TARGET_DIR}/server
  cp .env.example .env   # edit OPENAI_API_KEY and other settings
  OPENAI_API_KEY=sk-yourkey docker compose up -d

This will start Mem0 plus its Postgres/Neo4j dependencies on port 8888.
Refer to docs/MEM0_SELF_HOSTING.md for full instructions.
EOF
