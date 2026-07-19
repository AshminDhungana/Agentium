"""
Task 3: verify the `decide` tool is injected into the Head's generation call
so routing is classified within the same LLM turn (no second round-trip).

The real ChatService.process_message touches the DB, config, provider and
media layers, so we stub those touchpoints but otherwise exercise the real
production code path up to and including the generate_with_tools call, and
capture the kwargs it is invoked with.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import chat_service as cs


@pytest.mark.asyncio
async def test_head_generation_receives_decide_tool(monkeypatch):
    captured = {}

    async def fake_generate_with_tools(self, agent, user_message, *, db, **kwargs):
        # Capture only the PRIMARY generation (process_message's own call). When
        # the model omits the `decide` tool call, the new fallback invokes
        # DecisionEngine().decide which calls generate_with_tools again; we must
        # not let that second (fallback) call overwrite the primary kwargs.
        if not captured:
            captured.update(kwargs)
        return {"content": "On it.", "tool_calls": [], "model": "x"}

    # --- LLMClient: no real network/provider ---
    monkeypatch.setattr(cs.LLMClient, "__init__", lambda self, **k: None)
    monkeypatch.setattr(cs.LLMClient, "generate_with_tools", fake_generate_with_tools)

    # --- provider lookup must return something truthy (else early return) ---
    monkeypatch.setattr(cs.ModelService, "get_provider", AsyncMock(return_value=MagicMock()))

    # --- stubs for the heavier side-paths so we reach generate_with_tools ---
    monkeypatch.setattr(
        cs.reincarnation_service, "get_predecessor_context", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        cs.ChatService, "get_cached_system_context", AsyncMock(return_value="")
    )
    monkeypatch.setattr(cs.context_manager, "update_usage", lambda *a, **k: None)
    monkeypatch.setattr(
        cs.ChatService, "create_task_from_decision", AsyncMock(return_value={})
    )

    # api_key_manager.get_fallback_config_ids is imported locally inside the fn
    import backend.services.api_key_manager as akm

    monkeypatch.setattr(akm.api_key_manager, "get_fallback_config_ids", lambda *a, **k: [])

    # --- make sovereign_user None so media/persist/broadcast paths are skipped ---
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None

    head = MagicMock()
    head.agentium_id = "00001"
    head.current_task_id = None

    await cs.ChatService.process_message(head, "build a scraper", db)

    assert "tools" in captured, "decide tool was not injected (no `tools` kwarg)"
    names = [t.get("function", {}).get("name") for t in captured["tools"]]
    assert "decide" in names, f"decide tool missing from tools: {names}"
    assert captured.get("tool_choice") == {"type": "auto"}
