# Sankalp Architecture

## Overview

Sankalp is a local-first personal assistant with auditable memory. The current version
is a minimal MVP: one Python stdlib HTTP server, a small agent loop, explicit local tools,
JSON session storage, Obsidian-compatible Markdown memory, and a vanilla HTML/CSS/JS UI.

The design intentionally avoids a framework, background queue, database, bundler, or
plugin system until real usage proves those are needed.

## Components

### HTTP Server

Files:

- `server.py`
- `sankalp/server.py`

The root `server.py` only starts the app. `sankalp/server.py` owns request handling and
serves both JSON API routes and static assets.

Routes:

- `GET /` serves the UI.
- `GET /api/health` returns a health check.
- `GET /api/sessions` lists persisted sessions.
- `GET /api/session?id=<id>` loads one session transcript and tool log.
- `GET /api/memory` lists recent Markdown notes.
- `GET /api/memory/tree` returns a folder/note tree for the configured vault workspace.
- `GET /api/memory/folders` returns all folders for the workspace dropdown.
- `GET /api/memory/children?folder=<path>` returns immediate children of one folder.
- `GET /api/memory/notes?folder=<path>` returns recursive Markdown note previews.
- `GET /api/obsidian/vaults` discovers local Obsidian vault paths from Obsidian's macOS
  registry when available.
- `GET /api/macos/status` reports whether the local macOS app wrapper is installed.
- `GET /api/profile` reads `People/you.md` as structured profile memory.
- `GET /api/settings` reads provider settings with API keys masked.
- `POST /api/session/new` creates a session.
- `POST /api/chat` runs one agent turn.
- `POST /api/profile` updates the user-authored profile section.
- `POST /api/profile/trait/delete` removes one inferred trait block.
- `POST /api/settings` updates provider, model, and optional API key settings.
- `POST /api/macos/install-app` creates `~/Applications/Sankalp.app`.
- `POST /api/macos/open-full-disk-access` opens the macOS Full Disk Access settings pane.
- `POST /api/app/relaunch` reinstalls the app wrapper and restarts the backend.
- `POST /api/memory/open` opens a Markdown note in Obsidian or a folder in Finder.

Decision: stdlib HTTP is enough for the first milestone. A framework would add more
surface area before routing, auth, middleware, or async behavior need it.

### Agent

Files:

- `sankalp/agent/core.py`
- `sankalp/agent/llm.py`

The agent receives a user message, saves it to the active JSON session, appends the turn
to the Obsidian session note, and then either routes an explicit command or calls the LLM
adapter.

Explicit command routing exists for the MVP commands:

- `remember: <fact>`
- `/fetch <url>`
- `/read <path>`
- `/append <path> :: <text>`
- `/sh <command>`

Normal chat retrieves matching memory snippets and sends them to the model adapter. If
`OPENAI_API_KEY` is missing, the adapter returns a local fallback response so the app
still runs and memory/tool behavior can be tested.

The model adapter supports five providers:

- `local`: no network call, useful for testing memory and tools.
- `local_openai`: calls any OpenAI-compatible local, LAN, or hosted endpoint at
  `<base-url>/chat/completions`, for example `http://localhost:2276/v1`.
- `codex`: calls the local `codex exec` CLI in read-only, ephemeral mode. This uses the
  user's Codex login or plan instead of an OpenAI API key.
- `gemini`: calls the Gemini REST `generateContent` API with a saved Gemini API key or
  `GEMINI_API_KEY`.
- `openai`: calls the OpenAI Responses API with a saved OpenAI API key or `OPENAI_API_KEY`.

Settings intentionally show only the selected provider's fields. OpenAI-compatible
endpoints include presets for local runtimes and common API-key providers, but all route
through the same simple Chat Completions adapter.

Hermes provider setup research used:

- The Hermes AI Providers page, which lists provider setup through `hermes model`, API-key
  env vars, OAuth providers, and custom/self-hosted `/v1/chat/completions` endpoints.
- The Hermes CLI reference, which separates `hermes model` as the full provider setup
  wizard from in-chat `/model`, which only switches configured providers.

Sankalp does not try to replicate every Hermes provider natively yet. The UI presents a
provider setup guide for Hermes-style providers, while native Sankalp execution currently
supports local fallback, Codex CLI, Gemini API, OpenAI API, and OpenAI-compatible endpoints.
The guide covers the Hermes provider families documented online: OpenRouter, Nous Portal,
OpenAI Codex, GitHub Copilot, Anthropic, Gemini, Gemini OAuth, Qwen OAuth, Hugging Face,
Z.AI/GLM, Kimi, MiniMax, DeepSeek, NVIDIA, xAI, Ollama Cloud, Bedrock, AI Gateway,
OpenCode, Kilo Code, Xiaomi, Arcee, Alibaba, GMI Cloud, Tencent TokenHub, LM Studio, and
custom/self-hosted endpoints.

Decision: command routing is explicit string parsing for now. A tool-call planner or
schema-driven router would be premature before we know the real command surface.

### Sessions

Files:

- `sankalp/sessions/store.py`

Each session is one JSON file under `SANKALP_STATE_DIR/sessions`. The session contains
messages, tool calls, timestamps, title, and optional OpenAI `previous_response_id`.

Flow:

```text
POST /api/chat
  -> SessionStore.get/create
  -> append user message
  -> agent/tool/model work
  -> append assistant message
  -> SessionStore.save
```

Decision: JSON files are enough for single-user MVP persistence and are easy to inspect,
delete, and migrate.

### Memory

Files:

- `sankalp/memory/obsidian.py`

