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
- `sankalp/skills/registry.py`: scans `~/.sankalp/skills` for folder-backed skills with
  `skill.json` manifests and `SKILL.md` entrypoints.
- `sankalp/updater.py`: explicit app update checks against the stable GitHub manifest and
  confirmed installer launches.
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
  composer preferences, provider-scoped model selection, model catalog loading, and sidebar
  filtering.
- `web/src/lib/services/api.ts`: typed JSON fetch helper and SSE parser.
- `web/src/lib/storage/db.ts`: Dexie database for local UI cache and preferences.
- `web/scripts/check-node-version.mjs`: runtime guard invoked by npm pre-scripts so local
  development/build commands fail fast with actionable guidance when Node does not satisfy
  the Vite/Svelte plugin requirement (`20.19+` or `22.12+`).
- `scripts/relaunch_dev.sh`: macOS dev helper that kills existing backend/frontend listeners
  on configured ports, then relaunches both local servers and records PID/log files under
  `.dev-logs/`.

The design choice is to keep the current backend stable while replacing the UI foundation.
This avoids a combined frontend/backend rewrite and lets the professional shell prove the
data contracts before SQLite and typed backend routes are introduced.

## Agent Home

`~/.sankalp` is Sankalp's local agent home. Managed application code lives under
`~/.sankalp/app`; user-owned data lives in sibling folders and must survive reinstall,
update, and managed checkout resets.

```text
~/.sankalp/
  app/              # managed app checkout
  settings.json     # local settings and provider config
  SOUL.md           # editable persona file loaded into LLM prompts
  state.db          # future SQLite operational state
  sessions/         # JSON session state today
  skills/           # installed folder-backed skills
  hooks/            # future user/system hooks
  logs/             # launcher/backend logs
  cache/            # runtime caches
  sandboxes/        # future isolated tool workspaces
  memories/         # future memory indexes
  obsidian-vault/   # human-readable Markdown memory
  webui/            # browser/UI runtime cache
  tools/            # future user-installed tool adapters
```

Each skill is a folder with `skill.json`, `DESCRIPTION.md`, `SKILL.md`, and optional
`setup.md`, `scripts/`, `examples/`, or `assets/`. Startup seeds bundled default skills
into `~/.sankalp/skills` only when the target skill folder does not already exist, so user
edits are not overwritten.

`SOUL.md` is also user-owned. `LLMAdapter` reads it fresh while building the developer
prompt, strips the default comment-only template, and appends non-empty persona text to the
normal Sankalp system behavior.

Installed app mode uses a single loopback origin. The WebUI is built into `web/build`, and
`sankalp/server.py` serves that static bundle with SPA fallback while keeping `/api/*`
reserved for JSON and SSE routes. The curl installer at `scripts/install_macos.sh` clones or
updates the app checkout under `~/.sankalp/app`, installs/builds the WebUI, frees the
configured backend port, creates `~/Applications/Sankalp.app`, and opens it. The app wrapper
also frees the configured port before launching the Python backend when no healthy Sankalp
server is already listening. When the installer is run from a local checkout instead of curl,
it mirrors that working tree into `~/.sankalp/app` before building so local changes can be
validated without first pushing to GitHub. The default `~/.sankalp/app` checkout is treated
as managed application code: curl updates clean tracked and untracked git changes before
branch switching, then reset to `origin/main` so upgrades recover from dirty local test
installs, while user state remains in sibling `~/.sankalp` data folders. For developer
diagnostics, `SANKALP_PRESERVE_LOCAL_CHANGES=1` skips the managed-clean behavior.
On macOS, installer onboarding checks whether Obsidian is installed and opens the official
download page when it is missing. Optional vault permission prompting can be enabled during
install with `SANKALP_OBSIDIAN_ONBOARD=prompt`, which asks the user to choose the vault
folder and persists that path into local settings.
When Obsidian is present, Sankalp auto-detects the best available vault from Obsidian's
registry (open vault first, then other accessible vaults) and stores that path for memory
sync. Users can still change the vault path manually in Settings at any time.
Windows now follows the same managed-install contract through
`scripts/install_windows.ps1`: installs into `%USERPROFILE%\.sankalp\app`, treats that
checkout as resettable managed app code on updates, keeps runtime state in sibling folders
under `%USERPROFILE%\.sankalp`, and creates a local launcher/Start Menu shortcut. The Windows
installer mirrors Obsidian onboarding by checking install status, opening the official
download page if missing, and auto-detecting accessible vault paths from Obsidian metadata.
Both installers migrate legacy `sankalp` app/home folders into the `~/.sankalp` agent-home
layout before building. On Windows the managed app checkout now also defaults to
`%USERPROFILE%\.sankalp\app`; older `%LOCALAPPDATA%\Sankalp\app` installs are moved into
that location when possible.

App updates are release-manifest driven rather than commit-driven. `update.json` is the
stable channel contract; bump its `version` and `sankalp.__version__` only for changes worth
surfacing to installed users. The WebUI checks `/api/app/update` at startup using a daily
browser cache, shows a small header signal and dismissible banner when the remote manifest
is newer, and keeps the detailed release notes plus the confirmed `Update and relaunch`
action in Settings -> App. The update action starts the installer in the background, which
dispatches to the platform installer in the background (macOS shell installer or Windows
PowerShell installer). That installer resets managed app code to GitHub `main`, rebuilds the
WebUI, refreshes launcher artifacts, relaunches the app, and skips first-run onboarding
prompts. The running browser tab waits until the old backend goes away, then reloads only
after `/api/health` responds again, avoiding early reloads against the stale bundle.
Release preparation is scripted in `scripts/release.sh`, which updates both `update.json`
and `sankalp.__version__` together and can auto-generate release notes from git commit
subjects since the previous release point.

