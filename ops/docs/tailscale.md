# Tailscale Baseline

## Intent
- Tailscale is the admin network (treat as localhost).
- SSH allowed only via tailscale0.
- Internal tools (e.g., LiteLLM) allowed only via tailscale0.

## Key commands
- Status: `tailscale status`
- Ping: `tailscale ping <host>`
- IPs: `ip -br a | grep tailscale0`

## Firewall expectations
- UFW: allow in/out on tailscale0
- Ports allowed on tailscale0: 22, 4000 (and any other internal services)

## Known hostnames
- homeserver.eagle-dubhe.ts.net = 100.125.48.108
- dsp4.eagle-dubhe.ts.net = 100.104.214.49

