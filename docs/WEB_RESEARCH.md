# Web Research Setup

Sankalp's research stack is provider-ordered so local/private infrastructure wins when it is
available:

1. Firecrawl self-hosted URL from `firecrawl_base_url`
2. Firecrawl cloud API key from `firecrawl_api_key`
3. SearXNG URL from `searxng_base_url`
4. DuckDuckGo fallback

The research flow is search -> extract readable content -> summarize with the user-selected
LLM -> optionally save the generated findings to Obsidian.

## Firecrawl Self-Hosted

Firecrawl's self-host docs use `PORT=3002`, `HOST=0.0.0.0`, and Docker Compose. With default
settings, the local API is available at:

```bash
http://localhost:3002
```

Set that value in Sankalp Settings -> Research as the Firecrawl self-hosted URL. Sankalp will
try `/v2/search` and `/v1/search`, and will request markdown content from search results when
the endpoint supports it.

## Firecrawl Cloud

If self-hosted Firecrawl is not configured or does not respond, Sankalp uses the saved
Firecrawl API key against:

```bash
https://api.firecrawl.dev/v2
```

The key is stored locally in `~/.sankalp/settings.json` and masked from normal settings API
responses.

## SearXNG

If Firecrawl is unavailable, Sankalp can query a SearXNG instance with JSON enabled:

```bash
http://localhost:8080/search?q=<query>&format=json
```

Set the base URL in Settings -> Research. Sankalp enriches SearXNG results by fetching readable
text from the top URLs.

## DuckDuckGo Fallback

DuckDuckGo is only the final fallback. Sankalp cleans DuckDuckGo redirect URLs and fetches
readable text from top result pages before asking the selected LLM to summarize.
