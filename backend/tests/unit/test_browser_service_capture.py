import asyncio
from unittest.mock import AsyncMock, MagicMock
from backend.services.browser_service import BrowserService, BrowserSession


def test_start_stream_early_returns_when_uninitialized():
    svc = BrowserService.__new__(BrowserService)
    svc._initialized = False
    svc._browser = None
    svc._sessions = {}
    asyncio.run(svc.start_stream("t1", "https://example.com", "agent", 2.0))
    assert "t1" not in svc._sessions


def test_screencast_frame_emits_browser_frame():
    svc = BrowserService.__new__(BrowserService)
    svc._initialized = True
    svc._browser = MagicMock()
    svc._sessions = {}

    cdp = MagicMock()
    cdp.send = AsyncMock()
    sent = {}
    def _on(event, cb): sent[event] = cb
    cdp.on = _on

    sess = BrowserSession(
        session_id="t1", url="https://example.com", title="", status="active",
        agent_id="a", fps=2.0, started_at=__import__("datetime").datetime.utcnow(),
        latest_frame="", action_log=[], _context=MagicMock(),
        _page=MagicMock(), _capture_task=None, _cdp=cdp,
    )
    sess._page.title = lambda: "Page"
    sess._page.url = "https://example.com"
    svc._sessions["t1"] = sess

    import backend.services.browser_service as bsm
    bsm.websocket_manager = MagicMock()
    bsm.websocket_manager.emit_browser_frame = AsyncMock()

    async def run():
        loop_task = asyncio.create_task(svc._capture_loop("t1"))
        await asyncio.sleep(0)  # let the handler register
        frame = {"sessionId": 1, "data": "BASE64DATA"}
        await sent["Page.screencastFrame"](frame)
        await asyncio.sleep(0)  # let the on-frame task run
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
    asyncio.run(run())
    bsm.websocket_manager.emit_browser_frame.assert_awaited()
    cdp.send.assert_any_await(
        "Page.screencastFrameAck", {"sessionId": 1, "dataSize": len("BASE64DATA")})
