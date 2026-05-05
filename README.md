# Sankalp

Sankalp is a local-first personal assistant with chat sessions, auditable tool activity,
provider switching, and human-readable Obsidian-compatible memory.

The current app has two parts:

- Python backend: local JSON/SSE APIs, provider adapters, sessions, tools, and memory.
- SvelteKit WebUI: the main chat interface, settings drawer, memory browser, and session
  controls.

The Python backend is API-only. Use the SvelteKit WebUI for the browser interface.

## Requirements

- macOS or Linux
- Python 3.9+
- Node.js 24 via `nvm` for the WebUI

On this Mac, `nvm` is already expected at `~/.nvm/nvm.sh`. If Node is not installed:

```sh
source ~/.nvm/nvm.sh
nvm install 24
```

## Install

### One-command macOS App Install

Sankalp can install like a local WebUI app: the installer clones or updates the repo under
`~/.sankalp/app`, installs Node through `nvm` when needed, builds the SvelteKit WebUI,
creates `~/Applications/Sankalp.app`, frees the configured local port, and opens the app.

```sh
curl -fsSL https://raw.githubusercontent.com/RSWAIN1486/sankalp/main/scripts/install_macos.sh | bash
```

The installed app serves the built WebUI and the Python backend from one loopback URL:

```text
http://127.0.0.1:8765
```

Useful installer overrides:

```sh
curl -fsSL https://raw.githubusercontent.com/RSWAIN1486/sankalp/main/scripts/install_macos.sh | SANKALP_PORT=8766 bash
SANKALP_INSTALL_DIR="$HOME/Developer/sankalp" bash scripts/install_macos.sh
SANKALP_SKIP_PORT_KILL=1 bash scripts/install_macos.sh
```

By default the installer and app launcher free `SANKALP_PORT` before starting Sankalp. Set
`SANKALP_SKIP_PORT_KILL=1` while installing if you want to handle occupied ports yourself.
When you run `bash scripts/install_macos.sh` from a local checkout, the installer copies that
checkout into `~/.sankalp/app` so uncommitted local changes can be tested before publishing
the curl installer.

### Development Install

Clone or enter the repo:

```sh
cd /Users/rswai/sankalp
```

Install WebUI dependencies:

```sh
cd web
source ~/.nvm/nvm.sh
nvm use
npm install
```

## Run

Start the Sankalp backend in one terminal:

```sh
cd /Users/rswai/sankalp
python3 server.py
```

The backend listens on:

```text
http://127.0.0.1:8765
```

Start the WebUI in a second terminal:

```sh
cd /Users/rswai/sankalp/web
source ~/.nvm/nvm.sh
nvm use
npm run dev -- --port 5173
```

Open:

```text
http://127.0.0.1:5173
```

The WebUI proxies `/api/*` to the backend at `http://127.0.0.1:8765`.

For installed app usage, run `cd web && npm run build` once and open
`http://127.0.0.1:8765`; the Python backend serves the built WebUI directly.

## First Setup

Open Settings from the gear icon.

Provider tab:

- `Local fallback`: no external model call; useful for testing.
- `OpenAI-compatible endpoint`: use llama.cpp, Ollama, LM Studio, vLLM, OpenRouter, or
  another `/v1/chat/completions` server.
- `Codex CLI`: uses your local Codex login.
- `Gemini API`: uses a Gemini API key.
- `OpenAI API`: uses an OpenAI API key.

For a llama.cpp-style local endpoint, set:

```text
Base URL: http://localhost:2276/v1
Model: the model name served by llama.cpp
```

Memory tab:

- Set an Obsidian vault path.
- Choose an optional workspace subfolder.
- Browse subfolders and notes.
- Open notes in Obsidian or folders in Finder.

Profile tab:

- Add your own user profile.
- Review or delete agent-inferred traits.

App tab:

- Relaunch with latest code when using the local macOS wrapper flow.

## Useful Environment Variables

- `SANKALP_HOST`: bind host, default `127.0.0.1`
- `SANKALP_PORT`: bind port, default `8765`
- `SANKALP_STATE_DIR`: runtime state, default `~/.sankalp`
- `SANKALP_OBSIDIAN_VAULT`: Markdown memory vault, default `~/.sankalp/obsidian-vault`
- `SANKALP_MODEL`: default OpenAI model, default `gpt-5.5`
- `OPENAI_API_KEY`: enables OpenAI-backed responses
- `GEMINI_API_KEY`: optional fallback for Gemini when no key is saved in UI settings
- `SANKALP_ALLOW_TERMINAL`: set to `1` to allow `/sh ...` commands
- `SANKALP_ALLOWED_ROOTS`: path list for file tools, separated by `:`

Provider settings and API keys are stored locally in:

```text
~/.sankalp/settings.json
```

## Chat Commands

Inside chat:

- `remember: <fact>` appends to the memory inbox
- `/fetch https://example.com` fetches and extracts page text
- `/read path/to/file` reads a file within allowed roots
- `/append path/to/file :: text` appends text within allowed roots
- `/sh command` runs a terminal command only when terminal access is enabled

## Data Locations

Runtime state:

```text
~/.sankalp/
```

Sessions:

```text
~/.sankalp/sessions/
```

Default memory vault:

```text
~/.sankalp/obsidian-vault/
```

Memory follows an append-first structure:

```text
People/you.md
Projects/
Sessions/
Skills/
Inbox/
Decisions/
```

## macOS Full Disk Access

If your Obsidian vault is under protected locations such as `~/Documents`, macOS may block
access when Sankalp is launched from a terminal. Grant Full Disk Access to the app or
terminal process that runs Sankalp.

The Memory tab has a Full Disk Access shortcut when macOS support is available.

## Development Checks

Backend checks:

```sh
python3 -m unittest tests/test_sessions.py tests/test_settings.py
```

WebUI checks:

```sh
cd web
source ~/.nvm/nvm.sh
nvm use
npm run check
npm run build
```

## Docs

- [Architecture](docs/architecture.md)
- [Features](docs/features.md)
- [MVP spec](docs/MVP_SPEC.md)
- [WebUI notes](web/README.md)
