"""Unit tests for retry_with_validation helper."""
import pytest
from pydantic import BaseModel, Field
from typing import List, Literal
from backend.services.model_provider import retry_with_validation


class TaskResponse(BaseModel):
    title: str
    priority: Literal["high", "normal", "low"]
    tags: List[str] = []


class MockProvider:
    """Mock provider for testing."""

    def __init__(self, responses: List[str]):
        self.responses = responses
        self.call_count = 0

    async def generate(self, system_prompt: str, user_message: str, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            response = self.responses[-1]
        self.call_count += 1

        return {
            "content": response,
            "tokens_used": 100,
            "prompt_tokens": 50,
            "completion_tokens": 50,
            "latency_ms": 100,
            "model": "test-model",
        }


@pytest.mark.asyncio
async def test_invalid_then_valid_on_retry():
    """First invalid, second valid should succeed with 1 retry."""
    provider = MockProvider([
        '{"priority": "high"}',  # missing title - invalid
        '{"title": "Fixed Task", "priority": "normal"}',  # valid
    ])

    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."

    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='{"priority": "high"}',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )

    assert error is not None
    assert error.get("success") is True
    assert model is not None
    assert model.title == "Fixed Task"
    assert model.priority == "normal"
    assert provider.call_count == 2  # Called twice
    assert error.get("attempts") == 2  # 2 attempts total (1 retry)


@pytest.mark.asyncio
async def test_max_retries_exceeded_returns_error():
    """All retries invalid should return error with attempt count."""
    provider = MockProvider([
        '{"priority": "high"}',  # invalid
        '{"title": "x"}',  # invalid - missing priority
        'still invalid',  # invalid
    ])

    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."

    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='{"priority": "high"}',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )

    assert model is None
    assert error is not None
    assert error["type"] == "schema_validation_error"
    assert error["attempts"] == 2  # max_retries
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_valid_on_first_try_no_retry():
    """Valid content on first try should not call provider again."""
    provider = MockProvider([
        '{"title": "Valid Task", "priority": "high"}',
    ])

    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."

    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='{"title": "Valid Task", "priority": "high"}',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )

    assert error is None
    assert model is not None
    assert provider.call_count == 0  # No retry needed


@pytest.mark.asyncio
async def test_markdown_fence_retry():
    """Content in markdown fences should be extracted and validated."""
    provider = MockProvider([
        '```json\n{"priority": "high"}\n```',  # missing title - invalid
        '{"title": "Fixed", "priority": "low"}',  # valid
    ])

    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."

    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='```json\n{"priority": "high"}\n```',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )

    assert error is not None
    assert error.get("success") is True
    assert model is not None
    assert model.title == "Fixed"
    assert model.priority == "low"
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_retry_uses_response_format_when_provider_supports():
    """OpenAI-compatible provider should use response_format on retry."""
    class FormatTrackingProvider(MockProvider):
        def __init__(self, responses):
            super().__init__(responses)
            self.last_response_format = None
            # Add config to simulate OpenAI-compatible provider
            from types import SimpleNamespace
            self.config = SimpleNamespace()
            self.config.provider = "OPENAI"

        async def generate(self, system_prompt: str, user_message: str, **kwargs):
            self.last_response_format = kwargs.get("response_format")
            return await super().generate(system_prompt, user_message, **kwargs)

    provider = FormatTrackingProvider([
        '{"priority": "high"}',  # invalid
        '{"title": "Fixed", "priority": "normal"}',  # valid
    ])

    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."

    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='{"priority": "high"}',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )

    assert error is not None
    assert error.get("success") is True
    assert model is not None
    # Verify response_format was passed on retry
    assert provider.last_response_format is not None
    assert provider.last_response_format["type"] == "json_schema"
    assert "json_schema" in provider.last_response_format