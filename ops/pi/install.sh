#!/usr/bin/env bash
# install.sh — per-machine installer for the Pi bridge.
#
# Symlinks extensions/pi-bridge.ts into ~/.pi/agent/extensions/, where pi
# auto-discovers it on session start. Pi exposes a typed extension API
# rather than a shell-hook config slot, so the bridge is a TS module
# (loaded via pi's bundled jiti — no compilation step needed).
#
# Idempotent — safe to re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EXT_DIR="${HOME}/.pi/agent/extensions"
SRC="$REPO_ROOT/extensions/pi-bridge.ts"
DST="$EXT_DIR/sacred-brain-bridge.ts"

if [[ ! -f "$SRC" ]]; then
  echo "install.sh: missing $SRC" >&2
  exit 1
fi

mkdir -p "$EXT_DIR"
ln -sf "$SRC" "$DST"
echo "linked $DST -> $SRC"

cat <<EOF

Next steps:
  1. Set GOVERNOR_URL and GOVERNOR_USER_ID in ~/.config/hippocampus.env
     (or in your shell profile). See docs/PI_BRIDGE.md.
  2. On a non-homer machine, point GOVERNOR_URL at homer via Tailscale:
       GOVERNOR_URL=http://100.125.48.108:54323
  3. Reload pi (or start a new session). The extension will fire
     session_start, before_agent_start, session_before_compact, and
     session_shutdown automatically.

To disable temporarily:  PI_BRIDGE_DISABLE=1 pi
To skip system-prompt injection (file-only mode):  PI_BRIDGE_INJECT=0 pi
EOF
