# Sankalp Architecture

Sankalp is a local-first personal assistant with auditable memory. The current backend uses
one Python stdlib HTTP server, JSON session files, Obsidian-compatible Markdown memory,
explicit local tools, provider adapters, and JSON/SSE APIs.

The product direction is now a professional WebUI and durable backend architecture. The
Python backend is API-only; the `web/` SvelteKit app is the browser UI and consumes the
existing `/api/*` routes.

## Components

- `sankalp/server.py`: loopback HTTP server, JSON APIs, SSE chat route, and static
  serving for the built `web/build` app in installed-app mode.
- `sankalp/agent/core.py`: turn orchestration, explicit command routing, memory retrieval,
  memory-search intent routing, session updates, edit/resend branching, and background
  generated titles.
- `sankalp/agent/llm.py`: provider adapters for local fallback, OpenAI-compatible endpoints,
  Codex CLI, Gemini API, and OpenAI API.
- `sankalp/sessions/store.py`: one JSON file per session under `~/.sankalp/sessions`.
- `sankalp/memory/obsidian.py`: Markdown vault schema, retrieval, profile memory, and
  Obsidian open helpers.
- `sankalp/tools/registry.py`: small explicit tools with structured logged results,
  including auditable Obsidian search.
- `web/`: SvelteKit/TypeScript frontend that follows the llama.cpp WebUI direction:
  routes, components, stores, services, and browser storage. It currently calls the existing
  backend APIs through the Vite dev proxy during development, and is served by the Python
  backend after `npm run build` for installed app usage.
- `web/src/lib/storage/db.ts`: Dexie/IndexedDB storage for browser-local UI state. The first
  stored data is composer preferences and cached session summaries. IndexedDB is not the
  source of truth for long-term memory.

## Frontend Migration

The WebUI is intentionally separated from the backend migration so it can be built and
reviewed incrementally.

```text
Svelte route
  -> App shell
  -> components
  -> chat store
  -> API service / Dexie storage
  -> existing /api/* backend
```

Current frontend layers:

- `web/src/routes/+page.svelte`: bootstraps the WebUI and loads initial API state.
- `web/src/lib/components/*`: chat shell, collapsible sidebar, message list, composer,
  inline activity details, and settings drawer.
- `web/src/lib/stores/chat.ts`: session/message/tool state, chat streaming orchestration,
  composer preferences, and sidebar filtering.
- `web/src/lib/services/api.ts`: typed JSON fetch helper and SSE parser.
- `web/src/lib/storage/db.ts`: Dexie database for local UI cache and preferences.

The design choice is to keep the current backend stable while replacing the UI foundation.
This avoids a combined frontend/backend rewrite and lets the professional shell prove the
data contracts before SQLite and typed backend routes are introduced.

Installed app mode uses a single loopback origin. The WebUI is built into `web/build`, and
`sankalp/server.py` serves that static bundle with SPA fallback while keeping `/api/*`
reserved for JSON and SSE routes. The curl installer at `scripts/install_macos.sh` clones or
updates the app checkout under `~/.sankalp/app`, installs/builds the WebUI, frees the
configured backend port, creates `~/Applications/Sankalp.app`, and opens it. The app wrapper
also frees the configured port before launching the Python backend when no healthy Sankalp
server is already listening. When the installer is run from a local checkout instead of curl,
it mirrors that working tree into `~/.sankalp/app` before building so local changes can be
validated without first pushing to GitHub. The default `~/.sankalp/app` checkout is treated
as managed application code: curl updates reset it to `origin/main` so upgrades recover from
dirty local test installs, while user state remains in sibling `~/.sankalp` data folders.

The WebUI navigation follows a minimal chat-tool model: primary navigation stays in the
collapsible left sidebar, the top bar only exposes settings, and detailed surfaces move into
a settings drawer. The drawer carries provider setup, Obsidian memory configuration, user
profile, and app relaunch controls. The Memory nav item opens the settings drawer directly
on the memory tab, where the UI can browse workspace children, preview notes recursively,
and open notes or folders through the existing `/api/memory/open` helper. Tool activity is
not shown as a right sidebar; it appears as a collapsible Markdown-rendered block above the
latest assistant message when the session has tool calls.

