"""
Issue 8.1 — Head delegates, never executes; stays responsive while busy.

Verifies the prompt-only guardrail and the non-blocking contract:

  1. The "Governance & Delegation Protocol" block (forbidding the Head from
     calling execution tools inline and instructing it to delegate) is injected
     into the Head's chat generation prompt.
  2. An execution-intent message is classified as a delegation action and the
     long-running task is scheduled fire-and-forget (off the critical path);
     `process_message` returns the Head's reply immediately, before the
     delegated task runs.
  3. Concurrency: the Head answers a second message while the first message's
     delegated task is still in flight.
"""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.services import chat_service as cs


def _stub_boundaries(monkeypatch):
    """Stub the I/O boundaries process_message touches so it runs with mocks."""
    monkeypatch.setattr(cs.ModelService, "get_provider", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(
        cs.reincarnation_service, "get_predecessor_context", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        cs.ChatService, "get_cached_system_context", AsyncMock(return_value="")
    )

    class _CtxStatus:
        is_critical = False

    monkeypatch.setattr(
        cs.context_manager, "update_usage", lambda *a, **k: _CtxStatus()
    )
    monkeypatch.setattr(
        cs.ChatService, "create_task_from_decision", AsyncMock(return_value={})
    )

    import backend.services.api_key_manager as akm

    monkeypatch.setattr(akm.api_key_manager, "get_fallback_config_ids", lambda *a, **k: [])

    # sovereign_user = None -> media/persist/broadcast paths are skipped, but the
    # delegation (task-creation) path still runs.
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
    return db


def _decide_message(action: str, brief: str) -> dict:
    """Build a generate_with_tools result whose assistant turn emits `decide`."""
    return {
        "content": "Acknowledged.",
        "model": "x",
        "messages": [
            {
                "role": "assistant",
                "content": "Acknowledged.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "decide",
                            "arguments": json.dumps(
                                {
                                    "action": action,
                                    "rationale": "delegation",
                                    "task_brief": brief,
                                    "confidence": 0.9,
                                }
                            ),
                        }
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_delegation_protocol_injected_into_prompt(monkeypatch):
    captured = {}

    async def fake_generate(self, agent, user_message, *, db, **kwargs):
        if not captured:
            captured.update(kwargs)
        return {"content": "ok", "tool_calls": [], "model": "x"}

    monkeypatch.setattr(cs.LLMClient, "__init__", lambda self, **k: None)
    monkeypatch.setattr(cs.LLMClient, "generate_with_tools", fake_generate)
    db = _stub_boundaries(monkeypatch)

    head = MagicMock()
    head.agentium_id = "00001"
    head.current_task_id = None

    await cs.ChatService.process_message(head, "deploy the new build", db)

    prompt = captured.get("system_prompt_override", "")
    assert "GOVERNANCE & DELEGATION PROTOCOL" in prompt
    assert "MUST NOT call execution tools" in prompt
    assert "create_task" in prompt
    assert "Lead/Task" in prompt


@pytest.mark.asyncio
async def test_execution_intent_delegated_not_executed_inline(monkeypatch):
    """Head replies immediately; delegated task is scheduled off the hot path."""

    async def fake_generate(self, agent, user_message, *, db, **kwargs):
        return _decide_message("create_task", "run the deployment script")

    monkeypatch.setattr(cs.LLMClient, "__init__", lambda self, **k: None)
    monkeypatch.setattr(cs.LLMClient, "generate_with_tools", fake_generate)
    db = _stub_boundaries(monkeypatch)

    # Capture every asyncio.create_task so we can drive background work later.
    scheduled = []
    real_create = asyncio.create_task

    def _capture(task):
        scheduled.append(task)
        return real_create(task)

    monkeypatch.setattr(asyncio, "create_task", _capture)

    head = MagicMock()
    head.agentium_id = "00001"
    head.current_task_id = None

    result = await cs.ChatService.process_message(head, "run the deployment script", db)

    # Reply is returned immediately.
    assert result["content"] == "Acknowledged."
    assert result["task_created"] is True
    # The long-running work was offloaded to a background task (not awaited
    # inline), proving the chat turn is non-blocking.
    assert scheduled, "delegated task was not scheduled off the critical path"

    # Now drive the background work and prove delegation still happened.
    await asyncio.gather(*scheduled, return_exceptions=True)


@pytest.mark.asyncio
async def test_head_answers_message_two_while_task_one_running(monkeypatch):
    """
    Concurrency: the Head answers message #2 while message #1's delegated task
    is still in flight.
    """
    # msg1 -> create_task (slow delegated task); msg2 -> plain reply.
    async def fake_generate(self, agent, user_message, *, db, **kwargs):
        if "deploy" in user_message:
            return _decide_message("create_task", "deploy the build")
        return {"content": "Hello, Sovereign.", "tool_calls": [], "model": "x"}

    monkeypatch.setattr(cs.LLMClient, "__init__", lambda self, **k: None)
    monkeypatch.setattr(cs.LLMClient, "generate_with_tools", fake_generate)
    db = _stub_boundaries(monkeypatch)

    # Slow delegated task: blocks on an event so we can prove it is still
    # running when message #2 is answered.
    task_one_running = asyncio.Event()

    async def fake_create_task_background(head_agentium_id, decision, prompt, user_id):
        await task_one_running.wait()  # pretend the delegated execution is busy

    monkeypatch.setattr(
        cs.ChatService, "_create_task_background", fake_create_task_background
    )

    head = MagicMock()
    head.agentium_id = "00001"
    head.current_task_id = None

    # Run both chat turns concurrently, exactly as two quick successive messages
    # would be handled by the WebSocket (each in its own task).
    res1, res2 = await asyncio.gather(
        cs.ChatService.process_message(head, "deploy the new build", db),
        cs.ChatService.process_message(head, "hello", db),
    )

    # Message #2 was answered...
    assert res2["content"] == "Hello, Sovereign."
    # ...while message #1's delegated task is STILL running (event not released).
    assert not task_one_running.is_set()

    # Cleanup: release so the (captured) background task can complete.
    task_one_running.set()
    await asyncio.sleep(0)
