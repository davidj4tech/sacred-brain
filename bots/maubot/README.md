# Sacred Brain Matrix maubot plugin

Mention-triggered bot packaged as a maubot plugin. It forwards Matrix messages to Sacred Brain’s `/matrix/respond` endpoint, replies with text, and can add TTS/STT for encrypted rooms.

## Build & upload
1. Install maubot CLI (on your workstation): `pip install maubot`.
2. Build the plugin bundle from repo root:
   ```bash
   mbc build bots/maubot -o sacredbrain-mention.mbp
   ```
3. In the maubot admin UI, upload `sacredbrain-mention.mbp` and attach it to the bot user you want to respond.
4. Open the plugin config and paste/adapt `bots/maubot/config.example.yaml`.

## Config keys (map from old envs)
- `mention` (was `MATRIX_MENTION`, default `@sacredbrain`)
- `allow_rooms` optional allowlist of room IDs to listen in.
- `persona` optional persona key forwarded to Sacred Brain (new).
- `context_limit` (roughly replaces the hardcoded 20-message context from the old bot).
- `autojoin_enabled` auto-accept room invites for the bot user.
- `autojoin_allow_rooms` optional allowlist of room IDs for autojoin.
- `autojoin_allow_senders` optional allowlist of inviter user IDs for autojoin.
- `sacred_brain_url` (was `SACRED_BRAIN_URL`)
- `api_key` (was `SACRED_BRAIN_API_KEY`)
- `timeout_seconds` HTTP timeout (new safety guard).
 - `tts_*` options mirror the old `BAIBOT_TTS_*` envs.
 - `stt_*` options mirror the old `BAIBOT_STT_*` envs.

The homeserver URL and access token/appservice are configured at the maubot host level per bot user, not inside this plugin.

## Migration checklist (from `matrix-nio` script)
- Gather old env values: `MATRIX_MENTION`, `SACRED_BRAIN_URL`, `SACRED_BRAIN_API_KEY`.
- Build and upload the plugin bundle, then configure the plugin with the values above.
- Join the bot user to target rooms (or invite it) and set `allow_rooms` if you want to restrict scope.
- Disable the old service if it was running:
  ```bash
  sudo systemctl disable --now matrix-bot || true
  ```
- Optionally remove the old virtualenv/service files once the plugin is live.

## Local dry-run
The plugin uses `httpx` only; no DB is required. For quick checks, load it into a local maubot instance and send a mention in a test room to confirm responses.
