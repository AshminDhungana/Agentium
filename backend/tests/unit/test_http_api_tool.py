"""
Quick smoke tests for http_api_tool.

The tool is aiohttp-based: `execute` does `async with session.request(...)`
and reads `.status` / `async .text()` / `.url`. The mock below implements
that protocol (an httpx-style mock never worked against this code) and is
patched onto `aiohttp.ClientSession` — the binding `_get_session` reads.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from yarl import URL


class MockAioResponse:
    """aiohttp response protocol: async CM, .status, .text(), .headers, .url."""

    def __init__(self, json_data=None, text="", status=200, headers=None):
        self._json = json_data
        self._text = text
        self.status = status
        self.headers = headers or {"content-type": "application/json"}
        self.url = URL("https://api.example.com/test")
        self.reason = "MOCK"

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class MockAioSession:
    """aiohttp session protocol: request() returns the async-CM response."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        resp = self.responses.pop(0) if self.responses else MockAioResponse(text="{}")
        return resp

    async def close(self):
        self.closed = True


def _patch_session(monkeypatch, session):
    """Patch aiohttp.ClientSession and reset the tool's cached _session —
    the tool is a module-level singleton, so a stale cache would leak
    across tests and never hit the patched constructor."""
    from backend.tools.http_api_tool import http_api_tool

    http_api_tool._session = None
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kw: session)
    return http_api_tool


def test_http_api_get(monkeypatch):
    session = MockAioSession([MockAioResponse(text='{"result": "success"}')])
    tool = _patch_session(monkeypatch, session)

    result = asyncio.run(tool.execute(
        url="https://api.example.com/test",
        method="GET"
    ))
    assert result["success"] is True
    assert result["body"]["result"] == "success"


def test_http_api_post_json(monkeypatch):
    session = MockAioSession([MockAioResponse(text='{"created": true, "id": 123}')])
    tool = _patch_session(monkeypatch, session)

    result = asyncio.run(tool.execute(
        url="https://api.example.com/items",
        method="POST",
        json_data={"name": "test item"}
    ))
    assert result["success"] is True
    assert result["body"]["id"] == 123


def test_http_api_with_auth(monkeypatch):
    session = MockAioSession([MockAioResponse(text='{"user": "test"}')])
    tool = _patch_session(monkeypatch, session)

    result = asyncio.run(tool.execute(
        url="https://api.example.com/me",
        method="GET",
        auth_type="bearer",
        auth_value="test-token"
    ))
    assert result["success"] is True
    # The bearer token was attached to the outgoing request.
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer test-token"


def test_http_api_batch(monkeypatch):
    session = MockAioSession([
        MockAioResponse(text='{"id": 1}'),
        MockAioResponse(text='{"id": 2}'),
        MockAioResponse(text='{"id": 3}'),
    ])
    tool = _patch_session(monkeypatch, session)

    result = asyncio.run(tool.batch_request(
        requests=[
            {"url": "https://api.example.com/1", "method": "GET"},
            {"url": "https://api.example.com/2", "method": "GET"},
            {"url": "https://api.example.com/3", "method": "GET"},
        ],
        concurrency=2
    ))
    # batch_request returns a list (asyncio.gather) — one result per request.
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(r["success"] for r in result)


def test_http_api_error_handling(monkeypatch):
    session = MockAioSession([MockAioResponse(text="Not Found", status=404)])
    tool = _patch_session(monkeypatch, session)

    result = asyncio.run(tool.execute(
        url="https://api.example.com/missing",
        method="GET"
    ))
    assert result["success"] is False
    assert "404" in result["error"]


def test_http_api_timeout(monkeypatch):
    session = MockAioSession([])
    tool = _patch_session(monkeypatch, session)

    async def slow_request(*args, **kwargs):
        await asyncio.sleep(10)
        return MockAioResponse()

    session.request = slow_request

    result = asyncio.run(tool.execute(
        url="https://slow.example.com",
        method="GET",
        timeout=1
    ))
    # Should handle timeout gracefully
    assert result["success"] is False
