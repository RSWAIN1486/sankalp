# Web Research Skill

Research any topic from the web, summarize findings , provide source links, and save findings when requested.

## Behavior

- Use `/research <query>` for explicit web discovery.
- For natural requests like "find latest ...", tool selection may run web search automatically.
- Return concise findings with cited links.
- If user asks to save/document, store the generated findings in Obsidian memory (not the raw request).

## Recommended Flow

1. Run web search for the query.
2. Summarize top relevant findings.
3. Include source links in response.
4. Save summary to Obsidian when asked.

## Notes

- This skill is generic web research, not paper-only.
- For deeper analysis, follow search with `/fetch <url>` on the most relevant results.
