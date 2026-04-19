# shellcheck shell=sh
# _outcome_drain.sh — shared helper for draining pending-outcome files.
#
# Source this, then call `drain_outcomes <filename>`. The file lives under
# ~/.cache/sacred-brain/. Each line is a JSON object matching the Governor's
# /outcome request body. Posted lines are removed; unposted lines are kept
# (so a transient network failure doesn't discard queued outcomes).

drain_outcomes() {
  _fname="$1"
  [ -n "$_fname" ] || return 0
  _dir="${HOME}/.cache/sacred-brain"
  _path="${_dir}/${_fname}"
  [ -r "$_path" ] || return 0
  [ -s "$_path" ] || return 0

  _log="${_dir}/claude-bridge.log"
  mkdir -p "$_dir"

  # Source env (same rule as the other scripts)
  for _f in "$HOME/.config/hippocampus.env" "$HOME/.config/sacred-brain.env"; do
    if [ -r "$_f" ]; then
      # shellcheck disable=SC1090
      . "$_f"
      break
    fi
  done
  _url="${GOVERNOR_URL:-${HIPPOCAMPUS_URL:-http://127.0.0.1:54323}}"
  _key="${GOVERNOR_API_KEY:-${HIPPOCAMPUS_API_KEY:-}}"

  _tmp="$(mktemp)"
  _posted=0
  _failed=0
  while IFS= read -r _line; do
    [ -z "$_line" ] && continue
    _hdrs='-H "Content-Type: application/json"'
    if [ -n "$_key" ]; then
      if curl -sS --max-time 3 \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $_key" \
        -X POST "$_url/outcome" -d "$_line" >/dev/null 2>&1; then
        _posted=$((_posted+1))
      else
        printf '%s\n' "$_line" >> "$_tmp"
        _failed=$((_failed+1))
      fi
    else
      if curl -sS --max-time 3 \
        -H "Content-Type: application/json" \
        -X POST "$_url/outcome" -d "$_line" >/dev/null 2>&1; then
        _posted=$((_posted+1))
      else
        printf '%s\n' "$_line" >> "$_tmp"
        _failed=$((_failed+1))
      fi
    fi
  done < "$_path"

  mv "$_tmp" "$_path"
  printf '%s drain(%s): posted=%d failed=%d\n' \
    "$(date -Iseconds)" "$_fname" "$_posted" "$_failed" >> "$_log"
}
