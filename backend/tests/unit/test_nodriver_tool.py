"""
Quick smoke tests for nodriver_tool.
"""
import pytest


def test_nodriver_tool_unavailable():
    """Test that tool returns error when nodriver not installed."""
    from backend.tools.nodriver_tool import nodriver_tool

    result = asyncio_run(nodriver_tool.navigate(url="https://example.com"))
    assert result["status"] == "error"
    assert "nodriver is not installed" in result["error"]


def test_nodriver_tool_screenshot_unavailable():
    from backend.tools.nodriver_tool import nodriver_tool

    result = asyncio_run(nodriver_tool.screenshot(save_path="/tmp/test.png"))
    assert result["status"] == "error"


def test_nodriver_tool_get_content_unavailable():
    from backend.tools.nodriver_tool import nodriver_tool

    result = asyncio_run(nodriver_tool.get_content())
    assert result["status"] == "error"


def test_nodriver_tool_close_unavailable():
    from backend.tools.nodriver_tool import nodriver_tool

    result = asyncio_run(nodriver_tool.close())
    assert result["status"] == "error"


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)