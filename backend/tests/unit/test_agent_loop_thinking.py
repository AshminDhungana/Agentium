import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import model_provider as mp


class _ThinkConfig:
    """Minimal UserModelConfig stand-in for provider construction.

    `provider` is a plain string (the enum *value*) to mirror a DB-loaded
    UserModelConfig at runtime, where SQLAlchemy stores the ProviderType as its
    string value. The str-enum comparison in BaseModelProvider.__init__ then
    treats it as equal to ProviderType.<X>.
    """
    def __init__(self, provider, model, effort="none", max_tokens=4000):
        self.id = "cfg-test"
        self.provider = provider
        self.default_model = model
        self.effort = effort
        self.max_tokens = max_tokens
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

    def get_effective_base_url(self):
        # Mirror UserModelConfig default-base-URL lookup so providers that are
        # not in _REQUIRES_EXPLICIT_BASE_URL resolve to a non-None URL (avoids
        # the "no base URL" guard) without any network access.
        from backend.models.entities.user_config import UserModelConfig
        if self.provider in {p.value for p in UserModelConfig._REQUIRES_EXPLICIT_BASE_URL}:
            return None
        return UserModelConfig._DEFAULT_BASE_URLS.get(self.provider, "https://api.openai.com/v1")


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="answer")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        model="claude-opus-4-8",
    ))
    client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="answer", tool_calls=None),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
        model="gpt-5.6",
    ))
    monkeypatch.setattr(mp, "_get_cached_sdk_client", lambda *a, **k: client)
    # Rate limiter + header hooks are no-ops in the unit harness.
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "release_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire", AsyncMock())
    monkeypatch.setattr(mp, "_record_provider_headers", AsyncMock())
    return client


async def _run(provider, config):
    prov = provider(config)
    return await prov.generate_with_tools(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_executor=AsyncMock(return_value="{}"),
        max_iterations=1,
        agentium_id="test",
    )


def test_anthropic_adaptive_forwarded(mock_client):
    asyncio.run(_run(mp.AnthropicProvider, _ThinkConfig("ANTHROPIC", "claude-opus-4-8", "high")))
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["extra_body"]["thinking"] == {"type": "adaptive"}
    assert kwargs["extra_body"]["output_config"] == {"effort": "high"}


def test_anthropic_legacy_budget_forwarded(mock_client):
    asyncio.run(_run(mp.AnthropicProvider, _ThinkConfig("ANTHROPIC", "claude-opus-4-5", "high")))
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    assert kwargs["max_tokens"] >= 16000 + 2048  # guard applied


def test_anthropic_none_forwards_no_thinking(mock_client):
    asyncio.run(_run(mp.AnthropicProvider, _ThinkConfig("ANTHROPIC", "claude-opus-4-8", "none")))
    kwargs = mock_client.messages.create.call_args.kwargs
    assert "extra_body" not in kwargs
    assert "thinking" not in kwargs


def test_openai_reasoning_effort_forwarded(mock_client):
    asyncio.run(_run(mp.OpenAICompatibleProvider, _ThinkConfig("OPENAI", "gpt-5.6", "xhigh")))
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"]["reasoning_effort"] == "xhigh"
