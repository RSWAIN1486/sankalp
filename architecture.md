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
- `GET /api/profile` reads `People/you.md` as structured profile memory.
- `GET /api/settings` reads provider settings with API keys masked.
- `POST /api/session/new` creates a session.
- `POST /api/chat` runs one agent turn.
- `POST /api/profile` updates the user-authored profile section.
- `POST /api/profile/trait/delete` removes one inferred trait block.
- `POST /api/settings` updates provider, model, and optional API key settings.

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
- `local_openai`: calls any OpenAI-compatible local or LAN endpoint at
  `<base-url>/chat/completions`, for example `http://localhost:2276/v1`.
- `codex`: calls the local `codex exec` CLI in read-only, ephemeral mode. This uses the
  user's Codex login or plan instead of an OpenAI API key.
- `gemini`: calls the Gemini REST `generateContent` API with a saved Gemini API key or
  `GEMINI_API_KEY`.
- `openai`: calls the OpenAI Responses API with a saved OpenAI API key or `OPENAI_API_KEY`.

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

The UI has three regions:

- Left icon rail for Chat, User Profile, Memory, and Settings
- Session list / profile editor / memory viewer / settings panel
- Chat transcript and composer
- Activity and provider status panel

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

Optional external dependency:

- OpenAI Responses API when `OPENAI_API_KEY` is set
- OpenAI-compatible local endpoint when provider is set to `local_openai`
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