Message and session actions are handled in the WebUI against the existing backend contracts.
Message copy uses the browser clipboard, edit/regenerate reuse `/api/chat/stream` with the
backend `edit_index` path, and branch deletion persists through `/api/session/truncate`,
which removes the selected message and all later messages from the JSON session. Conversation
rename/delete call the existing session APIs, while export is a browser-side Markdown
download built from `/api/session`.

## Flow

```text
Browser
  -> SvelteKit WebUI
  -> /api/chat/stream
  -> Agent.turn
  -> SessionStore get/create
  -> append user turn
  -> route explicit tool or call LLMAdapter
  -> append assistant turn
  -> stream status/session/delta/done events
```

The synchronous `/api/chat` route remains as a simple JSON fallback. The UI uses
`/api/chat/stream` for thinking status and progressive assistant rendering. Provider-native
token streaming can be added later behind the same SSE event contract.

Session titles use an immediate deterministic fallback, then a background title call updates
the session. The title call ignores the chat message's selected provider/model and chooses
the smallest configured title-capable provider globally: OpenAI `gpt-5.4-nano` first,
Gemini `gemini-2.5-flash-lite` second, then the configured OpenAI-compatible endpoint.
Manual renames are preserved.

## Memory

Obsidian is the human-readable long-term layer. JSON sessions are operational state.

```text
People/you.md
Projects/
Sessions/YYYY-MM-DD-<session-id>.md
Skills/
Inbox/YYYY-MM-DD.md
Decisions/
```

Writes are append-first. `remember:` captures go to `Inbox/`; chat turns go to `Sessions/`;
profile edits and inferred traits go to `People/you.md`. Deleting a chat session removes
the JSON session and matching `Sessions/YYYY-MM-DD-<session-id>.md` Obsidian transcript.
Retrieval is lightweight keyword scoring for now.

When the user explicitly asks to search, check, retrieve, or find something in memory,
`Agent.turn` routes the request through the `memory_search` tool before any model call.
Before searching, the configured model rewrites the user request into a concise memory
search query; if that rewrite is unavailable, Sankalp falls back to the raw user wording.
The tool searches the configured Obsidian vault across knowledge folders, intentionally
skipping `Sessions/` because that folder stores chat transcripts rather than promoted
memory. Search scores note text plus folder and file names, logs the rewritten query, the
original user query, vault status, and matching snippets in `session.tool_calls`, then
filters weak matches before giving evidence to a model. This keeps local models from being
distracted by loosely related notes. For OpenAI-compatible local grounded-memory answers,
Sankalp requests deterministic temperature-zero output. If the user is only checking whether
memory exists, the agent confirms yes or no, cites the matched paths, and asks what the user
wants to inspect next. Normal chat still receives lightweight retrieved context without
forcing a visible tool call, keeping everyday turns simple while making memory-audit
requests explicit.

Tool routing is intentionally two-step. Cheap deterministic commands and regex checks run
first for obvious intents such as `remember:` and "in my memory". If those do not select a
tool, the configured LLM may choose from a small safe-read catalog: `memory_search`,
`browser_fetch`, or `file_read`. Write and terminal tools remain explicit commands because
LLM selection is useful for wording flexibility, not for hidden side effects.

## Providers

Settings store provider configuration locally in `~/.sankalp/settings.json`, with API keys
masked from normal reads. In the `web/` UI, browser-local UI state lives in Dexie/IndexedDB
so drafts, cached sessions, attachment metadata, and preferences can share one local storage
layer.

Native providers today:

- `local`
- `local_openai`
- `codex`
- `gemini`
- `openai`

## Constraints

- HTTP binds to loopback by default.
- File tools are limited to configured roots.
- Terminal execution is disabled unless explicitly enabled.
- Tool calls are logged with input, output, status, and timestamps.
- macOS Full Disk Access must be granted to `Sankalp.app` for protected vault locations.

## Documentation Rule

Keep this file minimal. Update it only when the structure, flow, boundaries, storage, or
provider architecture changes. Put user-facing capability details in `docs/features.md`.
