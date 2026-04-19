#!/usr/bin/env bash
# governor_precompact.sh — called by Claude Code's PreCompact hook.
#
# Reads the transcript path from the hook's JSON input on stdin and POSTs
# the last ~2000 words to the Governor's /observe endpoint so salient
# details survive compaction. Logs to ~/.cache/sacred-brain/claude-bridge.log
# and never fails loudly — compaction must proceed regardless.

set -u

LOG_DIR="${HOME}/.cache/sacred-brain"
LOG="${LOG_DIR}/claude-bridge.log"
mkdir -p "$LOG_DIR"

log() { printf '%s precompact: %s\n' "$(date -Iseconds)" "$*" >> "$LOG"; }

for f in "$HOME/.config/hippocampus.env" "$HOME/.config/sacred-brain.env"; do
  if [[ -r "$f" ]]; then
    set -a; . "$f"; set +a
    break
  fi
done

GOVERNOR_URL="${GOVERNOR_URL:-${HIPPOCAMPUS_URL:-http://127.0.0.1:54323}}"
API_KEY="${GOVERNOR_API_KEY:-${HIPPOCAMPUS_API_KEY:-}}"
USER_ID="${GOVERNOR_USER_ID:-sam}"
PROJECT="$(basename "$PWD")"

# Hook input: either a JSON object on stdin, or CLAUDE_TRANSCRIPT env, or $1
TRANSCRIPT=""
if [[ -n "${CLAUDE_TRANSCRIPT:-}" ]]; then
  TRANSCRIPT="$CLAUDE_TRANSCRIPT"
elif [[ $# -ge 1 && -r "$1" ]]; then
  TRANSCRIPT="$1"
else
  HOOK_JSON="$(cat || true)"
  if [[ -n "$HOOK_JSON" ]]; then
    TRANSCRIPT="$(printf '%s' "$HOOK_JSON" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get("transcript_path") or d.get("transcript") or "")
except Exception:
    pass' 2>/dev/null)"
  fi
fi

if [[ -z "$TRANSCRIPT" || ! -r "$TRANSCRIPT" ]]; then
  log "no readable transcript (arg=$*, env=${CLAUDE_TRANSCRIPT:-}); exit 0"
  exit 0
fi

# Take the last ~2000 words as the observe payload
TAIL_TEXT="$(tr -s '[:space:]' ' ' < "$TRANSCRIPT" | awk '{
  n=split($0, w, " ");
  start = n - 2000; if (start < 1) start = 1;
  for (i=start; i<=n; i++) printf "%s ", w[i];
}')"
if [[ -z "${TAIL_TEXT// /}" ]]; then
  log "transcript empty after extraction; exit 0"
  exit 0
fi

export USER_ID PROJECT

BODY="$(python3 -c '
import json, os, sys
user = os.environ["USER_ID"]
project = os.environ["PROJECT"]
text = sys.stdin.read()
print(json.dumps({
    "source": "claude-code:precompact",
    "user_id": user,
    "text": text,
    "scope": {
        "kind": "project", "id": project,
        "parent": {"kind": "user", "id": user, "parent": None},
    },
    "metadata": {"origin": "claude-code", "event": "precompact"},
}))
' <<< "$TAIL_TEXT")" || { log "body build failed"; exit 0; }

HDRS=(-H "Content-Type: application/json")
[[ -n "$API_KEY" ]] && HDRS+=(-H "X-API-Key: $API_KEY")

if curl -sS --max-time 3 "${HDRS[@]}" -X POST "$GOVERNOR_URL/observe" -d "$BODY" >/dev/null 2>&1; then
  log "posted tail (${#TAIL_TEXT} bytes) for project=$PROJECT user=$USER_ID"
else
  log "POST /observe failed (non-fatal)"
fi

exit 0
