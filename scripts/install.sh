#!/usr/bin/env bash
set -euo pipefail

# Sacred Brain installer
# Clone the repo, edit the config templates, then run this script.
#
# Usage:
#   sudo ./scripts/install.sh          # full install
#   sudo ./scripts/install.sh --update # update systemd units only (no user/dir/config creation)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYSTEMD_DIR="$REPO_DIR/ops/systemd"
CONFIG_DIR="$REPO_DIR/ops/config"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { echo "  [+] $*"; }
warn()  { echo "  [!] $*" >&2; }
die()   { echo "  [ERROR] $*" >&2; exit 1; }

# ── Pre-flight checks ───────────────────────────────────────────────

[[ $EUID -eq 0 ]] || die "Must run as root (sudo)"
[[ -d "$SYSTEMD_DIR" ]] || die "ops/systemd/ not found — run from repo root"

UPDATE_ONLY=false
if [[ "${1:-}" == "--update" ]]; then
    UPDATE_ONLY=true
    info "Update mode: refreshing systemd units only"
fi

# ── Phase 1: Service user ───────────────────────────────────────────

if [[ "$UPDATE_ONLY" == false ]]; then
    if id sacred &>/dev/null; then
        info "User 'sacred' already exists"
    else
        info "Creating service user 'sacred'"
        useradd --system --shell /usr/sbin/nologin --home-dir /opt/sacred-brain sacred
    fi
fi

# ── Phase 2: FHS directories ────────────────────────────────────────

if [[ "$UPDATE_ONLY" == false ]]; then
    info "Creating state directories"
    mkdir -p /var/lib/sacred-brain/hippocampus
    mkdir -p /var/lib/sacred-brain/governor
    mkdir -p /var/lib/sacred-brain/cache
    chown -R sacred:sacred /var/lib/sacred-brain

    info "Creating config directory"
    mkdir -p /etc/sacred-brain
    chown sacred:sacred /etc/sacred-brain
fi

# ── Phase 3: Configuration ──────────────────────────────────────────

if [[ "$UPDATE_ONLY" == false ]]; then
    for tmpl in hippocampus.toml.example hippocampus.env.example memory-governor.env.example; do
        target="/etc/sacred-brain/${tmpl%.example}"
        if [[ -f "$target" ]]; then
            info "Config exists, skipping: $target"
        else
            if [[ -f "$CONFIG_DIR/$tmpl" ]]; then
                cp "$CONFIG_DIR/$tmpl" "$target"
                chown sacred:sacred "$target"
                chmod 640 "$target"
                warn "Created $target from template — edit CHANGE_ME values!"
            else
                warn "Template not found: $CONFIG_DIR/$tmpl"
            fi
        fi
    done
fi

# ── Phase 4: Python venv ────────────────────────────────────────────

if [[ "$UPDATE_ONLY" == false ]]; then
    if [[ ! -d "$REPO_DIR/.venv" ]]; then
        info "Creating Python venv"
        python3 -m venv "$REPO_DIR/.venv"
        "$REPO_DIR/.venv/bin/pip" install --upgrade pip
    fi

    if [[ -f "$REPO_DIR/pyproject.toml" ]]; then
        info "Installing Python dependencies"
        "$REPO_DIR/.venv/bin/pip" install -e "$REPO_DIR" 2>/dev/null \
            || "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt" 2>/dev/null \
            || warn "No installable package or requirements.txt found — install deps manually"
    fi
fi

# ── Phase 5: Systemd units ──────────────────────────────────────────

# Core services and timers (always installed)
CORE_UNITS=(
    hippocampus.service
    hippocampus-auto-prune.service
    hippocampus-auto-prune.timer
    hippocampus-auto-tune.service
    hippocampus-auto-tune.timer
    hippocampus-notes-export.service
    hippocampus-notes-export.timer
    hippocampus-notes-import.service
    hippocampus-notes-import.timer
    memory-governor.service
    memory-governor-consolidate.service
    memory-governor-consolidate.timer
)

# Optional units (only installed if present in ops/systemd/)
OPTIONAL_UNITS=(
    governor-digest.service
    governor-digest.timer
    hippocampus-memory-sync.service
    hippocampus-memory-sync.timer
)

info "Installing systemd units"
for unit in "${CORE_UNITS[@]}" "${OPTIONAL_UNITS[@]}"; do
    src="$SYSTEMD_DIR/$unit"
    if [[ -f "$src" ]]; then
        cp "$src" "/etc/systemd/system/$unit"
        info "  $unit"
    fi
done

systemctl daemon-reload

# ── Phase 6: Enable services and timers ──────────────────────────────

info "Enabling core services"
systemctl enable hippocampus.service memory-governor.service 2>/dev/null

info "Enabling timers"
for timer in hippocampus-auto-prune.timer hippocampus-auto-tune.timer \
             hippocampus-notes-export.timer hippocampus-notes-import.timer \
             memory-governor-consolidate.timer; do
    systemctl enable "$timer" 2>/dev/null
done

# Enable optional timers if their unit files exist
for timer in governor-digest.timer hippocampus-memory-sync.timer; do
    if [[ -f "/etc/systemd/system/$timer" ]]; then
        systemctl enable "$timer" 2>/dev/null
        info "  (optional) $timer"
    fi
done

# ── Phase 7: Start ──────────────────────────────────────────────────

if [[ "$UPDATE_ONLY" == false ]]; then
    info "Starting services"
    systemctl start hippocampus.service
    sleep 2
    systemctl start memory-governor.service
    sleep 2

    info "Starting timers"
    systemctl start hippocampus-auto-prune.timer
    systemctl start hippocampus-auto-tune.timer
    systemctl start hippocampus-notes-export.timer
    systemctl start hippocampus-notes-import.timer
    systemctl start memory-governor-consolidate.timer

    for timer in governor-digest.timer hippocampus-memory-sync.timer; do
        if [[ -f "/etc/systemd/system/$timer" ]]; then
            systemctl start "$timer"
        fi
    done
else
    info "Restarting services"
    systemctl restart hippocampus.service
    sleep 2
    systemctl restart memory-governor.service
fi

# ── Phase 8: Verify ─────────────────────────────────────────────────

echo ""
info "Verifying..."
sleep 2

hippo_ok=false
gov_ok=false

if curl -sf http://127.0.0.1:54321/health >/dev/null 2>&1; then
    info "Hippocampus: OK"
    hippo_ok=true
else
    warn "Hippocampus: NOT RESPONDING"
fi

if curl -sf http://127.0.0.1:54323/health >/dev/null 2>&1; then
    info "Governor: OK"
    gov_ok=true
else
    warn "Governor: NOT RESPONDING"
fi

echo ""
if $hippo_ok && $gov_ok; then
    info "Sacred Brain is running!"
    echo ""
    echo "  Hippocampus:  http://127.0.0.1:54321"
    echo "  Governor:     http://127.0.0.1:54323"
    echo "  Config:       /etc/sacred-brain/"
    echo "  State:        /var/lib/sacred-brain/"
    echo "  Ops:          cd $REPO_DIR && just --list"
    echo ""
    if [[ "$UPDATE_ONLY" == false ]]; then
        warn "Remember to edit CHANGE_ME values in /etc/sacred-brain/*.env and hippocampus.toml!"
    fi
else
    warn "Some services failed to start. Check: journalctl -u hippocampus -u memory-governor"
fi
