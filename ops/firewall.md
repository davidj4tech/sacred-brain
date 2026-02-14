# Homeserver Firewall Baseline

This document captures the **known‑good UFW configuration** for this host, designed to be **stable, boring, and hard to accidentally break** when running Docker services and Tailscale side‑by‑side.

The goals:

* Protect the public edge
* Keep Docker networking out of UFW’s way
* Treat Tailscale like localhost
* Avoid logging storms and SSH lockouts

---

## Architecture at a Glance

* **Public edge:** nginx (HTTP/HTTPS), Matrix federation
* **Private/admin:** SSH, LiteLLM, internal tools
* **Container runtime:** Docker (bridge networks)
* **Overlay network:** Tailscale (trusted)

Trust model:

* Internet = untrusted
* Tailscale = trusted
* Docker bridges = internal plumbing

---

## UFW Global Defaults (Critical)

```text
Status: active
Logging: off
Default: deny (incoming), allow (outgoing), allow (routed)
```

Why this matters:

* `deny (incoming)` → protects the public surface
* `allow (outgoing)` → normal system behavior
* `allow (routed)` → **prevents Docker ↔ UFW conflicts**
* `logging off` → avoids kernel / IO churn during container restarts

**This single routed-policy change prevents restart storms from freezing SSH.**

---

## Explicit Interface Trust

### Tailscale (treat like localhost)

```bash
ufw allow in on tailscale0
ufw allow out on tailscale0
```

Effect:

* Admin services are reachable only over Tailscale
* No need for public exposure

---

### Docker Bridges (hands off)

```text
Anywhere on docker0           ALLOW IN
Anywhere on br-<docker-id>   ALLOW IN
```

Effect:

* UFW does **not** inspect or block container‑to‑container traffic
* Docker’s own iptables/NAT rules remain authoritative

---

## Allowed Services

### Public (Internet-facing)

```text
80/tcp     (HTTP)
443/tcp    (HTTPS)
8443/tcp   (Matrix federation)
```

Handled by nginx (reverse proxy).

---

### Tailscale‑only (Private)

```text
22/tcp     (SSH)
4000/tcp  (LiteLLM)
```

Rules:

```bash
ufw allow in on tailscale0 to any port 22
ufw allow in on tailscale0 to any port 4000
```

Effect:

* Invisible to the public internet
* Accessible from trusted devices only

---

## Outbound Rules

```text
ALLOW OUT Anywhere on tailscale0
```

Allows host and containers to communicate over Tailscale without friction.

---

## Known‑Good UFW Status Snapshot

```text
Status: active
Logging: off
Default: deny (incoming), allow (outgoing), allow (routed)

80/tcp                     ALLOW IN    Anywhere
443/tcp                    ALLOW IN    Anywhere
8443/tcp                   ALLOW IN    Anywhere

Anywhere on docker0        ALLOW IN    Anywhere
Anywhere on br-<id>        ALLOW IN    Anywhere
Anywhere on tailscale0     ALLOW IN    Anywhere

22 on tailscale0           ALLOW IN    Anywhere
4000 on tailscale0         ALLOW IN    Anywhere

ALLOW OUT Anywhere on tailscale0
```

If this matches, the firewall is in a **known‑safe state**.

---

## Operational Rules of Thumb

* **Never** re‑enable UFW logging unless debugging a specific incident
* If SSH is flaky but nginx works → suspect container restart storms
* Validate Docker Compose files **before** deploying:

```bash
docker compose config && docker compose up -d
```

* Prefer **healthchecks + restart policies** over firewall micromanagement

---

## Emergency Recovery

If a container starts flapping and the host feels unstable:

```bash
docker update --restart=no <container>
docker stop <container>
```

This immediately halts network churn without rebooting the host.

---

## Design Philosophy (Why This Works)

* Docker already acts as a firewall
* Tailscale already provides zero‑trust networking
* UFW should guard the **edge**, not police containers

When UFW tries to be clever inside Docker, stability suffers.
This configuration keeps responsibilities clean and predictable.

---

**Status:** Baseline accepted
**Last verified:** 2025‑12‑17

