"""
TDD: Task 5 — Media interception + Head-turn persistence must be deferred
OFF the critical path of `ChatService.process_message`.

The streamed reply (`result["content"]`) must be returned immediately, while
the (potentially slow) media URL download/rewrite and the ChatMessage
persistence for the Head-of-Council turn run later in a `asyncio.create_task`
background coroutine.

This test asserts BOTH properties:
  1. `MediaInterceptor.intercept_and_store` is NOT called synchronously inside
     `process_message` (call count == 0 immediately after it returns).
  2. It IS called once the scheduled background work is driven to completion
     (proving the work still happens — just not on the hot path).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services import chat_service as cs


def _stub_external_boundaries(monkeypatch):
    """Replace every real I/O boundary that process_message touches so the
    whole flow can run with nothing but MagicMocks (no DB / providers / LLM)."""

    # Provider + LLM generation return quickly.
    monkeypatch.setattr(
        cs.ModelService, "get_provider", AsyncMock(return_value=MagicMock())
    )

    fake_llm = MagicMock()
    fake_llm.generate_with_tools = AsyncMock(
        return_value={"content": "ok", "tool_calls": [], "model": "x"}
    )
    monkeypatch.setattr(cs, "LLMClient", MagicMock(return_value=fake_llm))

    # No governance command short-circuits the LLM path.
    monkeypatch.setattr(
        "backend.services.governance_command_service.GovernanceCommandService.detect_command",
        lambda message: None,
    )

    # Context builder / summary / prefs — no real DB scans.
    class _StubCtxBuilder:
        def __init__(self, *a, **k):
            pass

        def build(self, *a, **k):
            return {
                "history": [],
                "context_compressed": False,
                "raw_turn_count": 0,
            }

    monkeypatch.setattr(
        "backend.services.chat_context.ChatContextBuilder", _StubCtxBuilder
    )
    monkeypatch.setattr(
        "backend.services.chat_context.load_summary", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "backend.services.chat_context.format_summary_for_prompt", lambda *a, **k: ""
    )
    monkeypatch.setattr(
        "backend.services.chat_context.set_chat_request", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "backend.services.chat_context.clear_chat_request", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "backend.services.chat_context.estimate_tokens", lambda *a, **k: 0
    )
    monkeypatch.setattr(
        "backend.services.user_preference_service.UserPreferenceService",
        MagicMock(),
    )
    monkeypatch.setattr(
        "backend.services.api_key_manager.api_key_manager.get_fallback_config_ids",
        lambda *a, **k: [],
    )

    # Channel broadcast is already fire-and-forget; stub it so gathering the
    # background tasks does not attempt real network I/O.
    monkeypatch.setattr(
        "backend.services.channel_manager.ChannelManager.broadcast_to_channels",
        AsyncMock(),
    )

    # Tool registry lookup is best-effort; stub to empty.
    class _StubToolRegistry:
        def to_openai_tools(self, *a, **k):
            return []

    monkeypatch.setattr(
        "backend.core.tool_registry.ToolRegistry", _StubToolRegistry
    )

    # Reincarnation / context critical — keep us on the simple happy path.
    monkeypatch.setattr(
        cs.reincarnation_service,
        "get_predecessor_context",
        lambda *a, **k: {},
    )

    class _CtxStatus:
        is_critical = False

    monkeypatch.setattr(
        cs.context_manager, "update_usage", lambda *a, **k: _CtxStatus()
    )


@pytest.mark.asyncio
async def test_media_interception_deferred_off_critical_path(monkeypatch):
    _stub_external_boundaries(monkeypatch)

    # Recording fake for the heavy media work.
    calls = {"n": 0}

    async def fake_intercept(text, user_id, db, http_client=None):
        calls["n"] += 1
        return (text, [])

    monkeypatch.setattr(
        "backend.services.media_interceptor.MediaInterceptor.intercept_and_store",
        staticmethod(fake_intercept),
    )
    # Avoid any real DB session inside the background persistence helper.
    monkeypatch.setattr(
        cs.ChatService,
        "_persist_head_turn_background",
        staticmethod(AsyncMock()),
    )

    # Capture every task spawned via asyncio.create_task so we can drive the
    # scheduled background work deterministically.
    scheduled = []
    real_create = asyncio.create_task

    def _capture(task):
        scheduled.append(task)
        return real_create(task)

    monkeypatch.setattr(asyncio, "create_task", _capture)

    head = MagicMock()
    head.agentium_id = "00001"
    db = MagicMock()

    result = await cs.ChatService.process_message(head, "show me the sales chart", db)

    # 1) Critical path must NOT have run the heavy media work synchronously.
    assert calls["n"] == 0, "MediaInterceptor.intercept_and_store ran on the critical path!"
    # The reply is returned immediately with the original content.
    assert result["content"] == "ok"

    # 2) Now drive the scheduled background work and prove it still happens.
    if scheduled:
        await asyncio.gather(*scheduled, return_exceptions=True)
    assert calls["n"] >= 1, "MediaInterceptor.intercept_and_store never ran in the background!"
