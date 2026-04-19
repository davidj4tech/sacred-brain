#!/usr/bin/env bash
# install.sh — per-machine installer for the Codex bridge.
#
# Symlinks governor_context.sh, codex-with-governor, and _outcome_drain.sh
# into ~/.local/bin so the launcher wrapper is usable as `codex-with-governor`
# (and users can optionally alias `codex` to it in their shell rc).
#
# Codex's hook API isn't stable, so this installer does NOT splice anything
# into a Codex config file. See docs/CODEX_BRIDGE.md.
#
# Idempotent — safe to re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
SCRIPTS=(governor_context.sh codex-with-governor _outcome_drain.sh)

mkdir -p "$BIN_DIR"
for s in "${SCRIPTS[@]}"; do
  src="$REPO_ROOT/scripts/$s"
  dst="$BIN_DIR/$s"
  if [[ ! -e "$src" ]]; then
    echo "install.sh: missing $src" >&2
    exit 1
  fi
  if [[ ! -x "$src" && "$s" != _* ]]; then
    chmod +x "$src"
  fi
  ln -sf "$src" "$dst"
  echo "linked $dst -> $src"
done

cat <<EOF

Next steps:
  1. Set GOVERNOR_URL and GOVERNOR_USER_ID in ~/.config/hippocampus.env
     (or in your shell profile). See docs/CODEX_BRIDGE.md.
  2. On a non-homer machine, point GOVERNOR_URL at homer via Tailscale:
       export GOVERNOR_URL=http://100.125.48.108:54323
  3. Either:
       a. Invoke 'codex-with-governor' instead of 'codex', OR
       b. Add to your shell rc:  alias codex=codex-with-governor
EOF
