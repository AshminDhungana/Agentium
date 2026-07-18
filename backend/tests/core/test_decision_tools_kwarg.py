"""
Regression test for the decision-engine `tools` kwarg bug.

`LLMClient.decide()` forwards ``tools``/``tool_choice`` to
``ModelService.generate_with_agent_tools`` via ``**kwargs``. The old code then
called the provider's ``generate_with_tools(tools=tools, **kwargs)`` which put
``tools`` in *both* places and raised::

    TypeError: generate_with_tools() got multiple values for keyword argument 'tools'

This broke every decision-engine LLM call (and surfaced as 504/hang on the
Head of Council path). The fix pops ``tools``/``tool_choice`` out of kwargs and
passes them explicitly, honouring an explicit ``tool_choice``.

These tests drive ``generate_with_agent_tools`` exactly as ``decide()`` does and
assert no exception is raised and the provider receives the caller's tools plus
the forwarded ``tool_choice``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import model_provider as mp
from backend.core.tool_registry import tool_registry
from backend.services.api_key_manager import api_key_manager


class _FakeProvider:
    """Records the kwargs it was called with; returns a minimal result."""

    def __init__(self):
        self.calls = []

    async def generate_with_tools(
        self, *, system_prompt, messages, tools, tool_executor,
        max_iterations=10, agentium_id=None, on_delta=None,
        cancel_event=None, **kwargs,
    ):
        self.calls.append({
            "tools": tools,
            "tool_choice": kwargs.get("tool_choice"),
            "agentium_id": agentium_id,
        })
        return {
            "content": "ok", "tokens_used": 0, "prompt_tokens": 0,
            "completion_tokens": 0, "latency_ms": 1, "model": "test",
            "messages": messages,
        }


@pytest.fixture
def patched(monkeypatch):
    fake = _FakeProvider()
    fake.config = MagicMock(id="cfg-test")
    monkeypatch.setattr(
        mp.ModelService, "get_provider",
        staticmethod(AsyncMock(return_value=fake)),
    )
    monkeypatch.setattr(
        mp.provider_rate_limiter, "acquire_concurrency", AsyncMock(),
    )
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire", AsyncMock())
    # Avoid touching the real tool registry / API-key manager.
    monkeypatch.setattr(
        tool_registry, "to_openai_tools",
        MagicMock(return_value=[{"id": "registry-tool"}]),
    )
    monkeypatch.setattr(api_key_manager, "mark_key_success", AsyncMock())
    monkeypatch.setattr(api_key_manager, "mark_key_failed", AsyncMock())
    monkeypatch.setattr(api_key_manager, "record_spend", AsyncMock())
    return fake


async def test_decide_tools_path_no_duplicate_kwarg(patched):
    """decide() passes tools/tool_choice via **kwargs — must not raise."""
    fake = patched
    decision_tool = {"type": "function", "function": {"name": "decide"}}
    tool_choice = {"type": "function", "function": {"name": "decide"}}

    agent = MagicMock()
    agent.agentium_id = "0xxxx"

    # Mirror LLMClient.decide(): tools/tool_choice arrive inside **kwargs.
    result = await mp.ModelService.generate_with_agent_tools(
        agent, "route this", db=MagicMock(),
        tools=[decision_tool], tool_choice=tool_choice,
    )

    assert result["content"] == "ok"
    assert fake.calls, "provider.generate_with_tools was never called"
    call = fake.calls[0]
    # The caller's tools must win over the registry tool set.
    assert call["tools"] == [decision_tool]
    # tool_choice must be forwarded through to the provider.
    assert call["tool_choice"] == tool_choice


async def test_normal_agent_path_uses_registry_tools(patched):
    """No caller tools -> provider gets registry tools, no duplicate kwarg."""
    fake = patched
    agent = MagicMock()
    agent.agentium_id = "3xxxx"

    await mp.ModelService.generate_with_agent_tools(
        agent, "do work", db=MagicMock(),
    )

    assert fake.calls
    assert fake.calls[0]["tools"] == [{"id": "registry-tool"}]
    assert fake.calls[0]["tool_choice"] is None
