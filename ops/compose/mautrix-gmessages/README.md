# mautrix-gmessages bridge

Bridge Google Messages (Android) into Matrix using the mautrix-gmessages appservice. This repo now treats
`/opt/mautrix-gmessages` + `/etc/matrix-bridges` as the source of truth; the compose layout here is legacy.

## Files
- `config.yaml`: bridge config (homeserver `https://matrix.ryer.org`, domain `ryer.org`, sqlite DB at `/data/gmessages-bridge.db`).
- `docker-compose.yml`: runs the mautrix-gmessages image with this folder mounted at `/data`.

## Binary install layout (recommended for this host)

- Binary: `/opt/mautrix-gmessages/mautrix-gmessages`
- Config: `/etc/matrix-bridges/mautrix-gmessages/config.yaml`
- Registration: `/etc/matrix-bridges/mautrix-gmessages/registration.yaml`
- Data/logs: `/var/lib/mautrix-gmessages/`
- Owner/group: `matrix:matrix`

Template configs live at `/opt/mautrix-gmessages/config.template.yaml`.

## Generate registration + tokens

The `as_token` and `hs_token` values in `config.yaml` must be generated. Run:

```bash
sudo -u matrix /opt/mautrix-gmessages/mautrix-gmessages \
  -c /etc/matrix-bridges/mautrix-gmessages/config.yaml \
  -r /etc/matrix-bridges/mautrix-gmessages/registration.yaml -g
```

Then copy the generated tokens from `registration.yaml` into `config.yaml`.

## Install into Synapse

1) Add the registration file to `app_service_config_files` in `/etc/matrix-synapse/homeserver.yaml` (or wherever the Synapse config lives) and restart Synapse:
```bash
app_service_config_files:
  - /etc/matrix-bridges/mautrix-gmessages/registration.yaml

sudo systemctl restart matrix-synapse
```

## Run the bridge
```bash
sudo -u matrix /opt/mautrix-gmessages/mautrix-gmessages \
  -c /etc/matrix-bridges/mautrix-gmessages/config.yaml \
  -r /etc/matrix-bridges/mautrix-gmessages/registration.yaml
```
Logs go to `/var/lib/mautrix-gmessages/logs/bridge.log` and the database
is configured in `config.yaml` (Postgres by default).

## Pair Android device

Install the Google Messages companion app and follow the pairing instructions for the bridge. After the
bridge starts, DM the bot user in Matrix (`@smsbot:ryer.org`) and use `help` to see available commands.
