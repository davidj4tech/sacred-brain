# Memory Sync: Markdown → Hippocampus

The `memory_sync.py` script syncs markdown memory files into Hippocampus. It reads every non-empty, non-header line from `MEMORY.md` and `memory/*.md` in a source directory and pushes them as memory records, with content-hash deduplication so repeated runs are safe.

## How It Works

Given a directory like:

```
/opt/sam/
├── MEMORY.md           ← top-level memory file (optional)
└── memory/
    ├── IDENTITY.md     ← who the identity is
    ├── SOUL.md         ← personality and values
    ├── USER.md         ← info about the human they help
    ├── TOOLS.md        ← environment-specific setup
    └── memory/         ← ignored (only top-level *.md files are read)
```

The script:
1. Reads each `.md` file, skipping headers (`#`) and blank lines
2. Hashes each line (SHA-256, first 16 hex chars)
3. Checks Hippocampus SQLite for existing hashes → skips duplicates
4. Pushes new lines as memories with metadata (source file, line number, hash)

## Adding a New Identity

### 1. Create the memory directory

```bash
sudo mkdir -p /opt/mybot/memory
sudo chown -R sacred:sacred /opt/mybot
```

### 2. Write the memory files

At minimum, create an identity file:

```bash
cat > /opt/mybot/memory/IDENTITY.md << 'EOF'
# Identity

- **Name:** Aria
- **Role:** Home automation assistant
- **Vibe:** Efficient, friendly, slightly nerdy
EOF
```

You can add as many `.md` files as you like under `memory/`. Common ones:

| File | Purpose |
|------|---------|
| `IDENTITY.md` | Who the identity is (name, role, personality) |
| `SOUL.md` | Values, communication style, boundaries |
| `USER.md` | Info about the human (preferences, schedule, context) |
| `TOOLS.md` | Environment-specific setup (devices, hosts, voices) |
| `MEMORY.md` | Top-level curated long-term memories (in the root, not `memory/`) |

### 3. Create a systemd service + timer

```bash
sudo tee /etc/systemd/system/hippocampus-memory-sync-mybot.service > /dev/null << 'EOF'
[Unit]
Description=Sync mybot memory files into Hippocampus
After=hippocampus.service

[Service]
Type=oneshot
User=sacred
Group=sacred
EnvironmentFile=/etc/sacred-brain/hippocampus.env
Environment=MEMORY_SYNC_ROOT=/opt/mybot
Environment=HIPPOCAMPUS_USER_ID=mybot
Environment=HIPPOCAMPUS_SQLITE_PATH=/var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite
ExecStart=/opt/sacred-brain/.venv/bin/python /opt/sacred-brain/scripts/memory_sync.py push

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/sacred-brain
ReadOnlyPaths=/opt/sacred-brain /opt/mybot /etc/sacred-brain
ProtectKernelTunables=true
ProtectKernelModules=true

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hippocampus-memory-sync-mybot.timer > /dev/null << 'EOF'
[Unit]
Description=Daily sync of mybot memory files into Hippocampus

[Timer]
OnCalendar=*-*-* 03:40:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hippocampus-memory-sync-mybot.timer
```

### 4. Test it

```bash
# Dry run — see what would be pushed
sudo -u sacred \
  MEMORY_SYNC_ROOT=/opt/mybot \
  HIPPOCAMPUS_USER_ID=mybot \
  HIPPOCAMPUS_API_KEY=hippo_local_a58b583f7a844f0eb3bc02e58d56f5bd \
  HIPPOCAMPUS_SQLITE_PATH=/var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite \
  /opt/sacred-brain/.venv/bin/python /opt/sacred-brain/scripts/memory_sync.py push --dry-run

# Push for real
sudo -u sacred \
  MEMORY_SYNC_ROOT=/opt/mybot \
  HIPPOCAMPUS_USER_ID=mybot \
  HIPPOCAMPUS_API_KEY=hippo_local_a58b583f7a844f0eb3bc02e58d56f5bd \
  HIPPOCAMPUS_SQLITE_PATH=/var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite \
  /opt/sacred-brain/.venv/bin/python /opt/sacred-brain/scripts/memory_sync.py push

# Run again — should show pushed=0 (dedup working)
```

### 5. Add the timer to the justfile (optional)

Edit `/opt/sacred-brain/justfile` and add the new timer to the `timers` recipe:

```
@systemctl list-timers ... hippocampus-memory-sync-mybot.timer --no-pager
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_SYNC_ROOT` | *(required)* | Directory containing `MEMORY.md` and/or `memory/*.md` |
| `HIPPOCAMPUS_URL` | `http://127.0.0.1:54321` | Hippocampus API URL |
| `HIPPOCAMPUS_API_KEY` | *(empty)* | API key for Hippocampus auth |
| `HIPPOCAMPUS_USER_ID` | `default` | User ID to store memories under |
| `HIPPOCAMPUS_SQLITE_PATH` | `/var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite` | SQLite path for hash-based dedup |

## Existing Setup: Sam

Sam's memory sync is already configured:

- **Source**: `/opt/sam/` (MEMORY.md + memory/IDENTITY.md, SOUL.md, USER.md, TOOLS.md)
- **User ID**: `sam`
- **Timer**: `hippocampus-memory-sync.timer` at 03:35 daily
- **Service**: `hippocampus-memory-sync.service`
