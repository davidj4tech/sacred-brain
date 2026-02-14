# Ops Changelog

Rules:
- One entry per change.
- Include: what, why, how to rollback, and what to verify.
- Prefer links to configs/paths.

## 2025-12-17
### UFW baseline hardened (Docker + Tailscale friendly)
**What:** Disabled UFW logging; set routed policy to allow; restricted SSH + LiteLLM to tailscale0; allowed docker bridges.  
**Why:** Prevent restart storms + UFW logging from causing host stalls; reduce public exposure.  
**Files/commands:**
- `/etc/default/ufw` (DEFAULT_FORWARD_POLICY)
- `ufw status verbose`
**Rollback:** Restore DEFAULT_FORWARD_POLICY=DROP; re-enable logging; re-open ports (see firewall doc).  
**Verify:** `sudo ufw status verbose` matches baseline; SSH reachable via Tailscale; LiteLLM healthcheck = healthy.

