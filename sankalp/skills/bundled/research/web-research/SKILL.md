# Web Research Skill

Research any topic from the web, summarize findings, provide source links, and save findings when requested.

## Behavior

- Use `/research <query>` for explicit web discovery.
- Natural requests like "find latest ..." route into the research workflow automatically.
- Search provider order is Firecrawl self-hosted URL, Firecrawl cloud API key, SearXNG URL, then DuckDuckGo fallback.
- Extract readable page content before summarizing whenever the provider can provide or fetch it.
- Return concise findings with cited links.
- If user asks to save/document, store only the generated findings note body in Obsidian memory, not the raw request or conversational answer wrapper.
- Route saved findings to the most relevant existing vault folder, such as `Research` for source-backed research and papers; create a concise new top-level folder when no existing destination fits.

## Recommended Flow

1. Run web search through the configured provider chain.
2. Extract markdown or readable text from the best results.
3. Ask the user-selected LLM to synthesize findings from the extracted source material.
4. Include source links in response.
5. Save the clean Markdown note body to Obsidian when asked.

## Notes

- This skill is generic web research, not paper-only.
- Configure Firecrawl and SearXNG in Settings -> Research.
- `/fetch <url>` also prefers Firecrawl scraping when configured, then falls back to plain readable-text extraction.