Memory is Markdown in an Obsidian-compatible vault. The vault defaults to
`~/.sankalp/obsidian-vault` and contains:

```text
People/
Projects/
Sessions/
Skills/
Inbox/
Decisions/
```

Write behavior is append-first:

- `remember:` writes raw durable captures to `Inbox/YYYY-MM-DD.md`.
- Every chat turn appends to `Sessions/YYYY-MM-DD-<session-id>.md`.
- `People/you.md` stores user profile memory with a user-authored section and separate
  agent-inferred trait blocks.
- Curated promotion into `People/`, `Projects/`, `Skills/`, or `Decisions/` is not
  automated yet.

Retrieval is simple keyword scoring over Markdown files.

The Memory UI can switch the vault path to a real Obsidian vault and optionally scope
browsing/retrieval to a workspace subfolder. On macOS, Obsidian's registry is read from
`~/Library/Application Support/obsidian/obsidian.json` to suggest known vaults. If the
process cannot read a vault because of macOS privacy permissions, the backend returns an
access error instead of crashing.

The workspace subfolder selector is generated from readable vault directories. The right
folder panel shows immediate subfolders of the selected workspace as wide cards. A
recursive `View all notes` modal previews notes across the selected folder and its
subfolders. Markdown notes are opened with
`obsidian://open?vault=<vault-name>&file=<note-path>`; folders open in Finder because
Obsidian does not provide a stable public URI for focusing a folder in the file explorer.

For macOS privacy, Sankalp can install a lightweight app wrapper at
`~/Applications/Sankalp.app`. Full Disk Access must still be granted manually by the user;
Sankalp can only open the System Settings pane. To make the grant apply to vault reads, the
server should be launched from `Sankalp.app`, not from Terminal.

Settings exposes an app-management action to relaunch with the latest repo code. It writes
the current app bundle, starts a delayed replacement process through `Sankalp.app`, and then
exits the current backend.

Agent-inferred profile traits are intentionally low-confidence. The agent adds a trait
only for simple first-person signals such as "I prefer..." or "I like...". Each trait is
wrapped in comments like `<!-- sankalp:trait <id> -->`, allowing the UI to delete one
incorrect inference without rewriting the whole note.

Decision: Obsidian is the human-readable long-term layer. Keyword retrieval is intentionally
simple until usage shows whether embeddings or a database index are needed.

### Tools

Files:

- `sankalp/tools/base.py`
- `sankalp/tools/registry.py`

Tools return one structured `ToolResult` with name, status, input, output, and timestamps.
The agent stores those results in the session tool log for UI visibility.

Current tools:

- `memory_remember`
- `browser_fetch`
- `file_read`
- `file_append`
- `terminal`

Constraints:

- File tools are limited to `SANKALP_ALLOWED_ROOTS`; if unset, they are limited to the
  repo root and the memory vault.
- Terminal is blocked unless `SANKALP_ALLOW_TERMINAL=1`.
- Browser fetch accepts only `http://` and `https://` URLs.

Decision: one registry class is enough for the first tool set. A deeper tool interface was
removed because there are no independently loaded tool implementations yet.

### UI

Files:

- `sankalp/static/index.html`
- `sankalp/static/style.css`
- `sankalp/static/app.js`

The UI uses one left icon rail and separate full main screens:

- Chat: session list, transcript, composer, activity, and provider status.
- User Profile: profile editor plus deletable inferred traits.
- Memory: full-page recent-note viewer.
- Memory: vault source, discovered vaults, workspace folder tree, and recent notes.
- Settings: provider selection, provider-specific fields, and setup guide.
- Settings: provider setup plus app relaunch controls.

The frontend uses plain browser APIs and no build step.

Decision: this matches the minimal web UI goal and keeps iteration easy. A component
framework can be introduced later only if UI complexity starts to justify it.

## Data Flow

```text
User message
  -> browser POST /api/chat
  -> Agent.turn
  -> SessionStore appends user message
  -> ObsidianMemory appends session note
  -> explicit tool command OR memory retrieval + LLMAdapter
  -> SessionStore appends assistant message and tool calls
  -> browser renders transcript, activity log, and recent memory
```

## Dependencies

Runtime dependencies:

- Python standard library
- macOS `open` command for the optional Full Disk Access helper

Optional external dependency:

- OpenAI Responses API when `OPENAI_API_KEY` is set
- OpenAI-compatible endpoint when provider is set to `local_openai`
- Gemini API when a Gemini key is configured
- Local Codex CLI when provider is set to `codex`

Development dependencies:

- Python `unittest`, from the standard library

## Current Principle Check

The MVP follows the minimal-first principles in `~/.codex/AGENTS.md` in these ways:

- No web framework, frontend framework, bundler, database, or background worker.
- Small modules with clear boundaries: agent, memory, sessions, tools, server, UI.
- Explicit data flow and command routing.
- Local files are inspectable and easy to delete or migrate.
- Tests cover the riskiest first behaviors: memory writes, retrieval, agent routing,
  file-root blocking, and terminal blocking.

Known tradeoffs:

- The package layout is slightly more modular than a single-file prototype. This is
  justified because the user's target architecture already separates agent, tools,
  memory, sessions, and UI, and each module is still small.
- Memory retrieval is basic keyword scoring. This is deliberately simpler than embeddings
  and should be replaced only after real usage shows retrieval quality is insufficient.
- Tool commands are manually parsed strings. This is enough for the MVP and avoids a
  speculative planner.

## Next Cleanup Candidates

- Add a memory promotion workflow from `Inbox/` into curated notes.
- Add a real approval queue if terminal/file writes become interactive rather than env gated.
- Add auth only if binding beyond loopback or exposing the server to other users.
