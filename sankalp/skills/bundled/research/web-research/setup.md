# Web Research Setup

Configure providers in Settings -> Research.

Recommended local-first setup:

1. Run a local Firecrawl server and set its base URL, for example `http://localhost:3002`.
2. Optionally add a Firecrawl cloud API key as fallback.
3. Optionally run SearXNG and set its base URL, for example `http://localhost:8080`.

If none are configured, Sankalp falls back to DuckDuckGo discovery and plain readable-text extraction.
