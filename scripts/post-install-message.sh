#!/usr/bin/env bash
# Print a friendly post-install summary. If any /etc/sacred-brain/* config
# still contains CHANGE_ME placeholders, tell the operator to edit them
# before starting services.
set -euo pipefail

ETC_DIR="${1:-/etc/sacred-brain}"

echo ""
echo "  Sacred Brain installed."
echo ""
echo "    Config: $ETC_DIR/"
echo "    State:  /var/lib/sacred-brain/"
echo "    Code:   /opt/pipx/venvs/sacred-brain-hippocampus/"
echo ""

if [[ -d "$ETC_DIR" ]] && grep -rlE 'CHANGE[_-]ME' "$ETC_DIR" >/dev/null 2>&1; then
    echo "  [!] Configs still contain CHANGE_ME placeholders. Edit them, then:"
    echo "        sudo systemctl start hippocampus memory-governor"
    echo "        sudo make install-update    # to also restart on code change"
else
    echo "  Start services:"
    echo "        sudo systemctl start hippocampus memory-governor"
fi
echo ""
