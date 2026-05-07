from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return html.unescape("\n".join(self.parts))


class WebResearchClient:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    def search(self, query: str, limit: int = 6, include_content: bool = True) -> dict[str, Any]:
        q = query.strip()
        limit = max(1, min(int(limit or 6), 10))
        attempts: list[dict[str, str]] = []

        firecrawl_url = str(self.settings.get("firecrawl_base_url") or "").strip()
        firecrawl_key = str(self.settings.get("firecrawl_api_key") or "").strip()
        if firecrawl_url:
            result = self._firecrawl_search(firecrawl_url, firecrawl_key, q, limit, "firecrawl:self-hosted")
            if result["ok"]:
                return self._with_extracted_content(result["payload"], include_content)
            attempts.append({"provider": "firecrawl:self-hosted", "error": result["error"]})

        if firecrawl_key:
            result = self._firecrawl_search("https://api.firecrawl.dev/v2", firecrawl_key, q, limit, "firecrawl:cloud")
            if result["ok"]:
                return self._with_extracted_content(result["payload"], include_content)
            attempts.append({"provider": "firecrawl:cloud", "error": result["error"]})

        searxng_url = str(self.settings.get("searxng_base_url") or "").strip()
        if searxng_url:
            result = self._searxng_search(searxng_url, q, limit)
            if result["ok"]:
                payload = self._with_extracted_content(result["payload"], include_content)
                payload["fallbacks"] = attempts
                return payload
            attempts.append({"provider": "searxng", "error": result["error"]})

        result = self._duckduckgo_search(q, limit)
        if result["ok"]:
            payload = self._with_extracted_content(result["payload"], include_content)
            payload["fallbacks"] = attempts
            return payload
        attempts.append({"provider": "duckduckgo", "error": result["error"]})
        return {"query": q, "engine": "none", "results": [], "fallbacks": attempts, "error": "all search providers failed"}

    def fetch(self, url: str) -> dict[str, Any]:
        firecrawl_url = str(self.settings.get("firecrawl_base_url") or "").strip()
        firecrawl_key = str(self.settings.get("firecrawl_api_key") or "").strip()
        if firecrawl_url:
            result = self._firecrawl_scrape(firecrawl_url, firecrawl_key, url, "firecrawl:self-hosted")
            if result["ok"]:
                return result["payload"]
        if firecrawl_key:
            result = self._firecrawl_scrape("https://api.firecrawl.dev/v2", firecrawl_key, url, "firecrawl:cloud")
            if result["ok"]:
                return result["payload"]
        return self._plain_fetch(url)

    def _firecrawl_search(self, base_url: str, api_key: str, query: str, limit: int, engine: str) -> dict[str, Any]:
        payload = {
            "query": query[:500],
            "limit": limit,
            "sources": ["web"],
            "timeout": 60000,
            "ignoreInvalidURLs": True,
            "scrapeOptions": {
                "formats": [{"type": "markdown"}],
                "onlyMainContent": True,
            },
        }
        for endpoint in self._firecrawl_endpoints(base_url, "search"):
            try:
                data = self._post_json(endpoint, payload, api_key=api_key, timeout=75)
                results = self._normalize_firecrawl_results(data)
                if results:
                    return {"ok": True, "payload": {"query": query, "engine": engine, "results": results}}
            except Exception as exc:
                last_error = str(exc)
                continue
        return {"ok": False, "error": locals().get("last_error", "no Firecrawl results")}

    def _firecrawl_scrape(self, base_url: str, api_key: str, url: str, engine: str) -> dict[str, Any]:
        payload = {"url": url, "formats": ["markdown"], "onlyMainContent": True, "timeout": 60000}
        for endpoint in self._firecrawl_endpoints(base_url, "scrape"):
            try:
                data = self._post_json(endpoint, payload, api_key=api_key, timeout=75)
                item = data.get("data") if isinstance(data, dict) else {}
                if isinstance(item, dict):
                    markdown = str(item.get("markdown") or item.get("summary") or "").strip()
                    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                    return {
                        "ok": True,
                        "payload": {
                            "url": url,
                            "title": str(metadata.get("title") or "").strip(),
                            "text": markdown[:12000],
                            "content_type": "text/markdown",
                            "engine": engine,
                        },
                    }
            except Exception:
                continue
        return {"ok": False, "error": "Firecrawl scrape failed"}

    def _searxng_search(self, base_url: str, query: str, limit: int) -> dict[str, Any]:
        endpoint = self._join_url(base_url, "search")
        params = urllib.parse.urlencode({"q": query, "format": "json"})
        try:
            data = self._get_json(f"{endpoint}?{params}", timeout=20)
            results = []
            for item in data.get("results", [])[:limit]:
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if title and url:
                    results.append({
                        "title": title,
                        "url": url,
                        "description": str(item.get("content") or "").strip(),
                        "markdown": "",
                    })
            return {"ok": bool(results), "payload": {"query": query, "engine": "searxng", "results": results}, "error": "no SearXNG results"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _duckduckgo_search(self, query: str, limit: int) -> dict[str, Any]:
        url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        try:
            raw = self._get_text(url, timeout=20, max_bytes=1_500_000)
            results = self._parse_duckduckgo_results(raw, limit=limit)
            return {"ok": bool(results), "payload": {"query": query, "engine": "duckduckgo", "results": results}, "error": "no DuckDuckGo results"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _with_extracted_content(self, payload: dict[str, Any], include_content: bool) -> dict[str, Any]:
        if not include_content:
            return payload
        enriched = []
        for index, item in enumerate(payload.get("results") or []):
            copied = dict(item)
            if copied.get("markdown"):
                enriched.append(copied)
                continue
            if index < 4 and copied.get("url"):
                try:
                    fetched = self.fetch(str(copied["url"]))
                    if fetched.get("text"):
                        copied["markdown"] = fetched["text"]
                        copied["extracted_by"] = fetched.get("engine") or "plain-fetch"
                except Exception as exc:
                    copied["extract_error"] = str(exc)
            enriched.append(copied)
        payload = dict(payload)
        payload["results"] = enriched
        return payload

    def _normalize_firecrawl_results(self, data: dict[str, Any]) -> list[dict[str, str]]:
        raw_results: Any = []
        body = data.get("data") if isinstance(data, dict) else None
        if isinstance(body, dict):
            raw_results = body.get("web") or []
        elif isinstance(body, list):
            raw_results = body
        results = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("metadata", {}).get("title") or "").strip()
            url = str(item.get("url") or item.get("metadata", {}).get("sourceURL") or "").strip()
            if not title or not url:
                continue
            results.append({
                "title": title,
                "url": url,
                "description": str(item.get("description") or item.get("snippet") or "").strip(),
                "markdown": str(item.get("markdown") or "").strip()[:12000],
            })
        return results

    def _parse_duckduckgo_results(self, raw_html: str, limit: int) -> list[dict[str, str]]:
        matches = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            raw_html,
            flags=re.I | re.S,
        )
        results: list[dict[str, str]] = []
        for href, title_html in matches:
            title = re.sub(r"<[^>]+>", "", title_html)
            clean_url = self._clean_duckduckgo_url(html.unescape(href))
            title = html.unescape(title).strip()
            if title and clean_url:
                results.append({"title": title, "url": clean_url, "description": "", "markdown": ""})
            if len(results) >= limit:
                break
        return results

    def _clean_duckduckgo_url(self, value: str) -> str:
        parsed = urllib.parse.urlparse(value)
        query = urllib.parse.parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return query["uddg"][0]
        if value.startswith("//duckduckgo.com/l/"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse("https:" + value).query)
            if "uddg" in query and query["uddg"]:
                return query["uddg"][0]
        return value

    def _plain_fetch(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "Sankalp/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(1_500_000)
            content_type = response.headers.get("content-type", "")
        raw = body.decode("utf-8", errors="replace")
        if "html" in content_type.lower():
            parser = TextExtractor()
            parser.feed(raw)
            text = parser.text()
        else:
            text = raw
        return {"url": url, "content_type": content_type, "text": text[:12000], "engine": "plain-fetch"}

    def _post_json(self, url: str, payload: dict[str, Any], api_key: str = "", timeout: int = 30) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "User-Agent": "Sankalp/0.1"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_json(self, url: str, timeout: int = 20) -> dict[str, Any]:
        return json.loads(self._get_text(url, timeout=timeout, max_bytes=1_500_000))

    def _get_text(self, url: str, timeout: int = 20, max_bytes: int = 1_500_000) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": "Sankalp/0.1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(max_bytes).decode("utf-8", errors="replace")

    def _firecrawl_endpoints(self, base_url: str, path: str) -> list[str]:
        base = base_url.rstrip("/")
        if base.endswith("/v1") or base.endswith("/v2"):
            preferred = [self._join_url(base, path)]
        else:
            preferred = [self._join_url(base, f"v2/{path}"), self._join_url(base, f"v1/{path}")]
        return list(dict.fromkeys(preferred))

    def _join_url(self, base_url: str, path: str) -> str:
        return f"{base_url.rstrip('/')}/{path.strip('/')}"
