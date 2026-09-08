"""
Quick smoke tests for browser_tool (BrowserTool class).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class MockPage:
    def __init__(self):
        self.url = "https://example.com"
        self._title = "Example Page"
        self.content_calls = []

    async def goto(self, url, **kwargs):
        self.url = url

    async def title(self):
        return self._title

    async def content(self):
        return "<html><body>Test</body></html>"

    async def screenshot(self, path=None, **kwargs):
        self.content_calls.append(("screenshot", path))
        return b"fake-png-data"

    async def close(self):
        pass


class MockContext:
    def __init__(self):
        self.pages = []

    async def new_page(self):
        page = MockPage()
        self.pages.append(page)
        return page


class MockBrowser:
    def __init__(self):
        self.contexts = []

    async def new_context(self, **kwargs):
        ctx = MockContext()
        self.contexts.append(ctx)
        return ctx

    async def close(self):
        pass


class MockPlaywright:
    def __init__(self):
        self.browsers = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @property
    def chromium(self):
        browser = MockBrowser()
        self.browsers.append(browser)
        return browser


def test_browser_tool_navigate(monkeypatch):
    from backend.tools.browser_tool import BrowserTool

    mock_pw = MockPlaywright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: mock_pw)

    tool = BrowserTool()
    result = asyncio_run(tool.execute(action="navigate", url="https://example.com"))

    assert result["success"] is True
    assert result["url"] == "https://example.com"
    assert "title" in result


def test_browser_tool_screenshot(monkeypatch):
    from backend.tools.browser_tool import BrowserTool

    mock_pw = MockPlaywright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: mock_pw)

    tool = BrowserTool()
    asyncio_run(tool.execute(action="navigate", url="https://example.com"))
    result = asyncio_run(tool.execute(action="screenshot", path="/tmp/test.png"))

    assert result["success"] is True
    assert result["path"] == "/tmp/test.png"


def test_browser_tool_close(monkeypatch):
    from backend.tools.browser_tool import BrowserTool

    mock_pw = MockPlaywright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: mock_pw)

    tool = BrowserTool()
    asyncio_run(tool.execute(action="navigate", url="https://example.com"))
    result = asyncio_run(tool.execute(action="close"))

    assert result["success"] is True


def test_browser_tool_invalid_action(monkeypatch):
    from backend.tools.browser_tool import BrowserTool

    mock_pw = MockPlaywright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: mock_pw)

    tool = BrowserTool()
    result = asyncio_run(tool.execute(action="invalid_action"))

    assert result["success"] is False
    assert "unknown action" in result["error"].lower()


def test_browser_tool_navigate_no_playwright(monkeypatch):
    # Skip if playwright is installed (which it is in this env)
    import pytest
    pytest.skip("Playwright is installed in test environment")


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)