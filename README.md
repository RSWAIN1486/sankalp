# Sankalp

Sankalp is a local-first AI assistant with a professional WebUI, auditable tool activity, and Obsidian-compatible memory.

## What This Repo Contains

- Python backend for local APIs, chat orchestration, providers, tools, sessions, and memory.
- SvelteKit + TypeScript WebUI for chat, settings, memory browsing, and app controls.

## Core Features

- Streaming chat responses with session history.
- Multiple providers (`local`, `local_openai`, `codex`, `gemini`, `openai`).
- Obsidian-compatible memory with `/remember` and memory search.
- Tooling for web fetch/search and safe local file actions.
- Local installed app flow with in-app update checks.

## Install

### macOS (recommended)

```sh
curl -fsSL https://raw.githubusercontent.com/RSWAIN1486/sankalp/main/scripts/install_macos.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/RSWAIN1486/sankalp/main/scripts/install_windows.ps1 | iex
```

### Linux / Manual Dev Install

```sh
git clone https://github.com/RSWAIN1486/sankalp.git
cd sankalp
python3 server.py
```

In another terminal:

```sh
cd web
source ~/.nvm/nvm.sh
nvm install 24
nvm use 24
npm install
npm run dev
```

## Open Sankalp

- Installed app mode: `http://127.0.0.1:8765`
- WebUI dev mode: `http://127.0.0.1:5173`

## First-Time Setup

Open `Settings` in the app and configure:

- Provider and model
- Obsidian vault path (optional but recommended)
- Profile preferences

## Data and Privacy

Sankalp is local-first by default. Runtime data is stored under:

- `~/.sankalp/` (macOS/Linux)
- `%USERPROFILE%\.sankalp\` (Windows)

## Useful Commands

- `/remember <text>`: save a memory note
- `/research <query>`: web research flow
- `/fetch <url>`: fetch and summarize page content

## Documentation

Detailed feature behavior, architecture, and advanced setup will be hosted in the docs site.
For now:

- [Architecture](docs/architecture.md)
- [Features](docs/features.md)
- [MVP Spec](docs/MVP_SPEC.md)
