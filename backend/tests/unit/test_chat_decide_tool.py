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


@pytest.mark.asyncio
async def test_fallback_to_decision_engine_when_decide_omitted(monkeypatch):
    """
    Regression test for the fix at chat_service.py:528.

    When the Head's generation does NOT emit a `decide` tool call,
    `classify_action_from_result` returns REPLY/no_decide_tool_call, and
    `process_message` must fall back to `DecisionEngine().decide(...)` rather
    than silently dropping task creation. The deterministic fallback should
    classify an execution request as CREATE_TASK and schedule the task-creation
    background job so execution requests don't lose task creation.
    """
    # `generate_with_tools` returns a result with NO decide call in `messages`.
    async def fake_generate_with_tools(self, agent, user_message, *, db, **kwargs):
        return {
            "content": "On it.",
            "messages": [{"role": "assistant", "content": "On it."}],
            "model": "x",
        }

    monkeypatch.setattr(cs.LLMClient, "__init__", lambda self, **k: None)
    monkeypatch.setattr(cs.LLMClient, "generate_with_tools", fake_generate_with_tools)

    monkeypatch.setattr(cs.ModelService, "get_provider", AsyncMock(return_value=MagicMock()))

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

    import backend.services.api_key_manager as akm

    monkeypatch.setattr(akm.api_key_manager, "get_fallback_config_ids", lambda *a, **k: [])

    # --- fallback DecisionEngine: deterministic CREATE_TASK decision ---
    from backend.services.decision_engine import Decision, DecisionAction

    fallback_decision = Decision(
        action=DecisionAction.CREATE_TASK,
        task_brief="Build a scraper",
        decision_id="dec-1",
    )
    fake_engine = MagicMock()
    fake_engine.decide = AsyncMock(return_value=fallback_decision)
    monkeypatch.setattr(cs, "DecisionEngine", lambda: fake_engine)

    # --- record that the task-creation path was invoked with a delegation action ---
    recorded = {}
    async def fake_create_task_background(head_agentium_id, decision, prompt, user_id):
        recorded["called"] = True
        recorded["action"] = decision.action
        recorded["head"] = head_agentium_id
    monkeypatch.setattr(
        cs.ChatService, "_create_task_background", fake_create_task_background
    )

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None

    head = MagicMock()
    head.agentium_id = "00001"
    head.current_task_id = None

    result = await cs.ChatService.process_message(head, "build a scraper", db)

    # `_create_task_background` is scheduled via asyncio.create_task; let the
    # running loop execute the scheduled coroutine before we assert on it.
    import asyncio

    await asyncio.sleep(0)

    # 1) fallback DecisionEngine.decide was triggered (decide omitted)
    assert fake_engine.decide.called, "fallback DecisionEngine.decide was not called"
    # 2) the task-creation background path was invoked with a CREATE_TASK decision
    assert recorded.get("called") is True, "task creation path was not scheduled"
    assert recorded.get("action") is DecisionAction.CREATE_TASK
    assert recorded.get("head") == "00001"
    # 3) process_message surfaces the pending task creation
    assert result.get("task_created") is True
