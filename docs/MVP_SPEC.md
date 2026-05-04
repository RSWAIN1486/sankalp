# Sankalp MVP Spec

## Goal

Build a personal assistant that can chat, use a small set of tools, and remember durable
facts in an Obsidian-readable vault without hiding memory in opaque state.

## Architecture

1. Agent core
   - Receives a user turn.
   - Retrieves relevant memory snippets.
   - Routes explicit tool commands.
   - Calls an optional model adapter for normal chat.
   - Logs every tool call to the session.

2. Tools
   - `memory_remember`: append durable captures to Obsidian inbox.
   - `browser_fetch`: fetch and extract page text from a URL.
   - `file_read`: read files under configured roots.
   - `file_append`: append to files under configured roots.
   - `terminal`: disabled by default; explicit opt-in required.

3. Memory
   - Obsidian is the human-readable source of truth.
   - JSON session state is operational memory.
   - Writes are append-first. Promotion is a separate operation.
   - Retrieval is lightweight keyword scoring for v1.

4. UI
   - Chat transcript.
   - Activity log.
   - Full-screen memory viewer.
   - Session list on the chat screen.
   - Full-screen user profile editor.
   - Full-screen provider settings with provider-specific fields.

## Memory Schema

```text
<vault>/
  People/you.md
  Projects/
  Sessions/YYYY-MM-DD-<session-id>.md
  Skills/
  Inbox/YYYY-MM-DD.md
  Decisions/
```

## Permission Model

- The HTTP server binds to loopback by default.
- File tools are limited to configured roots.
- Terminal execution is disabled unless `SANKALP_ALLOW_TERMINAL=1`.
- Tool calls are recorded with input, output summary, status, and timestamp.

## First Milestone

The first milestone is complete when the assistant can:

- Start locally with no build step.
- Persist sessions.
- Capture `remember:` facts into Obsidian Markdown.
- Retrieve memory snippets before answering.
- Show tool activity in the UI.
- Run tests for memory and tool safety.
- Configure Gemini or Codex from the UI.
- Configure an OpenAI-compatible `/v1` endpoint from the UI.
- Edit user-authored profile memory and delete wrong inferred traits.
