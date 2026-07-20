"""
Regression tests for Task 6.8 — system-message usage across both LLM APIs.

Agentium talks to OpenAI-style and Anthropic-style APIs, which handle system
prompts differently:

  * OpenAI-style (Chat Completions)          -> a message with role "system"
  * Anthropic     (Messages API)             -> a top-level `system` field
    (Anthropic has no `system` *role*.)

These tests capture the exact request payload each provider builds and assert
an explicit system message is present in BOTH paths. They document the
before/after state (system message is and must remain sent) and guard against
any future refactor that silently drops it.
"""

import types as _types

import pytest

from backend.models.entities.user_config import ProviderType
from services.model_provider import OpenAICompatibleProvider, AnthropicProvider


@pytest.fixture(autouse=True)
def _stub_rate_limiter(monkeypatch):
    """Make the provider path hermetic — skip Redis-backed rate limiting."""
    import services.model_provider as mp

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(mp.provider_rate_limiter, "acquire", _noop)
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire_concurrency", _noop)
    monkeypatch.setattr(mp.provider_rate_limiter, "release_concurrency", _noop)


class _FakeConfig:
    """Minimal UserModelConfig stand-in for request-building tests."""

    def __init__(self, provider, base_url="https://api.example.com/v1"):
        self.id = "cfg-test"
        self.provider = provider
        self.api_base_url = base_url
        self.base_url = base_url
        self.api_key_encrypted = None
        self.default_model = "test-model"
        self.max_tokens = 1024
        self.temperature = 0.7
        self.top_p = 1.0
        self.timeout_seconds = 30
        self.max_concurrent_requests = 10
        self.requests_per_minute = 60
        self.effort = "none"

    def requires_api_key(self):
        return self.provider != ProviderType.LOCAL

    def get_effective_base_url(self):
        if self.provider == ProviderType.LOCAL:
            return "http://localhost:11434"
        return self.api_base_url


class _Capture:
    def __init__(self):
        self.kwargs = {}

    def record(self, **kwargs):
        self.kwargs.update(kwargs)
        return self._response()


class _OpenAIMessage:
    content = "ok"
    tool_calls = None


class _OpenAIChoice:
    message = _OpenAIMessage()
    finish_reason = "stop"


class _OpenAIUsage:
    prompt_tokens = 1
    completion_tokens = 1


class _OpenAIResponse:
    model = "test-model"
    choices = [_OpenAIChoice()]
    usage = _OpenAIUsage()


class _AnthropicBlock:
    text = "ok"


class _AnthropicUsage:
    input_tokens = 1
    output_tokens = 1


class _AnthropicResponse:
    model = "test-model"
    content = [_AnthropicBlock()]
    usage = _AnthropicUsage()
    stop_reason = "end_turn"


class _OpenAICapture(_Capture):
    """Captures chat.completions.create(**kwargs) and returns a valid response."""

    def _response(self):
        return _OpenAIResponse()


class _AnthropicCapture(_Capture):
    """Captures messages.create(**kwargs) and returns a valid response."""

    def _response(self):
        return _AnthropicResponse()


def _fake_client_factory(capture):
    """Build an SDK-shaped fake client for either provider family."""

    class _Completions:
        def __init__(self, cap):
            self._cap = cap

        async def create(self, **kwargs):
            self._cap.record(**kwargs)
            if kwargs.get("stream"):
                # Yield a single text chunk so stream_generate can iterate.
                chunk = _types.SimpleNamespace(
                    choices=[_types.SimpleNamespace(
                        delta=_types.SimpleNamespace(content="ok"))]
                )
                async def _gen():
                    yield chunk
                return _gen()
            return _OpenAIResponse()

    class _Chat:
        def __init__(self, cap):
            self.completions = _Completions(cap)

    class _Messages:
        def __init__(self, cap):
            self._cap = cap

        async def create(self, **kwargs):
            return self._cap.record(**kwargs)

    class _Client:
        def __init__(self, cap):
            self.chat = _Chat(cap)
            self.messages = _Messages(cap)

    return _Client(capture)


async def test_openai_provider_sends_explicit_system_message(monkeypatch):
    cap = _OpenAICapture()
    client = _fake_client_factory(cap)
    monkeypatch.setattr(
        "services.model_provider._get_cached_sdk_client",
        lambda *a, **k: client,
    )

    provider = OpenAICompatibleProvider(_FakeConfig(ProviderType.OPENAI))
    await provider.generate("SYS: you are the council", "hello")

    messages = cap.kwargs.get("messages", [])
    assert messages, "no messages were sent to the provider"
    assert messages[0]["role"] == "system"
    assert "you are the council" in messages[0]["content"]


async def test_anthropic_provider_sends_explicit_system_message(monkeypatch):
    cap = _AnthropicCapture()
    client = _fake_client_factory(cap)
    monkeypatch.setattr(
        "services.model_provider._get_cached_sdk_client",
        lambda *a, **k: client,
    )

    provider = AnthropicProvider(_FakeConfig(ProviderType.ANTHROPIC))
    await provider.generate("SYS: you are the council", "hello")

    # Anthropic carries the system prompt as a dedicated top-level field,
    # NOT as a `role: "system"` message.
    assert cap.kwargs.get("system") == "SYS: you are the council"
    assert not any(
        m.get("role") == "system" for m in cap.kwargs.get("messages", [])
    )


async def test_openai_provider_stream_sends_explicit_system_message(monkeypatch):
    cap = _OpenAICapture()
    client = _fake_client_factory(cap)
    monkeypatch.setattr(
        "services.model_provider._get_cached_sdk_client",
        lambda *a, **k: client,
    )

    provider = OpenAICompatibleProvider(_FakeConfig(ProviderType.OPENAI))
    async for _ in provider.stream_generate("SYS: system", "hi"):
        pass

    messages = cap.kwargs.get("messages", [])
    assert messages[0]["role"] == "system"


async def test_openai_provider_tools_sends_explicit_system_message(monkeypatch):
    cap = _OpenAICapture()
    client = _fake_client_factory(cap)
    monkeypatch.setattr(
        "services.model_provider._get_cached_sdk_client",
        lambda *a, **k: client,
    )

    provider = OpenAICompatibleProvider(_FakeConfig(ProviderType.OPENAI))

    async def _executor(name, args):
        return "done"

    await provider.generate_with_tools(
        system_prompt="SYS: system",
        messages=[{"role": "user", "content": "do a thing"}],
        tools=[],
        tool_executor=_executor,
    )

    messages = cap.kwargs.get("messages", [])
    assert messages[0]["role"] == "system"
    assert "system" in messages[0]["content"]
