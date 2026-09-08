"""
Quick smoke tests for web_search_tool.
"""
import asyncio
import pytest
from types import SimpleNamespace


class FakeResp:
    def __init__(self, json_data, status_code=200, text=""):
        self._json = json_data
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def post(self, url, json=None, **kw):
        self.calls.append(("post", url, json))
        return self.responses.pop(0) if self.responses else FakeResp({"results": []})

    async def get(self, url, **kw):
        self.calls.append(("get", url))
        return self.responses.pop(0) if self.responses else FakeResp({"results": []})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def test_web_search_empty_query(monkeypatch):
    from backend.tools.web_search_tool import web_search_tool
    result = asyncio.run(web_search_tool.execute(query=""))
    assert result["status"] == "error"
    assert "empty" in result["error"].lower()


def test_web_search_duckduckgo_fallback(monkeypatch):
    from backend.tools.web_search_tool import web_search_tool
    import backend.tools.web_search_tool as wst

    # Mock httpx to return DuckDuckGo HTML
    ddg_html = """
    <html>
    <a class="result__a" href="https://example.com/1">Title One</a>
    <a class="result__snippet">Snippet one</a>
    <a class="result__a" href="https://example.com/2">Title Two</a>
    <a class="result__snippet">Snippet two</a>
    </html>
    """

    async def mock_post(*args, **kwargs):
        return FakeResp({}, status_code=200, text=ddg_html)

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)
    monkeypatch.setattr(wst, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(wst, "_cache_set", lambda *a, **k: None)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    result = asyncio.run(web_search_tool.execute(query="test query", max_results=2, provider="duckduckgo"))
    assert result["status"] == "success"
    assert result["result_count"] == 2
    assert result["results"][0]["title"] == "Title One"
    assert result["results"][1]["url"] == "https://example.com/2"


def test_web_search_tavily_provider(monkeypatch):
    from backend.tools.web_search_tool import web_search_tool
    import backend.tools.web_search_tool as wst

    async def mock_post(*args, **kwargs):
        return FakeResp({
            "results": [
                {"title": "Tavily Result", "url": "https://tavily.com", "content": "Tavily snippet"}
            ]
        }, status_code=200)

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)
    monkeypatch.setattr(wst, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(wst, "_cache_set", lambda *a, **k: None)
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    result = asyncio.run(web_search_tool.execute(query="test", max_results=1, provider="tavily"))
    assert result["status"] == "success"
    assert result["provider"] == "tavily"
    assert result["results"][0]["title"] == "Tavily Result"


def test_web_search_cache_hit(monkeypatch):
    from backend.tools.web_search_tool import web_search_tool
    import backend.tools.web_search_tool as wst

    cached = {
        "status": "success",
        "query": "cached query",
        "provider": "cached",
        "cached": True,
        "latency_ms": 1,
        "result_count": 1,
        "results": [{"index": 0, "title": "Cached", "url": "https://cached.com", "snippet": "cached"}]
    }

    monkeypatch.setattr(wst, "_cache_get", lambda *a, **k: cached)

    result = asyncio.run(web_search_tool.execute(query="cached query", max_results=5))
    assert result["status"] == "success"
    assert result["cached"] is True
    assert result["results"][0]["title"] == "Cached"