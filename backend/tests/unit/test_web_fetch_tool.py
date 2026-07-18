import asyncio
from types import SimpleNamespace
from backend.tools import web_fetch_tool


def test_fetch_success_truncates(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        text = "<html><head><title>Hi</title></head><body>" + ("x" * 100000) + "</body></html>"
        headers = {"content-type": "text/html"}

    class FakeClient:
        async def get(self, url, **kw):
            captured["url"] = url
            return FakeResp()

    monkeypatch.setattr(web_fetch_tool, "_client", FakeClient())
    # force no extraction lib so it falls back to raw strip
    monkeypatch.setattr(web_fetch_tool, "_extract", lambda html, url: html)

    result = asyncio.get_event_loop().run_until_complete(
        web_fetch_tool.execute("fetch", url="https://example.com", max_tokens=100)
    )
    assert result["status"] == "success"
    assert result["title"] == "Hi"
    assert result["truncated"] is True
    assert result["token_count"] <= 200


def test_fetch_blocks_disallowed_domain(monkeypatch):
    monkeypatch.setattr(web_fetch_tool, "_client", None)
    result = asyncio.get_event_loop().run_until_complete(
        web_fetch_tool.execute(
            "fetch", url="https://evil.com", allowed_domains=["good.com"]
        )
    )
    assert result["status"] == "error"
    assert "domain" in result["error"].lower()


def test_help_action():
    result = asyncio.get_event_loop().run_until_complete(web_fetch_tool.execute("help"))
    assert result["status"] == "success"
    assert "SKILL.md" in result["description"]
