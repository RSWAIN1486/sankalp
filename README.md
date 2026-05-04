# Sankalp

Sankalp is a local-first personal assistant runtime with durable, human-readable memory.

The v1 shape is intentionally small:

- A browser chat UI
- JSON session history
- Obsidian-compatible Markdown memory
- A visible activity/tool log
- Conservative local tools
- Local settings for Local fallback, OpenAI-compatible endpoint, Codex CLI, Gemini API,
  or OpenAI API providers
- A user profile panel backed by `People/you.md`

## Run

```sh
python3 server.py
```

Then open <http://127.0.0.1:8765>.

## Useful Environment Variables

- `SANKALP_HOST`: bind host, default `127.0.0.1`
- `SANKALP_PORT`: bind port, default `8765`
- `SANKALP_STATE_DIR`: runtime state, default `~/.sankalp`
- `SANKALP_OBSIDIAN_VAULT`: Markdown memory vault, default `~/.sankalp/obsidian-vault`
- `SANKALP_MODEL`: OpenAI model, default `gpt-5.5`
- `OPENAI_API_KEY`: enables model-backed responses
- `GEMINI_API_KEY`: optional fallback for Gemini when no key is saved in UI settings
- `SANKALP_ALLOW_TERMINAL`: set to `1` to allow `/sh ...` commands
- `SANKALP_ALLOWED_ROOTS`: path list for file tools, separated by `:`

Provider settings can also be configured from the Settings icon in the UI. API keys are
stored locally in `~/.sankalp/settings.json`.

For local or hosted OpenAI-compatible runtimes, set provider to `OpenAI-compatible endpoint`,
choose a preset or enter a base URL such as `http://localhost:2276/v1`, and provide the
model name exposed by that runtime. Sankalp calls `<base-url>/chat/completions`.

## MVP Commands

Inside chat:

- `remember: <fact>` appends to the memory inbox
- `/fetch https://example.com` fetches and extracts page text
- `/read path/to/file` reads a file within allowed roots
- `/append path/to/file :: text` appends text within allowed roots
- `/sh command` runs a terminal command only when terminal access is enabled

Memory follows the append-first rule. Raw captures go to `Inbox/`, session traces go to
`Sessions/`, and curated notes can be promoted manually or by a later summarizer.

## User Profile

The profile icon opens `People/you.md` as structured profile memory:

- `User-authored profile`: your own description of yourself and your preferences.
- `Agent-inferred traits`: low-confidence traits inferred from conversation.

Inferred traits are stored as separate Markdown blocks so you can delete wrong traits from
the UI without deleting the whole profile.

## Obsidian Vault Sync

The Memory screen can point Sankalp at a real Obsidian vault and an optional workspace
subfolder inside that vault. On macOS, Obsidian vaults under `~/Documents` may require Full
Disk Access for the terminal process running Sankalp. If access is blocked, the UI shows the
permission error and keeps the app running.

Once the vault is readable, the workspace selector is populated from the vault's folder
tree. Selecting a folder shows its immediate subfolders and notes. Markdown notes can be
opened directly in Obsidian; folders open in Finder because Obsidian's public URI scheme is
file-oriented.

On macOS, use the Memory screen to install `~/Applications/Sankalp.app` and open System
Settings > Privacy & Security > Full Disk Access. Grant access to `Sankalp.app`, then quit
the terminal-run server and launch Sankalp from the app so macOS attributes vault reads to
the app.

The Settings screen includes `Relaunch with latest code`, which reinstalls the app wrapper
from the current repo and restarts the backend.
