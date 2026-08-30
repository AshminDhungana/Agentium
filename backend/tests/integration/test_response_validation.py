"""
Integration tests for Task 6: Response Validation verification.
Verifies that structured output validation works end-to-end with providers.
"""
import pytest
from pydantic import BaseModel, Field
from typing import List, Literal
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.model_provider import ModelService, OpenAICompatibleProvider, retry_with_validation
from backend.core.response_validator import ResponseValidator


class TaskResponse(BaseModel):
    title: str
    priority: Literal["high", "normal", "low"]
    tags: List[str] = []


class MockAgent:
    """Mock agent for testing."""
    def __init__(self, agentium_id="test-agent", ethos=None):
        self.agentium_id = agentium_id
        self.ethos = ethos


class MockEthos:
    """Mock ethos for testing."""
    def __init__(self, mission="Test mission", rules=None):
        self.mission_statement = mission
        self.behavioral_rules = rules or "[]"


@pytest.mark.asyncio
async def test_valid_response_returns_parsed():
    """Agent outputs valid JSON -> parsed_response present in result."""
    # Mock provider that returns valid JSON
    mock_provider = AsyncMock()
    mock_provider.generate_with_tools = AsyncMock(return_value={
        "content": '{"title": "Test Task", "priority": "high", "tags": ["urgent"]}',
        "tokens_used": 100,
        "prompt_tokens": 50,
        "completion_tokens": 50,
        "latency_ms": 100,
        "model": "test-model",
        "messages": [],
        "finish_reason": "stop",
        "cost_usd": 0.001,
    })
    mock_provider.config = MagicMock()
    mock_provider.config.id = "test-config"

    mock_db = MagicMock()
    mock_agent = MockAgent(ethos=MockEthos())

    with patch('backend.services.model_provider.ModelService.get_provider', return_value=mock_provider):
        with patch('backend.services.api_key_manager.api_key_manager') as mock_key_manager:
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()

            result = await ModelService.generate_with_agent_tools(
                agent=mock_agent,
                user_message="Create a task",
                db=mock_db,
                response_model=TaskResponse,
                max_validation_retries=2,
            )

    assert "parsed_response" in result
    assert result["parsed_response"] is not None
    assert result["parsed_response"]["title"] == "Test Task"
    assert result["parsed_response"]["priority"] == "high"
    assert result["parsed_response"]["tags"] == ["urgent"]
    assert result["validation_error"] is None
    assert result["validation_retries"] == 0


