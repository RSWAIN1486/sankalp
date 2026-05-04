# Sankalp Architecture

Sankalp is a local-first personal assistant with auditable memory. The MVP uses one Python
stdlib HTTP server, JSON session files, Obsidian-compatible Markdown memory, explicit local
tools, provider adapters, and a vanilla HTML/CSS/JS UI.

The project stays intentionally small: no frontend framework, database, queue, bundler, or
plugin runtime until usage proves the need.

## Components

- `sankalp/server.py`: loopback HTTP server, static UI, JSON APIs, and SSE chat route.
- `sankalp/agent/core.py`: turn orchestration, explicit command routing, memory retrieval,
  session updates, edit/resend branching, and background generated titles.
- `sankalp/agent/llm.py`: provider adapters for local fallback, OpenAI-compatible endpoints,
  Codex CLI, Gemini API, and OpenAI API.
- `sankalp/sessions/store.py`: one JSON file per session under `~/.sankalp/sessions`.
- `sankalp/memory/obsidian.py`: Markdown vault schema, retrieval, profile memory, and
  Obsidian open helpers.
- `sankalp/tools/registry.py`: small explicit tools with structured logged results.
- `sankalp/static/*`: chat, profile, memory, and settings UI.

## Flow

```text
Browser
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
profile edits and inferred traits go to `People/you.md`. Retrieval is lightweight keyword
scoring for now.

## Providers

Settings store provider configuration locally in `~/.sankalp/settings.json`, with API keys
masked from normal reads. Composer-level provider/model/reasoning choices are stored in
browser local storage so refreshes keep the chat selection without changing saved Settings.

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
