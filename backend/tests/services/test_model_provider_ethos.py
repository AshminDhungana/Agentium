import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.model_provider import ModelService
from backend.models.entities.agents import Agent


@pytest.mark.asyncio
async def test_generate_with_agent_uses_get_system_prompt():
    """Verify generate_with_agent_tools calls agent.get_system_prompt with channel."""
    agent = MagicMock(spec=Agent)
    agent.agentium_id = "30001"
    agent.get_system_prompt = MagicMock(return_value="FULL PERSONA PROMPT")
    agent.ethos = MagicMock()
    agent.ethos.mission_statement = "Old mission"
    agent.ethos.behavioral_rules = '["rule1"]'
    
    # Mock the provider's generate_with_tools
    mock_provider = AsyncMock()
    mock_provider.generate_with_tools = AsyncMock(return_value={
        "content": "Response",
        "cost_usd": 0.0,
        "tokens_used": 100,
    })
    
    with patch('backend.services.model_provider.ModelService.get_provider', return_value=mock_provider):
        with patch('backend.services.api_key_manager.api_key_manager'):
            service = ModelService()
            result = await service.generate_with_agent_tools(
                agent=agent,
                user_message="Test",
                db=MagicMock(),
                channel="text"
            )
    
    # Verify get_system_prompt was called with channel
    agent.get_system_prompt.assert_called_once()
    call_kwargs = agent.get_system_prompt.call_args.kwargs
    assert call_kwargs.get("channel") == "text"


@pytest.mark.asyncio
async def test_generate_with_agent_voice_channel():
    """Verify voice channel gets VOICE_ADAPTATION."""
    agent = MagicMock(spec=Agent)
    agent.agentium_id = "30001"
    agent.get_system_prompt = MagicMock(return_value="VOICE PERSONA")
    agent.ethos = MagicMock()
    agent.ethos.mission_statement = "Mission"
    agent.ethos.behavioral_rules = "[]"
    
    mock_provider = AsyncMock()
    mock_provider.generate_with_tools = AsyncMock(return_value={
        "content": "Response",
        "cost_usd": 0.0,
        "tokens_used": 100,
    })
    
    with patch('backend.services.model_provider.ModelService.get_provider', return_value=mock_provider):
        with patch('backend.services.api_key_manager.api_key_manager'):
            service = ModelService()
            result = await service.generate_with_agent_tools(
                agent=agent,
                user_message="Test",
                db=MagicMock(),
                channel="voice"
            )
    
    call_args = agent.get_system_prompt.call_args
    assert call_args.kwargs.get("channel") == "voice"
    assert call_args.kwargs.get("db") is not None