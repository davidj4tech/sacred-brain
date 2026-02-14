# Sacred Brain operations justfile

set dotenv-load := false

# List all recipes
default:
    @just --list

# Start all services
start:
    sudo systemctl start hippocampus memory-governor

# Stop all services
stop:
    sudo systemctl stop memory-governor hippocampus

# Restart all services
restart:
    sudo systemctl restart hippocampus
    sleep 2
    sudo systemctl restart memory-governor

# Show service status
status:
    @systemctl status hippocampus memory-governor --no-pager

# Tail logs from all services
logs *ARGS='-f':
    sudo journalctl -u hippocampus -u memory-governor {{ARGS}}

# Health check both services
health:
    @echo "Hippocampus: $(curl -sf http://127.0.0.1:54321/health || echo FAIL)"
    @echo "Governor:    $(curl -sf http://127.0.0.1:54323/health || echo FAIL)"

# Show timer status
timers:
    @systemctl list-timers hippocampus-auto-prune.timer memory-governor-consolidate.timer governor-digest.timer --no-pager

# Full backup to /root/
backup:
    sudo tar czf /root/sacred-brain-backup-$(date +%Y%m%d-%H%M).tar.gz \
      /var/lib/sacred-brain/ /etc/sacred-brain/ \
      /etc/systemd/system/hippocampus*.service /etc/systemd/system/hippocampus*.timer \
      /etc/systemd/system/memory-governor*.service /etc/systemd/system/memory-governor*.timer \
      /etc/systemd/system/governor-digest.service /etc/systemd/system/governor-digest.timer
    @echo "Backup complete"

# Quick SQLite DB backup
backup-db:
    sudo cp /var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite \
      /root/hippocampus_memories.sqlite.$(date +%Y%m%d-%H%M).bak
    @echo "DB backup complete"

# Smoke test: health + write + read
smoke:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Health ==="
    curl -sf http://127.0.0.1:54321/health && echo ""
    curl -sf http://127.0.0.1:54323/health && echo ""
    echo "=== Write test ==="
    curl -sf -X POST http://127.0.0.1:54323/remember \
      -H 'Content-Type: application/json' \
      -d '{"user_id":"test","text":"Smoke test '"$(date -Is)"'","source":"justfile","kind":"episodic","scope":{"kind":"global","id":"test"}}'
    echo ""
    echo "=== Read test ==="
    curl -sf -X POST http://127.0.0.1:54323/recall \
      -H 'Content-Type: application/json' \
      -d '{"user_id":"test","query":"smoke test","k":3}'
    echo ""
    echo "=== Smoke test PASSED ==="

# Validate config files exist and are readable
config-check:
    #!/usr/bin/env bash
    set -euo pipefail
    ok=true
    for f in /etc/sacred-brain/hippocampus.toml /etc/sacred-brain/hippocampus.env /etc/sacred-brain/memory-governor.env; do
      if [ -r "$f" ]; then echo "OK  $f"; else echo "FAIL $f"; ok=false; fi
    done
    for f in /var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite /var/lib/sacred-brain/governor/state.db; do
      if [ -f "$f" ]; then echo "OK  $f"; else echo "FAIL $f"; ok=false; fi
    done
    $ok && echo "All config checks passed" || { echo "Some checks failed"; exit 1; }

# systemd security audit
security-audit:
    @systemd-analyze security hippocampus.service 2>/dev/null | tail -1
    @systemd-analyze security memory-governor.service 2>/dev/null | tail -1

# Remove backward-compat symlinks from Phase 3 migration
remove-compat-symlinks:
    sudo rm -f /opt/sacred-brain/data/hippocampus_memories.sqlite
    sudo rm -f /opt/sacred-brain/data/memories-denote
    sudo rm -f /opt/sacred-brain/var/memory-governor/state.db
    sudo rm -f /opt/sacred-brain/var/memory-governor/durable.spool
    sudo rm -f /opt/sacred-brain/var/auto_memory_tuning.json
    sudo rm -f /opt/sacred-brain/config/hippocampus.toml
    sudo rm -f /etc/memory-governor/memory-governor.env
    @echo "Compat symlinks removed"