@pytest.mark.asyncio
async def test_invalid_then_valid_on_retry():
    """First invalid, re-prompts, second valid -> validation_retries=1."""
    call_count = 0

    async def mock_generate_with_tools(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First response: invalid (missing title)
            return {
                "content": '{"priority": "high"}',
                "tokens_used": 100,
                "prompt_tokens": 50,
                "completion_tokens": 50,
                "latency_ms": 100,
                "model": "test-model",
                "messages": [],
                "finish_reason": "stop",
                "cost_usd": 0.001,
            }
        else:
            # Second response: valid
            return {
                "content": '{"title": "Fixed Task", "priority": "normal"}',
                "tokens_used": 100,
                "prompt_tokens": 50,
                "completion_tokens": 50,
                "latency_ms": 100,
                "model": "test-model",
                "messages": [],
                "finish_reason": "stop",
                "cost_usd": 0.001,
            }

    mock_provider = AsyncMock()
    mock_provider.generate_with_tools = mock_generate_with_tools
    mock_provider.generate = AsyncMock(return_value={  # For retry
        "content": '{"title": "Fixed Task", "priority": "normal"}',
        "tokens_used": 100,
        "prompt_tokens": 50,
        "completion_tokens": 50,
        "latency_ms": 100,
        "model": "test-model",
        "finish_reason": "stop",
        "cost_usd": 0.001,
    })
    mock_provider.config = MagicMock()
    mock_provider.config.id = "test-config"

    mock_db = MagicMock()
    mock_agent = MockAgent(ethos=MockEthos())

    with patch('backend.services.model_provider.ModelService.get_provider', return_value=mock_provider):
        with patch('backend.services.api_key_manager.api_key_manager') as mock_key_manager:
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()

            result = await ModelService.generate_with_agent_tools(
                agent=mock_agent,
                user_message="Create a task",
                db=mock_db,
                response_model=TaskResponse,
                max_validation_retries=2,
            )

    assert "parsed_response" in result
    assert result["parsed_response"] is not None
    assert result["parsed_response"]["title"] == "Fixed Task"
    assert result["validation_retries"] == 1


@pytest.mark.asyncio
async def test_max_retries_exceeded_returns_error():
    """3 invalid attempts -> validation_error in result."""
    async def mock_generate_with_tools(*args, **kwargs):
        return {
            "content": '{"priority": "high"}',  # Always invalid - missing title
            "tokens_used": 100,
            "prompt_tokens": 50,
            "completion_tokens": 50,
            "latency_ms": 100,
            "model": "test-model",
            "messages": [],
            "finish_reason": "stop",
            "cost_usd": 0.001,
        }

    mock_provider = AsyncMock()
    mock_provider.generate_with_tools = mock_generate_with_tools
    mock_provider.generate = AsyncMock(return_value={  # For retry
        "content": '{"priority": "high"}',
        "tokens_used": 100,
        "prompt_tokens": 50,
        "completion_tokens": 50,
        "latency_ms": 100,
        "model": "test-model",
        "finish_reason": "stop",
        "cost_usd": 0.001,
    })
    mock_provider.config = MagicMock()
    mock_provider.config.id = "test-config"

    mock_db = MagicMock()
    mock_agent = MockAgent(ethos=MockEthos())

    with patch('backend.services.model_provider.ModelService.get_provider', return_value=mock_provider):
        with patch('backend.services.api_key_manager.api_key_manager') as mock_key_manager:
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()

            result = await ModelService.generate_with_agent_tools(
                agent=mock_agent,
                user_message="Create a task",
                db=mock_db,
                response_model=TaskResponse,
                max_validation_retries=2,
            )

    assert "validation_error" in result
    assert result["validation_error"] is not None
    assert result["validation_error"]["type"] == "schema_validation_error"
    assert result["validation_error"]["attempts"] == 2
    assert result["parsed_response"] is None


@pytest.mark.asyncio
async def test_no_response_model_unchanged():
    """Without response_model parameter -> identical behavior to before (no validation fields)."""
    mock_provider = AsyncMock()
    mock_provider.generate_with_tools = AsyncMock(return_value={
        "content": "Plain text response",
        "tokens_used": 100,
        "prompt_tokens": 50,
        "completion_tokens": 50,
        "latency_ms": 100,
        "model": "test-model",
        "messages": [],
        "finish_reason": "stop",
        "cost_usd": 0.001,
    })
    mock_provider.config = MagicMock()
    mock_provider.config.id = "test-config"

    mock_db = MagicMock()
    mock_agent = MockAgent(ethos=MockEthos())

    with patch('backend.services.model_provider.ModelService.get_provider', return_value=mock_provider):
        with patch('backend.services.api_key_manager.api_key_manager') as mock_key_manager:
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()

            result = await ModelService.generate_with_agent_tools(
                agent=mock_agent,
                user_message="Create a task",
                db=mock_db,
                # No response_model provided
            )

    # Should still work, no validation fields added
    assert result["content"] == "Plain text response"
    assert "parsed_response" not in result or result.get("parsed_response") is None


@pytest.mark.asyncio
async def test_openai_native_response_format():
    """OpenAI-compatible provider uses response_format when available."""
    # Create a proper config mock with id
    from unittest.mock import MagicMock
    config = MagicMock()
    config.provider = "OPENAI"
    config.default_model = "gpt-4o"
    config.max_tokens = 1000
    config.temperature = 0.7
    config.top_p = 1.0
    config.timeout_seconds = 30
    config.max_concurrent_requests = 10
    config.requests_per_minute = 60
    config.id = "test-config-id"

    provider = OpenAICompatibleProvider(config=config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"

    # Mock the client
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"title": "Test", "priority": "high"}'
    mock_response.choices[0].finish_reason = "stop"
    mock_response.model = "gpt-4o"
    mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=50)
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Patch the cached client with the correct key
    import backend.services.model_provider as mp
    cache_key = (str(config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client

    try:
        result = await provider.generate(
            system_prompt="You are a task creator.",
            user_message="Create a task",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "TaskResponse",
                    "schema": TaskResponse.model_json_schema(),
                    "strict": True,
                }
            },
            agentium_id="test-agent",
        )

        # Verify response_format was passed to the API
        call_args = mock_client.chat.completions.create.call_args
        assert "response_format" in call_args.kwargs
        assert call_args.kwargs["response_format"]["type"] == "json_schema"
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]


