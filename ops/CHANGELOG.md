# Ops Changelog

Rules:
- One entry per change.
- Include: what, why, how to rollback, and what to verify.
- Prefer links to configs/paths.

## 2026-02-25
### Fix Synapse log explosion (27G) and reclaim disk space
**What:** Synapse logs filled disk to 100% (1.2G free). Two clients with stale Matrix tokens were tight-looping `/sync` requests, each generating ~5GB/day of identical `MacaroonDeserializationException` warnings. Also fixed a dual-rotation conflict between Python's `TimedRotatingFileHandler` and logrotate.
**Why:** Disk at 100% (222G/235G used); `/opt/synapse/log/` alone was 27G of uncompressed logs.
**Root causes:**
1. `mention_bot.py` (matrix-mention-bot service) — stale `MATRIX_ACCESS_TOKEN`, plus `matrix-nio` login fails through nginx (empty response). Switched to `http://127.0.0.1:8008` to bypass nginx for local traffic.
2. `sam-listener.py` on Pixel 8a (runit `sam-listener` service) — stale hardcoded token, retrying every 2s.
3. Synapse's `TimedRotatingFileHandler` created uncompressed date-stamped files alongside logrotate's compressed numbered files.

**Files changed:**
- `/opt/synapse/data/log.yaml` — `TimedRotatingFileHandler` → `FileHandler` (logrotate is now sole rotation mechanism)
- `/etc/logrotate.d/synapse` — unchanged; already configured for daily/compress/14 rotations
- `/etc/sacred-brain-matrix-mention.env` — `MATRIX_HOMESERVER` → `http://127.0.0.1:8008`; `MATRIX_ACCESS_TOKEN` commented out (uses password login)
- `/opt/sacred-brain/bots/matrix/mention_bot.py` — added `logging.getLogger("nio.responses").setLevel(logging.ERROR)` to suppress noisy schema validation warnings
- `~/.local/bin/sam-listener.py` on p8a — updated stale access token
- `@sam:ryer.org` password reset via direct Synapse DB update (credential redacted; stored in password manager)

**Rollback:**
- `log.yaml`: restore `TimedRotatingFileHandler` with `when: midnight`, `backupCount: 5`
- `mention_bot.env`: set `MATRIX_HOMESERVER=https://matrix.ryer.org` and uncomment `MATRIX_ACCESS_TOKEN` with a valid token
- Restart: `sudo systemctl restart matrix-mention-bot`
- Phone: `SVDIR=/data/data/com.termux/files/usr/var/service sv up sam-listener` (via `ssh p8ar`)

**Verify:**
- `df -h /opt/synapse/log` — should show ~90% usage, ~23G free
- `sudo tail -f /opt/synapse/log/homeserver.log` — no `MacaroonDeserializationException` spam
- `sudo systemctl status matrix-mention-bot` — active (running), processing events
- `sudo tail -f /var/log/nginx/access.log | grep 403` — no tight-loop 403s

## 2025-12-17
### UFW baseline hardened (Docker + Tailscale friendly)
**What:** Disabled UFW logging; set routed policy to allow; restricted SSH + LiteLLM to tailscale0; allowed docker bridges.  
**Why:** Prevent restart storms + UFW logging from causing host stalls; reduce public exposure.  
**Files/commands:**
- `/etc/default/ufw` (DEFAULT_FORWARD_POLICY)
- `ufw status verbose`
**Rollback:** Restore DEFAULT_FORWARD_POLICY=DROP; re-enable logging; re-open ports (see firewall doc).  
**Verify:** `sudo ufw status verbose` matches baseline; SSH reachable via Tailscale; LiteLLM healthcheck = healthy.

