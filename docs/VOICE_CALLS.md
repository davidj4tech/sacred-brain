# Voice Calls (Asterisk + Matrix)

This setup uses local Asterisk (Docker, host networking) plus a Matrix↔SIP bridge.
Current SIP target: `@david:ryer.org`.

## Asterisk (local)

- Configs: `/opt/asterisk/etc/asterisk`
- Logs: `/opt/asterisk/var/log/asterisk`
- Start: `sudo docker compose -f /opt/asterisk/docker-compose.yml up -d`

Endpoints in `pjsip.conf`:
- `david` (extension 7001)
- `matrix` (extension 7002, reserved for Matrix↔SIP bridge)

Dialplan in `extensions.conf`:
- `600` echo test
- `7001` David's SIP endpoint
- `7002` Matrix bridge endpoint

## Matrix↔SIP bridge (pending)

Choose a Matrix↔SIP bridge and map Matrix user `@david:ryer.org` to SIP endpoint
`matrix` (or adjust the dialplan to target a bridge-provided SIP user).
