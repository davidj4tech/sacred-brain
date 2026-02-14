# Installing Sacred Brain

## Prerequisites

- Linux with systemd (Debian/Ubuntu/Raspberry Pi OS)
- Python 3.11+
- `curl` (for health checks and consolidation)
- `just` (optional, for ops recipes): `sudo apt install just`
- A LiteLLM-compatible gateway on port 4000 (optional, for LLM features)

## Quick Start

```bash
# 1. Clone the repo
git clone git@github.com:davidj4tech/sacred-brain.git /opt/sacred-brain
cd /opt/sacred-brain

# 2. Copy and edit config templates
cp ops/config/hippocampus.toml.example ops/config/hippocampus.toml.local
cp ops/config/hippocampus.env.example ops/config/hippocampus.env.local
cp ops/config/memory-governor.env.example ops/config/memory-governor.env.local

# Edit each file — replace CHANGE_ME values with real API keys
# The installer will copy these to /etc/sacred-brain/ if no config exists yet

# 3. Run the installer
sudo ./scripts/install.sh

# 4. Verify
just health
just timers
```

## What the Installer Does

| Phase | Action |
|-------|--------|
| 1. User | Creates `sacred` system user (nologin shell) |
| 2. Directories | Creates `/var/lib/sacred-brain/{hippocampus,governor,cache}` and `/etc/sacred-brain/` |
| 3. Config | Copies `.example` templates to `/etc/sacred-brain/` (skips if files already exist) |
| 4. Venv | Creates Python venv and installs dependencies |
| 5. Systemd | Copies unit files from `ops/systemd/` to `/etc/systemd/system/` |
| 6. Enable | Enables all services and timers |
| 7. Start | Starts Hippocampus, Governor, and all timers |
| 8. Verify | Health checks both services |

## Updating

After pulling new code:

```bash
cd /opt/sacred-brain
git pull

# Update systemd units only (doesn't touch config or recreate dirs)
just update-units

# Or manually:
sudo ./scripts/install.sh --update
```

## Directory Layout

```
/opt/sacred-brain/              ← repo (code, scripts, ops)
/etc/sacred-brain/              ← configuration (not in repo)
    hippocampus.toml            ← Hippocampus app config
    hippocampus.env             ← Hippocampus environment vars
    memory-governor.env         ← Governor environment vars
/var/lib/sacred-brain/          ← state (not in repo)
    hippocampus/
        hippocampus_memories.sqlite
        memories-denote/
    governor/
        state.db
        durable.spool
    cache/
        sam_chart.json
    auto_memory_tuning.json
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| `hippocampus.service` | 54321 | Memory storage and retrieval (Mem0/SQLite) |
| `memory-governor.service` | 54323 | Memory governance, classification, and consolidation |

## Timers

| Timer | Schedule | Description |
|-------|----------|-------------|
| `governor-digest.timer` | 03:20 daily | Write memory digest to markdown |
| `hippocampus-memory-sync.timer` | 03:35 daily | Sync markdown files into Hippocampus |
| `hippocampus-auto-prune.timer` | 04:15 daily | Prune low-salience auto memories |
| `hippocampus-auto-tune.timer` | Hourly | Adaptive capture threshold tuning |
| `hippocampus-notes-export.timer` | Daily | Export memories to Org/Denote format |
| `hippocampus-notes-import.timer` | Daily | Import Org/Denote notes into memories |
| `memory-governor-consolidate.timer` | Hourly | Consolidate working memory into long-term |

## Configuration

### Hippocampus (`hippocampus.toml`)

Core settings: auth keys, Mem0 backend, Agno model, notes directory. See `ops/config/hippocampus.toml.example` for all options.

### Hippocampus Environment (`hippocampus.env`)

SAM pipeline settings (LLM gateway URL, model alias, timeout) and the Hippocampus API key.

### Governor Environment (`memory-governor.env`)

Bind address, Hippocampus/LiteLLM URLs, stream/working memory TTLs, reranking config, consolidation scopes.

## Optional Features

### Memory Sync (per-identity)

Sync markdown memory files for any identity into Hippocampus. See [MEMORY_SYNC.md](MEMORY_SYNC.md) for setup.

### ChatGPT Import

One-time import of ChatGPT conversation history. See [CHATGPT_IMPORT.md](CHATGPT_IMPORT.md).

### Governor Digest

Nightly timer that pulls consolidated memories from Governor and writes human-readable markdown. Requires a target directory (configured via the systemd unit's `ReadWritePaths`).

## Hardening

All services run with:
- `NoNewPrivileges=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- `PrivateTmp=true`
- `ReadWritePaths` limited to `/var/lib/sacred-brain`
- `ReadOnlyPaths` for code and config

Check security scores: `just security-audit`

## Troubleshooting

```bash
# Service logs
just logs

# Service status
just status

# Full smoke test (health + write + read)
just smoke

# Config validation
just config-check

# Check a specific service
journalctl -u hippocampus --since "10 min ago"
journalctl -u memory-governor --since "10 min ago"
```
