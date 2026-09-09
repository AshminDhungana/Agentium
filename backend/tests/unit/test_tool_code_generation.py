"""Tests for ToolCodeGenerationService - natural language to tool code generation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.tool_code_generation import ToolCodeGenerationService
from backend.models.schemas.tool_creation import ToolParameter


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.agentium_id = "00001"
    return agent


@pytest.fixture
def mock_llm_client():
    with patch("backend.services.tool_code_generation.LLMClient") as mock:
        client_instance = AsyncMock()
        client_instance.generate = AsyncMock(return_value={
            "content": "result = {'emails': ['test@example.com']}"
        })
        mock.return_value = client_instance
        yield client_instance


@pytest.mark.asyncio
async def test_generate_returns_code_template_and_tool_name(mock_db, mock_agent, mock_llm_client):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class, \
         patch("backend.services.tool_code_generation.ToolFactory") as mock_factory_class:
        
        mock_llm_class.return_value = mock_llm_client
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCodeGenerationService(mock_db)
        result = await service.generate(
            description="Extract emails from a webpage",
            agent_id="00001",
            tool_name="extract_emails"
        )
        
        assert "code_template" in result
        assert result["tool_name"] == "extract_emails"
        assert isinstance(result["parameters"], list)
        mock_llm_client.generate.assert_called_once()
        mock_factory.validate_tool_code.assert_called_once()


@pytest.mark.asyncio
async def test_generate_derives_tool_name_from_description(mock_db, mock_agent, mock_llm_client):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class, \
         patch("backend.services.tool_code_generation.ToolFactory") as mock_factory_class:
        
        mock_llm_class.return_value = mock_llm_client
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCodeGenerationService(mock_db)
        result = await service.generate(
            description="Fetch a webpage and extract all email addresses",
            agent_id="00001"
        )
        
        assert result["tool_name"] == "fetch_a_webpage_and_extract_all_email_addresses"


@pytest.mark.asyncio
async def test_generate_raises_on_validation_failure(mock_db, mock_agent, mock_llm_client):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class, \
         patch("backend.services.tool_code_generation.ToolFactory") as mock_factory_class:
        
        mock_llm_class.return_value = mock_llm_client
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": False, "error": "Dangerous construct: eval()"}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCodeGenerationService(mock_db)
        
        with pytest.raises(ValueError, match="Dangerous construct: eval"):
            await service.generate(
                description="Run eval on user input",
                agent_id="00001"
            )


@pytest.mark.asyncio
async def test_generate_raises_on_llm_failure(mock_db, mock_agent):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class:
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(side_effect=Exception("LLM unavailable"))
        mock_llm_class.return_value = mock_client
        
        service = ToolCodeGenerationService(mock_db)
        
        with pytest.raises(ValueError, match="Code generation failed"):
            await service.generate(
                description="Simple tool",
                agent_id="00001"
            )


@pytest.mark.asyncio
async def test_generate_raises_on_unknown_agent(mock_db):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class:
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value={"content": "result = {'ok': True}"})
        mock_llm_class.return_value = mock_client
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        service = ToolCodeGenerationService(mock_db)
        
        with pytest.raises(ValueError, match="Unknown agent"):
            await service.generate(
                description="Simple tool",
                agent_id="99999"
            )


@pytest.mark.asyncio
async def test_generate_strips_markdown_fences(mock_db, mock_agent, mock_llm_client):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class, \
         patch("backend.services.tool_code_generation.ToolFactory") as mock_factory_class:
        
        mock_llm_client.generate.return_value = {"content": "```python\nresult = {'ok': True}\n```"}
        mock_llm_class.return_value = mock_llm_client
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCodeGenerationService(mock_db)
        result = await service.generate(
            description="Simple tool",
            agent_id="00001"
        )
        
        assert result["code_template"] == "result = {'ok': True}"