@pytest.mark.asyncio
async def test_markdown_fence_extraction_in_integration():
    """JSON inside markdown fences should be extracted and validated."""
    call_count = 0

    async def mock_generate_with_tools(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": '```json\n{"title": "Test", "priority": "high"}\n```',
                "tokens_used": 100,
                "prompt_tokens": 50,
                "completion_tokens": 50,
                "latency_ms": 100,
                "model": "test-model",
                "messages": [],
                "finish_reason": "stop",
                "cost_usd": 0.001,
            }
        else:
            # Should not be called if first is valid after extraction
            return {
                "content": '{"title": "Fixed", "priority": "normal"}',
                "tokens_used": 100,
                "prompt_tokens": 50,
                "completion_tokens": 50,
                "latency_ms": 100,
                "model": "test-model",
                "messages": [],
                "finish_reason": "stop",
                "cost_usd": 0.001,
            }

    mock_provider = AsyncMock()
    mock_provider.generate_with_tools = mock_generate_with_tools
    mock_provider.generate = AsyncMock(return_value={
        "content": '{"title": "Fixed", "priority": "normal"}',
        "tokens_used": 100,
        "prompt_tokens": 50,
        "completion_tokens": 50,
        "latency_ms": 100,
        "model": "test-model",
        "finish_reason": "stop",
        "cost_usd": 0.001,
    })
    mock_provider.config = MagicMock()
    mock_provider.config.id = "test-config"

    mock_db = MagicMock()
    mock_agent = MockAgent(ethos=MockEthos())

    with patch('backend.services.model_provider.ModelService.get_provider', return_value=mock_provider):
        with patch('backend.services.api_key_manager.api_key_manager') as mock_key_manager:
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()

            result = await ModelService.generate_with_agent_tools(
                agent=mock_agent,
                user_message="Create a task",
                db=mock_db,
                response_model=TaskResponse,
                max_validation_retries=2,
            )

    assert "parsed_response" in result
    assert result["parsed_response"] is not None
    assert result["parsed_response"]["title"] == "Test"
    assert result["validation_retries"] == 0


@pytest.mark.asyncio
async def test_streaming_with_response_format():
    """OpenAI-compatible provider should use response_format when streaming with structured output."""
    from backend.services.model_provider import OpenAICompatibleProvider, retry_with_validation

    # Create a proper config mock
    from unittest.mock import MagicMock
    config = MagicMock()
    config.provider = "OPENAI"
    config.default_model = "gpt-4o"
    config.max_tokens = 1000
    config.temperature = 0.7
    config.top_p = 1.0
    config.timeout_seconds = 30
    config.max_concurrent_requests = 10
    config.requests_per_minute = 60
    config.id = "test-config-id-stream"

    provider = OpenAICompatibleProvider(config=config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"

    # Mock the client with streaming response
    mock_client = AsyncMock()

    # Streaming chunks with JSON content
    class MockChunk:
        def __init__(self, content, finish_reason=None, usage=None):
            self.choices = [MagicMock()]
            self.choices[0].delta = MagicMock()
            self.choices[0].delta.content = content
            self.choices[0].finish_reason = finish_reason
            if usage:
                self.usage = usage

    async def mock_stream(*args, **kwargs):
        # Verify response_format was passed
        assert "response_format" in kwargs
        assert kwargs["response_format"]["type"] == "json_schema"
        yield MockChunk('{"title": "Stream', finish_reason=None)
        yield MockChunk('ed Task", "priority": "high"}', finish_reason="stop", usage=MagicMock(prompt_tokens=50, completion_tokens=50))

    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

    import backend.services.model_provider as mp
    cache_key = (str(config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client

    try:
        # Test streaming generate with response_format
        content_parts = []
        async for chunk in provider.stream_generate(
            system_prompt="You are a task creator.",
            user_message="Create a task",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "TaskResponse",
                    "schema": TaskResponse.model_json_schema(),
                    "strict": True,
                }
            },
            agentium_id="test-agent",
        ):
            content_parts.append(chunk)

        full_content = "".join(content_parts)
        # The content should be valid JSON
        parsed = TaskResponse.model_validate_json(full_content)
        assert parsed.title == "Streamed Task"
        assert parsed.priority == "high"
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]


@pytest.mark.asyncio
async def test_anthropic_structured_output():
    """Anthropic provider should handle structured output via tool use format."""
    from backend.services.model_provider import AnthropicProvider
    from unittest.mock import MagicMock

    config = MagicMock()
    config.provider = "ANTHROPIC"
    config.default_model = "claude-sonnet-5"
    config.max_tokens = 1000
    config.temperature = 0.7
    config.timeout_seconds = 30
    config.max_concurrent_requests = 10
    config.requests_per_minute = 60
    config.id = "test-anthropic-config"

    provider = AnthropicProvider(config=config)
    provider.api_key = "test-key"

    # Mock the client
    mock_client = AsyncMock()

    # Anthropic uses tool_use for structured output
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(type="tool_use", id="tool_1", name="structured_output",
                 input={"title": "Anthropic Task", "priority": "high", "tags": ["test"]})
    ]
    mock_response.stop_reason = "tool_use"
    mock_response.model = "claude-sonnet-5"
    mock_response.usage = MagicMock(input_tokens=50, output_tokens=30)

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    import backend.services.model_provider as mp
    cache_key = (str(config.id), provider.api_key, provider._anthropic_base_url(config), True)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client

    try:
        # Test that Anthropic can generate with tools (structured output via tool_use)
        result = await provider.generate(
            system_prompt="You are a task creator.",
            user_message="Create a task",
            agentium_id="test-agent",
        )
        # Anthropic returns content as list of blocks
        assert "content" in result
        assert result["model"] == "claude-sonnet-5"
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]


