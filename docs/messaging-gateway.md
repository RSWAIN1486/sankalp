# Messaging Gateway

Sankalp's messaging gateway is the first step toward an always-available local daemon. The initial
gateway supports Telegram through the official Bot API long-polling path, so it does not need a
public webhook URL.

## Configure

Create a bot with Telegram BotFather, then open `Settings -> Gateway` in Sankalp:

- Enable Telegram gateway.
- Paste the bot token.
- Add your Telegram user ID to the allowlist.
- Restart Sankalp or run `scripts/relaunch_dev.sh`.

If you do not know your Telegram user ID yet, start the bot without an allowlist and send it a
message. Sankalp will deny access and include the user ID to add.

## Run Locally

```sh
python3 -m sankalp.daemon --telegram
```

The daemon starts the normal loopback WebUI/API server and the Telegram gateway in the same process
when the gateway is enabled in settings. Use `--no-http` if you only want the Telegram gateway:

```sh
python3 -m sankalp.daemon --telegram --no-http
```

## Configuration

- `Settings -> Gateway`: normal product path for token, enablement, and allowed users.
- `SANKALP_TELEGRAM_BOT_TOKEN`: optional env override for the Telegram bot token.
- `SANKALP_TELEGRAM_ALLOWED_USERS`: optional env override for comma-separated Telegram user IDs.
- `SANKALP_TELEGRAM_ALLOW_ALL=1`: development-only bypass for the allowlist.
- `SANKALP_TELEGRAM_ENABLED=0`: temporarily disables the Telegram gateway for a daemon process.
- `SANKALP_TELEGRAM_POLL_TIMEOUT`: long-poll timeout in seconds; default `30`.
- `SANKALP_TELEGRAM_POLL_INTERVAL`: retry sleep after gateway errors; default `1.0`.

## Startup

- `scripts/relaunch_dev.sh` starts `python3 -m sankalp.daemon`, so the configured Telegram gateway is
  available during local development.
- `scripts/install_macos.sh` installs a user LaunchAgent at
  `~/Library/LaunchAgents/ai.yantrai.sankalp.daemon.plist`.
- The LaunchAgent starts the installed `Sankalp.app`. The app stays in the menu bar, starts/checks the
  daemon, and exposes quick actions to copy the base URL, open the WebUI, restart the daemon, or
  update Sankalp when a newer release manifest is available.
- The LaunchAgent has `RunAtLoad` and `KeepAlive`, so the menu-bar app and daemon start after macOS
  login and continue while the screen is locked.
- This is intentionally a user LaunchAgent, not a root LaunchDaemon. It does not run before the first
  user login, because Sankalp uses user-local state, user app permissions, and `~/.sankalp`.

## Chat Behavior

- One Sankalp session is kept per Telegram chat/thread.
- Session mappings and the Telegram update offset are stored in `~/.sankalp/gateway/telegram.json`.
- `/new` starts a fresh Sankalp session for the current Telegram chat.
- `/ls [path]` lists files and folders under Sankalp's configured local roots.
- `/find <name>` recursively finds matching files or folders across configured local roots.
- Long answers are split into Telegram-safe chunks.
- Non-text messages are acknowledged but not processed yet.

## Commands

```text
/start
/help
/whoami
/status
/new
/ls
/find
```

All normal text messages are routed through `Agent.turn`, so existing memory, tools, provider
selection, and session behavior still apply. Telegram uses the default provider/model saved in
`Settings -> Provider`; WebUI composer overrides are browser-local and do not affect Telegram unless
they are saved as the default.

Local file access is limited to roots saved in `Settings -> Memory` under `Allowed local roots`, or
to `SANKALP_ALLOWED_ROOTS` when that environment override is set.

## Roadmap

- launchd/systemd service wrappers for true background startup.
- Telegram attachments, images, files, and voice transcription.
- Outbound notifications from scheduled jobs.
- Gateway pairing flow instead of environment-only allowlists.
- Background tasks and `/stop` cancellation.
