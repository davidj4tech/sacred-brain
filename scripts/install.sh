#!/usr/bin/env bash
set -euo pipefail

# Sacred Brain installer
# Clone the repo, run this, edit /etc/sacred-brain/*, then re-run with --update.
#
# Usage:
#   sudo ./scripts/install.sh             # full install (won't start until configs are edited)
#   sudo ./scripts/install.sh --update    # refresh units + restart services
#   sudo ./scripts/install.sh --uninstall # stop + disable + remove units (keeps state by default)
#   sudo ./scripts/install.sh --uninstall --purge  # also remove /etc and /var/lib state

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYSTEMD_DIR="$REPO_DIR/ops/systemd"
CONFIG_DIR="$REPO_DIR/ops/config"
ETC_DIR="/etc/sacred-brain"
STATE_DIR="/var/lib/sacred-brain"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { echo "  [+] $*"; }
warn()  { echo "  [!] $*" >&2; }
die()   { echo "  [ERROR] $*" >&2; exit 1; }

# List unit files available in the repo (basenames). Every unit in
# ops/systemd/ is expected to have an [Install] section; if one doesn't,
# `systemctl enable` skips it (which is fine for compose-style units that
# are pulled in by another unit's Wants=).
list_units() {
    local f
    for f in "$SYSTEMD_DIR"/*.service "$SYSTEMD_DIR"/*.timer; do
        [[ -e "$f" ]] && basename "$f"
    done
}

# True if /etc/sacred-brain/*.env or *.toml still contains CHANGE_ME placeholders.
configs_have_placeholders() {
    [[ -d "$ETC_DIR" ]] || return 1
    grep -rlE 'CHANGE[_-]ME' "$ETC_DIR" >/dev/null 2>&1
}

# ── Argument parsing ────────────────────────────────────────────────

MODE=install
PURGE=false
for arg in "$@"; do
    case "$arg" in
        --update)    MODE=update ;;
        --uninstall) MODE=uninstall ;;
        --purge)     PURGE=true ;;
        -h|--help)
            sed -n '4,11p' "$0"
            exit 0
            ;;
        *) die "Unknown argument: $arg" ;;
    esac
done

# ── Pre-flight checks ───────────────────────────────────────────────

[[ $EUID -eq 0 ]] || die "Must run as root (sudo)"
[[ -d "$SYSTEMD_DIR" ]] || die "ops/systemd/ not found — run from repo root"

# ── Uninstall ───────────────────────────────────────────────────────

if [[ "$MODE" == "uninstall" ]]; then
    info "Stopping and disabling units"
    for unit in $(list_units); do
        if [[ -f "/etc/systemd/system/$unit" ]]; then
            systemctl disable --now "$unit" || true
            rm -f "/etc/systemd/system/$unit"
        fi
    done
    systemctl daemon-reload

    if $PURGE; then
        info "Removing $ETC_DIR and $STATE_DIR"
        rm -rf "$ETC_DIR" "$STATE_DIR"
        if id sacred &>/dev/null; then
            info "Removing service user 'sacred'"
            userdel sacred || warn "Could not remove user 'sacred'"
        fi
    else
        info "Kept $ETC_DIR and $STATE_DIR (use --purge to remove)"
    fi
    info "Uninstall complete."
    exit 0
fi

# ── Phase 1: Service user ───────────────────────────────────────────

if [[ "$MODE" == "install" ]]; then
    if id sacred &>/dev/null; then
        info "User 'sacred' already exists"
    else
        info "Creating service user 'sacred'"
        useradd --system --shell /usr/sbin/nologin --home-dir /opt/sacred-brain sacred
    fi
fi

# ── Phase 2: FHS directories ────────────────────────────────────────

if [[ "$MODE" == "install" ]]; then
    info "Creating state directories"
    mkdir -p "$STATE_DIR"/{hippocampus,governor,cache}
    chown -R sacred:sacred "$STATE_DIR"

    info "Creating config directory"
    mkdir -p "$ETC_DIR"
    chown sacred:sacred "$ETC_DIR"
fi

# ── Phase 3: Configuration ──────────────────────────────────────────

if [[ "$MODE" == "install" ]]; then
    for tmpl in "$CONFIG_DIR"/*.example; do
        [[ -e "$tmpl" ]] || continue
        target="$ETC_DIR/$(basename "${tmpl%.example}")"
        if [[ -f "$target" ]]; then
            info "Config exists, skipping: $target"
        else
            cp "$tmpl" "$target"
            chown sacred:sacred "$target"
            chmod 640 "$target"
            warn "Created $target from template — edit CHANGE_ME values!"
        fi
    done
fi

# ── Phase 4: Python venv ────────────────────────────────────────────

if [[ "$MODE" == "install" ]]; then
    if [[ ! -d "$REPO_DIR/.venv" ]]; then
        info "Creating Python venv"
        python3 -m venv "$REPO_DIR/.venv"
        "$REPO_DIR/.venv/bin/pip" install --upgrade pip
    fi

    if [[ -f "$REPO_DIR/pyproject.toml" ]]; then
        info "Installing Python package (editable)"
        "$REPO_DIR/.venv/bin/pip" install -e "$REPO_DIR"
    elif [[ -f "$REPO_DIR/requirements.txt" ]]; then
        info "Installing Python dependencies from requirements.txt"
        "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
    else
        warn "No pyproject.toml or requirements.txt — skipping Python deps"
    fi
fi

# ── Phase 5: Systemd units ──────────────────────────────────────────

info "Installing systemd units"
installed_units=()
for unit in $(list_units); do
    cp "$SYSTEMD_DIR/$unit" "/etc/systemd/system/$unit"
    info "  $unit"
    installed_units+=("$unit")
done

systemctl daemon-reload

# ── Phase 6: Enable units ───────────────────────────────────────────

info "Enabling units"
# `systemctl enable` errors on units without [Install]; skip those quietly.
for unit in "${installed_units[@]}"; do
    if grep -q '^\[Install\]' "$SYSTEMD_DIR/$unit"; then
        systemctl enable "$unit"
    fi
done

# ── Phase 7: Start ──────────────────────────────────────────────────

start_all() {
    info "Starting services"
    for unit in "${installed_units[@]}"; do
        [[ "$unit" == *.service ]] || continue
        systemctl start "$unit" || warn "Failed to start $unit"
    done
    info "Starting timers"
    for unit in "${installed_units[@]}"; do
        [[ "$unit" == *.timer ]] || continue
        systemctl start "$unit" || warn "Failed to start $unit"
    done
}

if [[ "$MODE" == "install" ]]; then
    if configs_have_placeholders; then
        warn "Configs in $ETC_DIR still contain CHANGE_ME placeholders."
        warn "Skipping service start. Edit them, then run:"
        warn "  sudo $0 --update"
        exit 0
    fi
    start_all
elif [[ "$MODE" == "update" ]]; then
    info "Restarting services"
    for unit in "${installed_units[@]}"; do
        [[ "$unit" == *.service ]] || continue
        systemctl restart "$unit" || warn "Failed to restart $unit"
    done
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
    echo "  Config:       $ETC_DIR/"
    echo "  State:        $STATE_DIR/"
    echo "  Ops:          cd $REPO_DIR && just --list"
else
    warn "Some services failed to start. Check: journalctl -u hippocampus -u memory-governor"
fi
