# Sankalp

Sankalp is a local-first personal assistant runtime with durable, human-readable memory.

The v1 shape is intentionally small:

- A browser chat UI
- JSON session history
- Obsidian-compatible Markdown memory
- A visible activity/tool log
- Conservative local tools
- Optional OpenAI Responses API support via `OPENAI_API_KEY`

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
- `SANKALP_ALLOW_TERMINAL`: set to `1` to allow `/sh ...` commands
- `SANKALP_ALLOWED_ROOTS`: path list for file tools, separated by `:`

## MVP Commands

Inside chat:

- `remember: <fact>` appends to the memory inbox
- `/fetch https://example.com` fetches and extracts page text
- `/read path/to/file` reads a file within allowed roots
- `/append path/to/file :: text` appends text within allowed roots
- `/sh command` runs a terminal command only when terminal access is enabled

Memory follows the append-first rule. Raw captures go to `Inbox/`, session traces go to
`Sessions/`, and curated notes can be promoted manually or by a later summarizer.