The WebUI navigation follows a minimal chat-tool model: primary navigation stays in the
collapsible left sidebar, the top bar exposes settings and update availability, and detailed
surfaces move into a settings drawer. The drawer carries provider setup, Obsidian memory
configuration, user profile, and explicit app update controls (check update, update/relaunch,
restart, and quit local app). The Memory nav item opens the
settings drawer directly on the memory tab, where the UI can browse workspace children,
preview notes recursively, and open notes or folders through the existing `/api/memory/open` helper. Tool activity is
not shown as a right sidebar; it appears as a collapsible Markdown-rendered block above the
latest assistant message when the session has tool calls.
The settings drawer now follows standard sidebar behavior with a full-screen backdrop:
clicking outside the drawer closes it, while clicks inside the panel keep it open.
Provider settings also include an optional Streaming diagnostics toggle that persists in
IndexedDB and shows live SSE event counts and output/reasoning character totals so provider
stream cadence can be validated without external logs.
On macOS, the Memory panel also exposes explicit helpers to request vault folder access via
native folder picker, open Full Disk Access settings, and open the Obsidian download page
when Obsidian is not installed.

Message and session actions are handled in the WebUI against the existing backend contracts.
Message copy uses the browser clipboard, edit/regenerate reuse `/api/chat/stream` with the
backend `edit_index` path, and branch deletion persists through `/api/session/truncate`,
which removes the selected message and all later messages from the JSON session. Conversation
rename/delete call the existing session APIs, while export is a browser-side Markdown
download built from `/api/session`. The App tab exposes Quit and Restart controls: Quit
stops the loopback server and asks the browser tab to close, while Restart queues the
installed app launcher before shutting down the current backend. The conversation row menu (Edit/Export/Delete) is
rendered as a viewport-fixed anchored popover rather than inside the scroll container so
opening actions never mutates sidebar scrollbars or list layout.
Composer submission now defaults to `Enter` to send and `Shift+Enter` to insert a newline.

## Flow

```text
Browser
  -> SvelteKit WebUI
  -> /api/chat/stream
  -> Agent.turn_stream
  -> SessionStore get/create
  -> append user turn
  -> route explicit tool or call LLMAdapter.stream_complete
  -> append assistant turn
  -> stream status/reasoning/delta/session/done events
```

The synchronous `/api/chat` route remains as a simple JSON fallback. The UI uses
`/api/chat/stream` for thinking status and progressive assistant rendering. OpenAI Responses,
OpenAI-compatible chat providers, Gemini, and Codex now stream token deltas through this
route. Providers without native streaming still use the same SSE event contract and degrade
to a single final delta.

The message list now exposes live agent activity in a collapsible inline panel on the latest
assistant message. While a response is pending, the panel accumulates `reasoning` stream
events as "Live thinking"; after completion, tool-call activity is shown in the same panel.

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

Writes are append-first. `/remember` captures go to `Inbox/`; chat turns go to `Sessions/`;
profile edits and inferred traits go to `People/you.md`. Deleting a chat session removes
the JSON session and matching `Sessions/YYYY-MM-DD-<session-id>.md` Obsidian transcript.
Retrieval is lightweight keyword scoring for now.

Slash memory capture is now standardized as `/remember ...` in the composer command flow.
Legacy `remember:` phrasing is still accepted for compatibility with older transcripts.

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
first for obvious intents such as `/remember` and "in my memory". If those do not select a
tool, the configured LLM may choose from a small safe-read catalog: `memory_search`,
`browser_fetch`, or `file_read`. Write and terminal tools remain explicit commands because
LLM selection is useful for wording flexibility, not for hidden side effects.

Capability discovery is explicit in the WebUI. The backend exposes `/api/capabilities`
for a typed list of features, folder-backed skills, tools, and slash commands.
`Settings -> Capabilities` renders that list, while the composer shows inline slash-command
suggestions when a draft begins with `/`, with keyboard selection and click-to-insert for
fast command usage.

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

The composer treats provider and model as a pair. Model options are loaded through
`/api/models?provider=...` and cached in frontend state by provider, while the selected
model is remembered per provider in Dexie. Switching from a local OpenAI-compatible runtime
to Codex, Gemini, or OpenAI therefore selects that provider's configured or listed model
instead of carrying the previous provider's model string into the new request. The
OpenAI-compatible provider also attempts `<base-url>/models` and falls back to its configured
model when the runtime does not expose a model list.

## Constraints

- HTTP binds to loopback by default.
- File tools are limited to configured roots.
- Terminal execution is disabled unless explicitly enabled.
- Tool calls are logged with input, output, status, and timestamps.
- macOS Full Disk Access must be granted to `Sankalp.app` for protected vault locations.

## Documentation Rule

Keep this file minimal. Update it only when the structure, flow, boundaries, storage, or
provider architecture changes. Put user-facing capability details in `docs/features.md`.
