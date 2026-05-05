# Sankalp Features

## Chat

- Chat sessions persist as JSON files.
- New sessions get an immediate short fallback title, then an async global small-model title
  update.
- Title generation uses the smallest configured title-capable provider globally, starting
  with OpenAI `gpt-5.4-nano`, instead of the provider/model selected for the chat message.
- Auto-generated titles are capped to five words, and manual session renames are never
  overwritten.
- Sessions can be renamed or deleted from the left rail.
- Deleting a session also deletes its matching Obsidian transcript from `Sessions/`.
- User messages can be edited and resent; Sankalp branches from that turn and drops later
  stale messages before generating a replacement response.
- User messages expose copy and edit actions at the bottom-right of the bubble on hover.
- The chat route streams status, session metadata, text chunks, and final payload events.
- Assistant responses render lightweight Markdown: paragraphs, bullets, numbered lists,
  links, inline code, code blocks, and headings.

## Composer

- Attach `.md`, `.txt`, `.pdf`, and image files.
- Text and Markdown attachments are added as text context.
- Images and PDFs are sent inline to providers that support media inputs.
- Select provider, model, and reasoning effort per message.
- Last selected composer provider, model, and reasoning effort are remembered across refreshes.
- Context usage is estimated client-side from transcript text, draft text, and attachments.

## Providers

- Local fallback works with no model key.
- OpenAI-compatible endpoint supports local or hosted `/v1/chat/completions` runtimes.
- Codex CLI uses local `codex login` and `codex exec`.
- Gemini API uses a saved Gemini key or `GEMINI_API_KEY`.
- OpenAI API uses a saved OpenAI key or `OPENAI_API_KEY`.
- Settings show only fields relevant to the selected provider.
- Model dropdowns load from live provider APIs/CLI when available and fall back to curated
  defaults.
- `Test hello` verifies the selected provider/model/key/endpoint without creating a chat
  session.

## Memory

- Obsidian-compatible Markdown vault.
- Configurable vault path and optional workspace subfolder.
- Recent note list, top-level workspace dropdown, folder cards, and recursive note preview.
- Notes can open directly in Obsidian.
- Folders open in Finder.
- `People/you.md` stores user-authored profile memory.
- Agent-inferred traits are separate, low-confidence, and individually deletable.
- `remember:` appends durable facts to the inbox.
- Memory lookup searches the whole configured vault, skips `Sessions/`, and matches both
  note contents and folder/file names.
- Memory lookup asks the configured model to rewrite the user request into a concise search
  query before searching, then logs both the rewritten and original query.
- Memory lookup response style follows the query: existence checks return yes/no plus
  source paths and a follow-up prompt; specific questions are answered from the notes.
- Memory lookup filters weak matches before model answering, and local OpenAI-compatible
  grounded answers use deterministic output to reduce drift.
- Assistant messages that mention Obsidian `.md` note paths show open-note controls that
  launch the note through the same Obsidian open endpoint used by the Memory tab.

## Tools

- `memory_remember`
- `memory_search`
- `browser_fetch`
- `file_read`
- `file_append`
- `terminal`, disabled by default

Every tool call is logged into the session activity trace. Obvious commands are routed
deterministically first. If no deterministic route matches, the configured model can choose
from safe read/search tools before normal chat.

## macOS App

- One-command curl installer clones or updates Sankalp, builds the WebUI, installs
  `~/Applications/Sankalp.app`, and opens it.
- Installed app mode serves the built WebUI and backend API from one local loopback port.
- The installer and app wrapper free the configured Sankalp port before starting when needed.
- Installs a lightweight `~/Applications/Sankalp.app` wrapper.
- Opens the Full Disk Access settings pane.
- Relaunches the app-backed server with latest repo code from Settings.
