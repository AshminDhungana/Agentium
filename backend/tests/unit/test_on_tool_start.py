"""Tests for the on_tool_start callback in the generation pipeline."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from services import model_provider as mp


class _ThinkConfig:
    """Minimal UserModelConfig stand-in — same pattern as test_agent_loop_thinking.py."""

    def __init__(self, provider="OPENAI", model="gpt-4o"):
        self.id = "cfg-test"
        self.provider = provider
        self.default_model = model
        self.effort = "none"
        self.max_tokens = 4000
        self.temperature = 0.7
        self.top_p = 1.0
        self.timeout_seconds = 60
        self.max_concurrent_requests = 10
        self.requests_per_minute = 60
        self.api_key_encrypted = None
        self.api_base_url = None
        self.base_url = None
        self.local_server_url = None

    def requires_api_key(self):
        return False

    def increment_usage(self, tokens, cost_usd=None):
        pass

    def get_effective_base_url(self):
        from backend.models.entities.user_config import UserModelConfig
        if self.provider in {p.value for p in UserModelConfig._REQUIRES_EXPLICIT_BASE_URL}:
            return None
        return UserModelConfig._DEFAULT_BASE_URLS.get(self.provider, "https://api.openai.com/v1")


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="ok", tool_calls=None),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        model="gpt-4o",
    ))
    monkeypatch.setattr(mp, "_get_cached_sdk_client", lambda *a, **k: client)
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "release_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire", AsyncMock())
    monkeypatch.setattr(mp, "_record_provider_headers", AsyncMock())
    return client


def _tc(index, id_, name, args='{}'):
    """Build a tool-call MagicMock matching the OpenAI wire format."""
    tc = MagicMock()
    tc.id = id_
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = args
    return tc


@pytest.mark.asyncio
async def test_on_tool_start_fires_with_cumulative_count(monkeypatch):
    """on_tool_start receives cumulative count across multiple tool-call turns."""
    on_tool_start = AsyncMock()
    tool_executor = AsyncMock(return_value="ok")

    monkeypatch.setattr(mp.provider_rate_limiter, "acquire_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "release_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire", AsyncMock())
    monkeypatch.setattr(mp, "_record_provider_headers", AsyncMock())

    call_index = [0]
    responses = [
        SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[_tc(0, "call_1", "search", '{"q":"a"}'),
                                _tc(1, "call_2", "read", '{"f":"b"}')],
                ),
                finish_reason="tool_calls",
            )],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=0),
            model="gpt-4o",
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[_tc(0, "call_3", "write", '{"f":"c"}')],
                ),
                finish_reason="tool_calls",
            )],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=0),
            model="gpt-4o",
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="Done", tool_calls=None),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(prompt_tokens=15, completion_tokens=5),
            model="gpt-4o",
        ),
    ]

    async def _fake_create(**kwargs):
        idx = call_index[0]
        call_index[0] += 1
        return responses[idx]

    monkeypatch.setattr(mp, "_get_cached_sdk_client", lambda *a, **k: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_fake_create))
    ))

    prov = mp.OpenAICompatibleProvider(_ThinkConfig())
    prov.api_key = "sk-test"

    result = await prov.generate_with_tools(
        system_prompt="Be helpful.",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        tool_executor=tool_executor,
        max_iterations=5,
        on_delta=None,
        on_tool_start=on_tool_start,
    )

    assert on_tool_start.call_count == 2, \
        f"expected 2 on_tool_start calls, got {on_tool_start.call_count}"
    assert on_tool_start.await_args_list[0][0][1] == 2
    assert on_tool_start.await_args_list[1][0][1] == 3
    assert result["content"] == "Done"


@pytest.mark.asyncio
async def test_on_tool_start_none_is_safe(monkeypatch):
    """on_tool_start=None does not crash the generation loop."""
    tool_executor = AsyncMock(return_value="ok")

    monkeypatch.setattr(mp.provider_rate_limiter, "acquire_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "release_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire", AsyncMock())
    monkeypatch.setattr(mp, "_record_provider_headers", AsyncMock())

    async def _fake_create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="Hello", tool_calls=None),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
            model="gpt-4o",
        )

    monkeypatch.setattr(mp, "_get_cached_sdk_client", lambda *a, **k: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_fake_create))
    ))

    prov = mp.OpenAICompatibleProvider(_ThinkConfig())
    prov.api_key = "sk-test"

    result = await prov.generate_with_tools(
        system_prompt="Be helpful.",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_executor=tool_executor,
        max_iterations=5,
        on_delta=None,
        on_tool_start=None,
    )

    assert result["content"] == "Hello"
