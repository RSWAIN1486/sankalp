import json
import unittest
from unittest.mock import patch

from sankalp.tools.web_research import WebResearchClient


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/json"):
        self._payload = payload
        self.headers = {"content-type": content_type}

    def read(self, _limit=None):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class WebResearchTests(unittest.TestCase):
    def test_firecrawl_search_normalizes_markdown_results(self):
        payload = {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "JEPA paper",
                        "url": "https://arxiv.org/abs/1",
                        "description": "paper",
                        "markdown": "# JEPA\ncontent",
                    }
                ]
            },
        }

        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode("utf-8"))):
            result = WebResearchClient({"firecrawl_base_url": "http://localhost:3002"}).search("jepa", limit=1)

        self.assertEqual(result["engine"], "firecrawl:self-hosted")
        self.assertEqual(result["results"][0]["url"], "https://arxiv.org/abs/1")
        self.assertIn("JEPA", result["results"][0]["markdown"])

    def test_duckduckgo_urls_are_cleaned(self):
        html = b'''
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpaper">Paper</a>
        '''

        with patch("urllib.request.urlopen", return_value=FakeResponse(html, "text/html")):
            result = WebResearchClient({}).search("paper", limit=1, include_content=False)

        self.assertEqual(result["engine"], "duckduckgo")
        self.assertEqual(result["results"][0]["url"], "https://example.com/paper")


if __name__ == "__main__":
    unittest.main()
