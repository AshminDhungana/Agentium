import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock


async def test_ws_emits_stream_events_and_cancel():
    from backend.api.routes import websocket as ws_mod

    sent = []

    class _FakeWS:
        def __init__(self):
            self.inbound = asyncio.Queue()

        async def send_json(self, payload):
            sent.append(payload)

        async def receive_text(self):
            return json.dumps(await self.inbound.get())

        async def accept(self):
            pass

    fake_ws = _FakeWS()

    async def fake_process_message(head, message, db, **kwargs):
        on_delta = kwargs.get("on_delta")
        cancel_event = kwargs.get("cancel_event")
        on_tool_start = kwargs.get("on_tool_start")
        assert on_delta is not None and cancel_event is not None

        # Simulate a tool call phase before streaming text
        if on_tool_start is not None:
            await on_tool_start([{"name": "search", "id": "tc_1"}], 1)

        await on_delta("Hello ")
        await on_delta("world")
        return {
            "content": "Hello world", "model": "m", "tokens_used": 2,
            "task_created": False, "task_id": None, "agent_spawned": None,
            "reincarnated": False, "finish_reason": "stop", "metadata": {},
        }

    # Find the connection handler coroutine function in the module.
    handler = None
    for name in dir(ws_mod):
        obj = getattr(ws_mod, name)
        if asyncio.iscoroutinefunction(obj) and "chat" in name.lower():
            handler = obj
            break
    assert handler is not None, "could not find chat websocket handler"

    head = MagicMock()
    with patch.object(ws_mod.ChatService, "process_message", staticmethod(fake_process_message)):
        # Bypass the JWT auth gate.
        with patch.object(ws_mod.manager, "authenticate",
                          AsyncMock(return_value={"username": "u", "head_agentium_id": "00001"})):
            # Provide a head for the per-message DB lookup.
            with patch.object(ws_mod, "get_fresh_db") as mock_db:
                mock_db.return_value.__enter__.return_value.query.return_value.filter_by.return_value.first.return_value = head

                task = asyncio.create_task(handler(fake_ws))
                await asyncio.sleep(0.05)
                # Authenticate so the message path is reachable.
                await fake_ws.inbound.put({"type": "auth", "token": "x"})
                await asyncio.sleep(0.05)
                # Send a real chat message to trigger streaming generation.
                await fake_ws.inbound.put({"type": "message", "content": "hi"})
                await asyncio.sleep(0.1)
                # A cancel for a non-existent stream_id must be a safe no-op.
                await fake_ws.inbound.put({"type": "cancel", "stream_id": "nope"})
                await asyncio.sleep(0.05)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    types = [m["type"] for m in sent]
    # The connection emits a `system` welcome right after auth, so the chat
    # stream events begin with the first `message_start` and end with the
    # final `message_end`.
    assert "message_start" in types, types
    assert "tool_progress" in types, f"expected tool_progress in {types}"
    tp_idx = types.index("tool_progress")
    start_idx = types.index("message_start")
    delta_idx = types.index("message_delta")
    assert start_idx < tp_idx < delta_idx, \
        f"tool_progress should be after message_start but before message_delta: {types}"
    assert types.index("message_start") < types.index("message_end"), types
    assert types[-1] == "message_end", types
    assert "message_delta" in types, types
    assert sent[-1]["content"] == "Hello world"
    assert sent[-1]["finish_reason"] == "stop"
