#!/usr/bin/env bash
# install_hooks.sh — per-machine installer for the Claude Code bridge.
#
# Installs governor_context.sh and governor_precompact.sh into ~/.local/bin
# (as symlinks to the repo copies, so updates propagate with a git pull) and
# splices SessionStart + PreCompact entries into ~/.claude/settings.json.
# Idempotent — safe to re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
SETTINGS="${HOME}/.claude/settings.json"
SCRIPTS=(governor_context.sh governor_precompact.sh)

if ! command -v jq >/dev/null 2>&1; then
  echo "install_hooks.sh: jq is required" >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
for s in "${SCRIPTS[@]}"; do
  src="$REPO_ROOT/scripts/$s"
  dst="$BIN_DIR/$s"
  if [[ ! -x "$src" ]]; then
    chmod +x "$src"
  fi
  ln -sf "$src" "$dst"
  echo "linked $dst -> $src"
done

mkdir -p "$(dirname "$SETTINGS")"
if [[ ! -f "$SETTINGS" ]]; then
  echo "{}" > "$SETTINGS"
fi
if ! jq -e . "$SETTINGS" >/dev/null 2>&1; then
  echo "install_hooks.sh: $SETTINGS is not valid JSON; refusing to edit" >&2
  exit 1
fi

tmp="$(mktemp)"
jq --arg ctx "$BIN_DIR/governor_context.sh --target claude" \
   --arg pre "$BIN_DIR/governor_precompact.sh" '
  .hooks //= {}
  | .hooks.SessionStart = (
      (.hooks.SessionStart // [])
      | map(select(.hooks // [] | any(.command != $ctx)))
      | . + [{"matcher": "", "hooks": [{"type": "command", "command": $ctx}]}]
    )
  | .hooks.PreCompact = (
      (.hooks.PreCompact // [])
      | map(select(.hooks // [] | any(.command != $pre)))
      | . + [{"matcher": "", "hooks": [{"type": "command", "command": $pre}]}]
    )
' "$SETTINGS" > "$tmp"

mv "$tmp" "$SETTINGS"
echo "updated $SETTINGS"

cat <<EOF

Next steps:
  1. Set GOVERNOR_URL and GOVERNOR_USER_ID in ~/.config/hippocampus.env
     (or in your shell profile). See docs/CLAUDE_CODE_BRIDGE.md.
  2. On a non-homer machine, point GOVERNOR_URL at homer via Tailscale:
       export GOVERNOR_URL=http://100.125.48.108:54323
  3. Open a new Claude Code session to trigger SessionStart.
EOF
