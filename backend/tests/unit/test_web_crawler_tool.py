import asyncio
from types import SimpleNamespace

from backend.tools import web_crawler_tool


class _FakeClient:
    """Configurable fake httpx client.

    - robots.txt → configurable body / 404
    - anything else → HTML page listing `links` (same-domain by default)
    """

    def __init__(self, robots_body=None, links=None, page_html=None):
        self.robots_body = robots_body
        self.links = links or []
        self.page_html = page_html
        self.get_calls = []

    async def get(self, url, **kw):
        self.get_calls.append(url)
        if url.endswith("/robots.txt"):
            if self.robots_body is None:
                return SimpleNamespace(status_code=404, headers={}, text="", content=b"")
            return SimpleNamespace(status_code=200, headers={"content-type": "text/plain"}, text=self.robots_body, content=self.robots_body.encode())
        html = self.page_html
        if html is None:
            link_html = "".join(f'<a href="{link}">x</a>' for link in self.links)
            html = f"<html><head><title>Page {url}</title></head><body>{link_html}</body></html>"
        return SimpleNamespace(status_code=200, headers={"content-type": "text/html"}, text=html, content=html.encode())


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_crawl_follows_links_depth_one(monkeypatch):
    # start page links to two same-domain children
    client = _FakeClient(links=["https://example.com/a", "https://example.com/b"])
    monkeypatch.setattr(web_crawler_tool, "_client", client)
    web_crawler_tool._robots_cache.clear()
    res = _run(web_crawler_tool.execute("crawl", url="https://example.com/", max_depth=1, max_pages=10))
    assert res["status"] == "success"
    assert res["pages_fetched"] == 3  # start + a + b
    assert res["depth_reached"] == 1
    # children were actually fetched
    assert any(u.endswith("/a") for u in client.get_calls)
    assert any(u.endswith("/b") for u in client.get_calls)


def test_crawl_respects_max_pages(monkeypatch):
    # start links to 5 children, but max_pages=2 → start + 1 child
    client = _FakeClient(links=[f"https://example.com/p{i}" for i in range(5)])
    monkeypatch.setattr(web_crawler_tool, "_client", client)
    web_crawler_tool._robots_cache.clear()
    res = _run(web_crawler_tool.execute("crawl", url="https://example.com/", max_depth=2, max_pages=2))
    assert res["status"] == "success"
    assert res["pages_fetched"] == 2


def test_crawl_respects_depth(monkeypatch):
    # depth 0 → only the start page
    client = _FakeClient(links=["https://example.com/deep"])
    monkeypatch.setattr(web_crawler_tool, "_client", client)
    web_crawler_tool._robots_cache.clear()
    res = _run(web_crawler_tool.execute("crawl", url="https://example.com/", max_depth=0, max_pages=10))
    assert res["status"] == "success"
    assert res["pages_fetched"] == 1
    assert "deep" not in " ".join(client.get_calls)


def test_crawl_stay_on_domain_blocks_offsite(monkeypatch):
    client = _FakeClient(links=["https://other.com/x"])
    monkeypatch.setattr(web_crawler_tool, "_client", client)
    web_crawler_tool._robots_cache.clear()
    res = _run(web_crawler_tool.execute("crawl", url="https://example.com/", max_depth=1, max_pages=10, stay_on_domain=True))
    assert res["status"] == "success"
    assert res["pages_fetched"] == 1  # off-site link not followed
    assert all("other.com" not in c for c in client.get_calls if not c.endswith("/robots.txt"))


def test_crawl_allowed_domains_widens_scope(monkeypatch):
    client = _FakeClient(links=["https://other.com/x"])
    monkeypatch.setattr(web_crawler_tool, "_client", client)
    web_crawler_tool._robots_cache.clear()
    res = _run(web_crawler_tool.execute(
        "crawl", url="https://example.com/", max_depth=1, max_pages=10,
        stay_on_domain=False, allowed_domains=["other.com"],
    ))
    assert res["status"] == "success"
    assert res["pages_fetched"] == 2  # start + other.com/x


def test_crawl_honors_robots_disallow(monkeypatch):
    robots = "User-agent: *\nDisallow: /private\n"
    client = _FakeClient(robots_body=robots)
    monkeypatch.setattr(web_crawler_tool, "_client", client)
    web_crawler_tool._robots_cache.clear()
    res = _run(web_crawler_tool.execute("crawl", url="https://example.com/private", max_depth=0, max_pages=5))
    assert res["status"] == "success"
    assert res["pages_fetched"] == 0
    assert any(f["error"] == "robots.txt disallow" for f in res["failed"])


def test_crawl_ssrf_guard_blocks_private_host(monkeypatch):
    monkeypatch.setattr(web_crawler_tool, "_client", _FakeClient())
    res = _run(web_crawler_tool.execute("crawl", url="http://localhost:5432/"))
    assert res["status"] == "error"
    assert "SSRF" in res["error"]


def test_crawl_invalid_url(monkeypatch):
    monkeypatch.setattr(web_crawler_tool, "_client", _FakeClient())
    res = _run(web_crawler_tool.execute("crawl", url="not-a-url"))
    assert res["status"] == "error"


def test_help_action():
    res = _run(web_crawler_tool.execute("help"))
    assert res["status"] == "success"
    assert "SKILL.md" in res["skill_file"]
    assert "web_crawler" in res["tool"]


def test_unknown_action():
    res = _run(web_crawler_tool.execute("frobnicate"))
    assert res["status"] == "error"
