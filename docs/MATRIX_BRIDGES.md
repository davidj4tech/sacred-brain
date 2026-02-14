# Matrix Bridges (mautrix-*)

This host uses binary installs under `/opt/mautrix-*` with configs in `/etc/matrix-bridges/`
and data under `/var/lib/mautrix-*`. Synapse runs as `synapse:synapse` and bridges
run as `matrix:matrix`.

## Layout

- Binaries:
  - `/opt/mautrix-meta/mautrix-meta`
  - `/opt/mautrix-gmessages/mautrix-gmessages`
- Configs:
  - `/etc/matrix-bridges/mautrix-meta/config.yaml`
  - `/etc/matrix-bridges/mautrix-gmessages/config.yaml`
- Appservice registrations:
  - `/etc/matrix-bridges/mautrix-meta/registration.yaml`
  - `/etc/matrix-bridges/mautrix-gmessages/registration.yaml`
- Data/logs:
  - `/var/lib/mautrix-meta/`
  - `/var/lib/mautrix-gmessages/`

## Synapse integration

Add the registration files to `app_service_config_files` in Synapse config:

```yaml
app_service_config_files:
  - /etc/matrix-bridges/mautrix-meta/registration.yaml
  - /etc/matrix-bridges/mautrix-gmessages/registration.yaml
```

Restart Synapse after changes.

## Services

Systemd units live in `/etc/systemd/system/` (for example, `mautrix-meta.service`
and `mautrix-gmessages.service`) and run as `matrix:matrix`.

## Pairing runbook (gmessages)

1) Ensure `mautrix-gmessages.service` is running.
2) In Matrix, DM `@smsbot:ryer.org` and send `login`.
3) The bridge will return a QR code or pairing URL; open Google Messages on Android and use its device linking flow.
4) Confirm the management room appears and `help` returns commands.

## Auto-join helper (optional)

If you want the Matrix user to auto-accept invites (e.g., for bridge portal rooms),
use `bots/matrix/autojoin_bot.py` with `ops/systemd/matrix-autojoin.service`.
Optionally set allowlists:

- `MATRIX_AUTOJOIN_ALLOWLIST_SENDERS` (comma-separated MXIDs)
- `MATRIX_AUTOJOIN_ALLOWLIST_ROOMS` (comma-separated room IDs)
