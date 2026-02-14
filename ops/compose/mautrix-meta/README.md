# mautrix-meta (Facebook/Messenger) bridge

Bridge Facebook/Messenger chats into Matrix using the mautrix-meta appservice. This repo now treats
`/opt/mautrix-meta` + `/etc/matrix-bridges` as the source of truth; the compose layout here is legacy.

## Files
- `config.yaml`: bridge config (homeserver `https://matrix.ryer.org`, domain `ryer.org`, sqlite DB at `/data/meta-bridge.db`, encryption enabled, bot `@metabot:ryer.org`).
- `registration.yaml`: appservice registration generated from the config (as/hs tokens already populated).
- `docker-compose.yml`: runs `dock.mau.dev/mautrix/meta:latest` with this folder mounted at `/data`.

## Binary install layout (recommended for this host)

- Binary: `/opt/mautrix-meta/mautrix-meta`
- Config: `/etc/matrix-bridges/mautrix-meta/config.yaml`
- Registration: `/etc/matrix-bridges/mautrix-meta/registration.yaml`
- Data/logs: `/var/lib/mautrix-meta/`
- Owner/group: `matrix:matrix`

Template configs live at `/opt/mautrix-meta/config.template.yaml`. For existing installs,
copy the current `/opt/mautrix-meta/config.yaml` and update paths as needed.

## Install into Synapse
1) Add the registration file to `app_service_config_files` in `/etc/matrix-synapse/homeserver.yaml` (or wherever the Synapse config lives) and restart Synapse:
```bash
app_service_config_files:
  - /etc/matrix-bridges/mautrix-meta/registration.yaml

sudo systemctl restart matrix-synapse
```

## Run the bridge
```bash
sudo -u matrix /opt/mautrix-meta/mautrix-meta \
  -c /etc/matrix-bridges/mautrix-meta/config.yaml \
  -r /etc/matrix-bridges/mautrix-meta/registration.yaml
```
The bridge will listen on `localhost:29319`. Logs go to `/var/lib/mautrix-meta/logs/bridge.log`
and the database is configured in the config file.

## Log in to Facebook/Messenger
1) In Matrix, DM the bot `@metabot:ryer.org`.
2) Send `login` and follow the prompts (enter FB username/password; complete 2FA if prompted). The bridge runs in `facebook` mode; Messenger login is available by choosing it when prompted.
3) After login succeeds, the bot opens a management room; run `help` there for command list. Portals will be created automatically as messages arrive.

If you change `appservice.address/port` or `homeserver.domain/address` in `config.yaml`, regenerate `registration.yaml` with the command above and restart both Synapse and the bridge container.
