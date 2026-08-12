# backend/tests/integration/test_uncertainty_clarification.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from backend.services.model_provider import OpenAICompatibleProvider, ModelService
from backend.core.uncertainty_detector import UncertaintySignal


@pytest.fixture
def mock_config():
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
    config.effort = "none"
    return config


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.agentium_id = "30001"
    agent.ethos = MagicMock()
    agent.ethos.mission_statement = "Test mission"
    agent.ethos.behavioral_rules = "[]"
    # Mock parent for clarification
    parent = MagicMock()
    parent.agentium_id = "20001"
    parent.agent_type.value = "lead_agent"
    agent.parent = parent
    return agent


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_api_key_manager():
    """Mock the api_key_manager that's imported inside model_provider functions."""
    with patch("backend.services.api_key_manager.api_key_manager") as mock:
        mock.mark_key_success = MagicMock()
        mock.record_spend = MagicMock()
        mock.mark_key_failed = MagicMock()
        yield mock


@pytest.mark.asyncio
async def test_generate_with_tools_injects_clarification_on_tool_error(mock_config, mock_agent, mock_db, mock_api_key_manager):
    """Tool error triggers clarification which is injected as system message before next LLM turn."""
    provider = OpenAICompatibleProvider(config=mock_config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"

    # Mock the client
    mock_client = AsyncMock()

    # First call: LLM calls a tool - create proper mock objects
    first_msg = MagicMock()
    first_msg.content = None
    first_msg.tool_calls = [
        MagicMock(
            id="call_1",
            function=MagicMock(name="read_file", arguments='{"filepath": "/nonexistent.txt"}')
        )
    ]

    first_choice = MagicMock()
    first_choice.message = first_msg
    first_choice.finish_reason = "tool_calls"

    first_response = MagicMock()
    first_response.choices = [first_choice]
    first_response.model = "gpt-4o"
    first_response.usage = MagicMock(prompt_tokens=50, completion_tokens=50)

    # Second call: after tool execution + clarification injection, LLM responds
    second_msg = MagicMock()
    second_msg.content = "I understand, I'll use a different approach."
    second_msg.tool_calls = None

    second_choice = MagicMock()
    second_choice.message = second_msg
    second_choice.finish_reason = "stop"

    second_response = MagicMock()
    second_response.choices = [second_choice]
    second_response.model = "gpt-4o"
    second_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

    mock_client.chat.completions.create = AsyncMock(side_effect=[first_response, second_response])

    # Patch the cached client
    import backend.services.model_provider as mp
    cache_key = (str(mock_config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client

    try:
        # Mock tool executor to return error - tool_executor returns JSON string
        async def mock_tool_executor(name, args):
            import json
            return json.dumps({"status": "error", "tool_name": name, "error": "File not found", "result": None})

        # Mock UncertaintyDetector to return signal
        with patch("backend.services.model_provider.UncertaintyDetector.analyze") as mock_analyze, \
             patch("backend.services.model_provider.ClarificationHandler") as mock_handler_class, \
             patch("backend.services.model_provider.provider_rate_limiter.acquire_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.acquire", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.release_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider._record_provider_headers", new=AsyncMock()), \
             patch.object(provider, '_log_usage', new=AsyncMock()):

            mock_analyze.return_value = UncertaintySignal(
                reason="tool_error",
                affected_tools=["read_file"],
                details={"status": "error", "error": "File not found"},
                suggested_question="My tool 'read_file' returned an error: File not found. What should I do?",
                severity="high"
            )

            mock_handler = AsyncMock()
            mock_handler.handle_uncertainty = AsyncMock(return_value=(True, "CLARIFICATION FROM LEAD_AGENT (20001) — supervisor\nOriginal uncertainty: tool_error in tools ['read_file']\nGuidance: Use browser tool instead"))
            mock_handler_class.return_value = mock_handler
            mock_handler.clarification_rounds = 1

            # Debug: add logging inside the generate_with_tools
            import backend.services.model_provider as mp_module
            original_method = mp_module.OpenAICompatibleProvider.generate_with_tools
            async def debug_method(self, *args, **kwargs):
                print("DEBUG: generate_with_tools called")
                try:
                    result = await original_method(self, *args, **kwargs)
                    print(f"DEBUG: generate_with_tools returned: {result}")
                    return result
                except Exception as e:
                    print(f"DEBUG: Exception in generate_with_tools: {e}")
                    import traceback
                    traceback.print_exc()
                    raise
            mp_module.OpenAICompatibleProvider.generate_with_tools = debug_method

            result = await provider.generate_with_tools(
                system_prompt="You are a helpful agent.",
                messages=[{"role": "user", "content": "Read a file"}],
                tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
                tool_executor=mock_tool_executor,
                max_iterations=5,
                agentium_id="30001",
                agent=mock_agent,
            )

            # Debug: print what we got
            print(f"DEBUG: result = {result}")
            print(f"DEBUG: calls = {mock_client.chat.completions.create.call_args_list}")

            # Verify clarification was injected (check conversation had system message added)
            # The second call to create should include the clarification system message
            calls = mock_client.chat.completions.create.call_args_list
            assert len(calls) == 2, f"Expected 2 calls, got {len(calls)}"

            # Second call should have clarification in messages
            second_call_messages = calls[1].kwargs["messages"]
            # Find system message with clarification
            clarification_found = any(
                msg.get("role") == "system" and "CLARIFICATION" in msg.get("content", "")
                for msg in second_call_messages
            )
            assert clarification_found, "Clarification system message not injected"

    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]


@pytest.mark.asyncio
async def test_generate_with_tools_continues_without_clarification_when_clear(mock_config, mock_agent, mock_db, mock_api_key_manager):
    """Clean tool results don't trigger clarification."""
    provider = OpenAICompatibleProvider(config=mock_config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"

    mock_client = AsyncMock()
    # First call: LLM calls a tool
    first_response = MagicMock()
    first_response.choices = [MagicMock()]
    first_response.choices[0].message = MagicMock()
    first_response.choices[0].message.tool_calls = [
        MagicMock(
            id="call_1",
            function=MagicMock(name="read_file", arguments='{"filepath": "/test.txt"}')
        )
    ]
    first_response.choices[0].finish_reason = "tool_calls"
    first_response.model = "gpt-4o"
    first_response.usage = MagicMock(prompt_tokens=50, completion_tokens=50)

    # Second call: LLM responds with final content
    second_response = MagicMock()
    second_response.choices = [MagicMock()]
    second_response.choices[0].message = MagicMock()
    second_response.choices[0].message.content = "Done"
    second_response.choices[0].message.tool_calls = None
    second_response.choices[0].finish_reason = "stop"
    second_response.model = "gpt-4o"
    second_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

    mock_client.chat.completions.create = AsyncMock(side_effect=[first_response, second_response])

    import backend.services.model_provider as mp
    cache_key = (str(mock_config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client

    try:
        async def mock_tool_executor(name, args):
            import json
            return json.dumps({"status": "success", "tool_name": name, "result": {"content": "file data"}})

        with patch("backend.services.model_provider.UncertaintyDetector.analyze") as mock_analyze, \
             patch("backend.services.model_provider.provider_rate_limiter.acquire_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.acquire", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.release_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider._record_provider_headers", new=AsyncMock()), \
             patch.object(provider, '_log_usage', new=AsyncMock()):

            mock_analyze.return_value = None  # No uncertainty

            result = await provider.generate_with_tools(
                system_prompt="You are a helpful agent.",
                messages=[{"role": "user", "content": "Read a file"}],
                tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
                tool_executor=mock_tool_executor,
                max_iterations=5,
                agentium_id="30001",
                agent=mock_agent,
            )

            assert result["content"] == "Done"
            # UncertaintyDetector.analyze should have been called once
            mock_analyze.assert_called_once()

    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]