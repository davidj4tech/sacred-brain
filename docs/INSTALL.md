# Installing Sacred Brain

## Prerequisites

- Linux with systemd (Debian/Ubuntu/Raspberry Pi OS)
- Python 3.11+
- `pipx` (`sudo apt install pipx`)
- `make`, `curl`
- `just` (optional, for ops recipes): `sudo apt install just`
- A LiteLLM-compatible gateway on port 4000 (optional, for LLM features)

## Quick Start

```bash
# 1. Clone the repo
sudo git clone https://github.com/davidj4tech/sacred-brain.git /opt/sacred-brain
cd /opt/sacred-brain

# 2. Install
sudo make install

# 3. Edit /etc/sacred-brain/* — replace CHANGE_ME values
sudoedit /etc/sacred-brain/hippocampus.toml
sudoedit /etc/sacred-brain/hippocampus.env
sudoedit /etc/sacred-brain/memory-governor.env

# 4. Start the services
sudo systemctl start hippocampus memory-governor

# 5. Verify
just health
just timers
```

The repo lives at `/opt/sacred-brain/` because the timer-target scripts
(in `scripts/`) run from there. The Python services themselves run from a
pipx-managed venv at `/opt/pipx/venvs/sacred-brain-hippocampus/`, with
`hippocampus` and `memory-governor` symlinked into `/usr/local/bin/`.

## What `make install` Does

| Target | Action |
|--------|--------|
| `install-deps` | Creates `sacred` system user (nologin) and `/var/lib/sacred-brain/{hippocampus,governor,cache}` and `/etc/sacred-brain/` |
| `migrate-legacy` | Removes any old `/opt/sacred-brain/.venv/` from a pre-pipx install (idempotent) |
| `install-package` | `pipx install --force .` into `/opt/pipx/venvs/sacred-brain-hippocampus/`, with `hippocampus` and `memory-governor` symlinks in `$(PREFIX)/bin/` |
| `install-bin` | Installs `sacred-search` to `$(PREFIX)/bin/sacred-search` |
| `install-systemd` | Copies all unit files from `ops/systemd/` to `/etc/systemd/system/`, runs `daemon-reload`, enables every unit with an `[Install]` section |
| `install-config` | Copies `.example` templates to `/etc/sacred-brain/` (skips files that already exist) |

`make install` does **not** start services automatically — the operator
edits `CHANGE_ME` values, then runs `systemctl start` manually.

## Updating

After pulling new code:

```bash
cd /opt/sacred-brain
sudo git pull
sudo make install-update
```

`install-update` reinstalls the Python package, refreshes systemd unit
files, runs `daemon-reload`, and restarts any enabled services.

## Uninstalling

```bash
# Stop, disable, and remove all systemd units; uninstall the pipx package;
# remove sacred-search from $(PREFIX)/bin. Keeps configs and state.
sudo make uninstall

# Also remove /etc/sacred-brain, /var/lib/sacred-brain, and the 'sacred' user
sudo make uninstall-purge
```

## Compatibility shim

`scripts/install.sh` still exists as a thin wrapper that delegates to the
Makefile, so `sudo ./scripts/install.sh [--update|--uninstall|--uninstall --purge]`
continues to work for existing automation.

## Customization

The Makefile honors standard variables for non-default installs and packagers:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PREFIX` | `/usr/local` | Where `hippocampus`, `memory-governor`, `sacred-search` live |
| `SYSCONFDIR` | `/etc` | Parent of `sacred-brain/` config dir |
| `DESTDIR` | (empty) | Stage all paths under this prefix (skips `systemctl` calls) |
| `PIPX_HOME` | `/opt/pipx` | Where pipx puts the package's venv |

## Directory Layout

```
/opt/sacred-brain/                        ← repo clone (timer scripts run from here)
/opt/pipx/venvs/sacred-brain-hippocampus/ ← installed Python package (services run from here)
/usr/local/bin/hippocampus
/usr/local/bin/memory-governor
/usr/local/bin/sacred-search
/etc/sacred-brain/                        ← configuration (not in repo)
    hippocampus.toml
    hippocampus.env
    memory-governor.env
/var/lib/sacred-brain/                    ← state (not in repo)
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
Optional: `HIPPOCAMPUS_HOST` (default `0.0.0.0`) and `HIPPOCAMPUS_PORT` (default `54321`).

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
- `ReadOnlyPaths` for code (`/opt/pipx`, plus `/opt/sacred-brain` for timer scripts) and config (`/etc/sacred-brain`)

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
