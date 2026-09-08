"""
Quick smoke tests for deep_think_tool.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class MockDB:
    def __init__(self, configs=None):
        self.configs = configs or []

    def query(self, model):
        return self

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return self.configs


class MockUserConfig:
    def __init__(self, provider, default_model, api_key, is_active=True, connection_status="ACTIVE"):
        self.provider = provider
        self.default_model = default_model
        self.api_key = api_key
        self.is_active = is_active
        self.connection_status = connection_status


class MockAnthropicResponse:
    def __init__(self, thinking_text, conclusion):
        self.content = [
            MagicMock(type="thinking", thinking=thinking_text),
            MagicMock(type="text", text=conclusion),
        ]
        self.usage = MagicMock(input_tokens=100, output_tokens=200)
        self.model = "claude-3-7-sonnet-20250219"


class MockAnthropicClient:
    def __init__(self, response):
        self.response = response

    async def messages_create(self, **kwargs):
        return self.response

    def __getattr__(self, name):
        if name == "messages":
            return MagicMock(create=self.messages_create)
        return MagicMock()


def test_deep_think_no_config():
    from backend.tools.deep_think_tool import deep_think_tool

    result = asyncio_run(deep_think_tool.execute(
        problem="What is 2+2?",
        context=None,
        db=None,
        agent_id="30001"
    ))
    assert result["status"] == "success"
    assert result["provider_path"] == "no_config"
    assert "thinking" in result["thinking_text"].lower()


def test_deep_think_anthropic_native(monkeypatch):
    from backend.tools.deep_think_tool import deep_think_tool
    import backend.tools.deep_think_tool as dtt

    mock_response = MockAnthropicResponse(
        thinking_text="<understand>2+2</understand><decide>4</decide>",
        conclusion="The answer is 4."
    )
    mock_client = MockAnthropicClient(mock_response)

    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda api_key: mock_client)

    db = MockDB(configs=[
        MockUserConfig(
            provider="ANTHROPIC",
            default_model="claude-3-7-sonnet-20250219",
            api_key="test-key"
        )
    ])

    result = asyncio_run(deep_think_tool.execute(
        problem="What is 2+2?",
        context="Math problem",
        db=db,
        agent_id="00001",
        budget_tokens=1024
    ))
    assert result["status"] == "success"
    assert result["provider_path"] == "anthropic_native"
    assert result["model_used"] == "claude-3-7-sonnet-20250219"
    assert "4" in result["conclusion"]


def test_deep_think_cot_fallback(monkeypatch):
    from backend.tools.deep_think_tool import deep_think_tool
    import backend.services.model_provider as mp

    class MockProvider:
        def __init__(self, config=None):
            self.config = config

        async def generate(self, **kwargs):
            return {
                "content": "<thinking><decide>Answer is 4</decide></thinking>The answer is 4.",
                "model": "gpt-4",
                "tokens_used": 150
            }

    # Add the missing method to ModelService class before patching
    mp.ModelService._get_provider_class = classmethod(lambda cls, provider: MockProvider)

    db = MockDB(configs=[
        MockUserConfig(
            provider="OPENAI",
            default_model="gpt-4",
            api_key="test-key"
        )
    ])

    result = asyncio_run(deep_think_tool.execute(
        problem="What is 2+2?",
        db=db,
        agent_id="00001"
    ))
    assert result["status"] == "success"
    assert result["provider_path"] == "cot_prompt"
    assert "4" in result["conclusion"]


def test_deep_think_no_action():
    from backend.tools.deep_think_tool import deep_think_tool

    # There's no explicit "help" action - it falls through to no_config
    result = asyncio_run(deep_think_tool.execute(
        problem="test problem",
        db=None
    ))
    assert result["status"] == "success"
    assert result["provider_path"] == "no_config"
    assert "thinking" in result["thinking_text"].lower()


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)