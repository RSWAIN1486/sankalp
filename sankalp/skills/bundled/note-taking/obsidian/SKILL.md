# Obsidian Memory

Use Sankalp's configured Obsidian vault as the human-readable long-term memory layer.

## Behavior

- Save explicit durable facts with `/remember <fact>`.
- Search promoted memory with `memory_search`.
- Keep chat transcripts in `Sessions/` separate from promoted memory.
- Treat Markdown files as user-owned and preserve readable note structure.

## Setup

- Configure `obsidian_vault_path` in Sankalp settings.
- Optionally configure `obsidian_workspace_path` to focus browsing on a subfolder.