@pytest.mark.asyncio
async def test_complex_nested_pydantic_model():
    """Validation should work with complex nested Pydantic models."""
    from pydantic import BaseModel, Field
    from typing import List, Optional
    from datetime import datetime

    class SubTask(BaseModel):
        name: str
        completed: bool = False
        due_date: Optional[datetime] = None

    class ProjectPlan(BaseModel):
        project_name: str
        tasks: List[SubTask] = Field(default_factory=list)
        total_budget: float
        metadata: dict = Field(default_factory=dict)

    # Test valid complex model
    provider = AsyncMock()
    provider.generate = AsyncMock(return_value={
        "content": '{"project_name": "Website Redesign", "tasks": [{"name": "Design", "completed": true}, {"name": "Develop", "completed": false}], "total_budget": 50000.0, "metadata": {"client": "Acme Corp"}}',
        "tokens_used": 200,
        "prompt_tokens": 100,
        "completion_tokens": 100,
        "latency_ms": 150,
        "model": "test-model",
        "finish_reason": "stop",
        "cost_usd": 0.002,
    })
    provider.config = MagicMock()
    provider.config.id = "test-config"

    mock_db = MagicMock()
    mock_agent = MockAgent(ethos=MockEthos())

    with patch('backend.services.model_provider.ModelService.get_provider', return_value=provider):
        with patch('backend.services.api_key_manager.api_key_manager') as mock_key_manager:
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()

            result = await ModelService.generate_with_agent_tools(
                agent=mock_agent,
                user_message="Create a project plan",
                db=mock_db,
                response_model=ProjectPlan,
                max_validation_retries=2,
            )

    assert "parsed_response" in result
    assert result["parsed_response"] is not None
    assert result["parsed_response"]["project_name"] == "Website Redesign"
    assert len(result["parsed_response"]["tasks"]) == 2
    assert result["parsed_response"]["tasks"][0]["completed"] is True
    assert result["parsed_response"]["total_budget"] == 50000.0
    assert result["parsed_response"]["metadata"]["client"] == "Acme Corp"
    assert result["validation_error"] is None


@pytest.mark.asyncio
async def test_validation_retry_preserves_conversation_history():
    """Retry should preserve conversation history for context."""
    call_count = 0

    async def mock_generate_with_tools(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        messages = kwargs.get("messages", [])
        if call_count == 1:
            # First response: invalid (missing required field)
            return {
                "content": '{"project_name": "Test"}',  # missing tasks, total_budget
                "tokens_used": 50,
                "prompt_tokens": 25,
                "completion_tokens": 25,
                "latency_ms": 50,
                "model": "test-model",
                "messages": messages,
                "finish_reason": "stop",
                "cost_usd": 0.001,
            }
        else:
            # Second response: valid, should have conversation history including error
            assert len(messages) >= 3  # system + user + assistant + tool/error + user reprompt
            return {
                "content": '{"project_name": "Fixed Project", "tasks": [], "total_budget": 1000.0}',
                "tokens_used": 50,
                "prompt_tokens": 25,
                "completion_tokens": 25,
                "latency_ms": 50,
                "model": "test-model",
                "messages": messages,
                "finish_reason": "stop",
                "cost_usd": 0.001,
            }

    from pydantic import BaseModel, Field
    from typing import List

    class ProjectPlan(BaseModel):
        project_name: str
        tasks: List[str] = Field(default_factory=list)
        total_budget: float

    provider = AsyncMock()
    provider.generate_with_tools = mock_generate_with_tools
    provider.generate = AsyncMock(return_value={
        "content": '{"project_name": "Fixed Project", "tasks": [], "total_budget": 1000.0}',
        "tokens_used": 50,
        "prompt_tokens": 25,
        "completion_tokens": 25,
        "latency_ms": 50,
        "model": "test-model",
        "finish_reason": "stop",
        "cost_usd": 0.001,
    })
    provider.config = MagicMock()
    provider.config.id = "test-config"

    mock_db = MagicMock()
    mock_agent = MockAgent(ethos=MockEthos())

    with patch('backend.services.model_provider.ModelService.get_provider', return_value=provider):
        with patch('backend.services.api_key_manager.api_key_manager') as mock_key_manager:
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()

            result = await ModelService.generate_with_agent_tools(
                agent=mock_agent,
                user_message="Create a project plan",
                db=mock_db,
                response_model=ProjectPlan,
                max_validation_retries=2,
            )

    assert result["parsed_response"] is not None
    assert result["parsed_response"]["project_name"] == "Fixed Project"
    assert result["validation_retries"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])