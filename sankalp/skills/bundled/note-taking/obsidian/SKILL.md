# Obsidian Memory

Use Sankalp's configured Obsidian vault as the human-readable long-term memory layer.

## Behavior

- Save explicit durable facts with `/remember <fact>`.
- `/remember` and natural save requests route to the best matching folder/note in the vault and create missing folders/notes when needed.
- Prefer existing semantic folders over `Inbox`; when no existing folder fits, create a concise new top-level folder under the vault.
- Save the durable note body only. Do not save conversational wrappers, tool/provider metadata, or "ready-to-paste" draft framing.
- Optional explicit routing syntax:
  - `folder: Research/JEPA`
  - `note: V-JEPA-reading-notes.md`
- Search promoted memory with `memory_search`.
- Keep chat transcripts in `Sessions/` separate from promoted memory.
- Treat Markdown files as user-owned and preserve readable note structure.

## Setup

- Configure `obsidian_vault_path` in Sankalp settings.
- Optionally configure `obsidian_workspace_path` to focus browsing on a subfolder.
