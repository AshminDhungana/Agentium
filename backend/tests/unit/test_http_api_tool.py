"""
Quick smoke tests for http_api_tool.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class MockResponse:
    def __init__(self, json_data=None, text="", status_code=200, headers=None):
        self._json = json_data
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockAsyncClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        resp = self.responses.pop(0) if self.responses else MockResponse({"ok": True})
        return resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def put(self, url, **kwargs):
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url, **kwargs):
        return await self.request("DELETE", url, **kwargs)

    async def patch(self, url, **kwargs):
        return await self.request("PATCH", url, **kwargs)


def test_http_api_get(monkeypatch):
    from backend.tools.http_api_tool import http_api_tool

    mock_client = MockAsyncClient([MockResponse(json_data={"result": "success"})])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)

    result = asyncio_run(http_api_tool.execute(
        url="https://api.example.com/test",
        method="GET"
    ))
    assert result["success"] is True
    assert result["data"]["result"] == "success"


def test_http_api_post_json(monkeypatch):
    from backend.tools.http_api_tool import http_api_tool

    mock_client = MockAsyncClient([MockResponse(json_data={"created": True, "id": 123})])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)

    result = asyncio_run(http_api_tool.execute(
        url="https://api.example.com/items",
        method="POST",
        json_data={"name": "test item"}
    ))
    assert result["success"] is True
    assert result["data"]["id"] == 123


def test_http_api_with_auth(monkeypatch):
    from backend.tools.http_api_tool import http_api_tool

    mock_client = MockAsyncClient([MockResponse(json_data={"user": "test"})])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)

    result = asyncio_run(http_api_tool.execute(
        url="https://api.example.com/me",
        method="GET",
        auth_type="bearer",
        auth_value="test-token"
    ))
    assert result["success"] is True


def test_http_api_batch(monkeypatch):
    from backend.tools.http_api_tool import http_api_tool

    responses = [
        MockResponse(json_data={"id": 1}),
        MockResponse(json_data={"id": 2}),
        MockResponse(json_data={"id": 3}),
    ]
    mock_client = MockAsyncClient(responses)
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)

    result = asyncio_run(http_api_tool.batch_request(
        requests=[
            {"url": "https://api.example.com/1", "method": "GET"},
            {"url": "https://api.example.com/2", "method": "GET"},
            {"url": "https://api.example.com/3", "method": "GET"},
        ],
        concurrency=2
    ))
    assert result["success"] is True
    assert len(result["results"]) == 3


def test_http_api_error_handling(monkeypatch):
    from backend.tools.http_api_tool import http_api_tool

    mock_client = MockAsyncClient([MockResponse(text="Not Found", status_code=404)])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)

    result = asyncio_run(http_api_tool.execute(
        url="https://api.example.com/missing",
        method="GET"
    ))
    assert result["success"] is False
    assert "404" in result["error"] or "not found" in result["error"].lower()


def test_http_api_timeout(monkeypatch):
    from backend.tools.http_api_tool import http_api_tool
    import httpx

    async def slow_request(*args, **kwargs):
        import asyncio
        await asyncio.sleep(10)
        return MockResponse()

    mock_client = MockAsyncClient([])
    mock_client.request = slow_request
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)

    result = asyncio_run(http_api_tool.execute(
        url="https://slow.example.com",
        method="GET",
        timeout=1
    ))
    # Should handle timeout gracefully


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)