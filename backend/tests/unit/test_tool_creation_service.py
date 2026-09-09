"""Tests for ToolCreationService - natural language tool creation."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from backend.services.tool_creation_service import ToolCreationService
from backend.models.schemas.tool_creation import ToolCreationRequest


def test_create_from_natural_language_head_auto_activates():
    db = MagicMock()
    
    with patch("backend.services.tool_creation_service.ToolCodeGenerationService") as mock_gen_class, \
         patch("backend.services.tool_creation_service.ToolFactory") as mock_factory_class:
        
        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(return_value={
            "code_template": "result = {'emails': ['test@example.com']}",
            "tool_name": "extract_emails",
            "parameters": []
        })
        mock_gen_class.return_value = mock_gen
        
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        # Mock propose_tool to return auto-activated result
        with patch.object(ToolCreationService, "propose_tool", return_value={
            "proposed": True,
            "tool_name": "extract_emails",
            "status": "activated",
            "activated": True,
            "version": "v1.0.0"
        }):
            service = ToolCreationService(db)
            import asyncio
            result = asyncio.run(service.create_from_natural_language(
                description="Extract emails from webpage",
                agent_id="00001"
            ))
        
        assert result["proposed"] is True
        assert result["tool_name"] == "extract_emails"
        assert result["status"] == "activated"


def test_create_from_natural_language_council_requires_vote():
    db = MagicMock()
    
    with patch("backend.services.tool_creation_service.ToolCodeGenerationService") as mock_gen_class, \
         patch("backend.services.tool_creation_service.ToolFactory") as mock_factory_class:
        
        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(return_value={
            "code_template": "result = {'data': 'test'}",
            "tool_name": "council_tool",
            "parameters": []
        })
        mock_gen_class.return_value = mock_gen
        
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        # Mock propose_tool to return vote-required result
        with patch.object(ToolCreationService, "propose_tool", return_value={
            "proposed": True,
            "tool_name": "council_tool",
            "status": "pending_vote",
            "voting_id": "vote-123",
            "requires_council_approval": True,
            "council_members": ["10001", "10002"]
        }):
            service = ToolCreationService(db)
            import asyncio
            result = asyncio.run(service.create_from_natural_language(
                description="Council tool",
                agent_id="10001"
            ))
        
        assert result["proposed"] is True
        assert result["status"] == "pending_vote"
        assert result["requires_council_approval"] is True


def test_create_from_natural_language_blocks_task_agent():
    db = MagicMock()
    
    service = ToolCreationService(db)
    import asyncio
    result = asyncio.run(service.create_from_natural_language(
        description="Task agent tool",
        agent_id="30001"
    ))
    
    assert result["proposed"] is False
    assert "Task agents cannot create tools" in result["error"]


def test_create_from_natural_language_passes_authorized_tiers():
    db = MagicMock()
    
    with patch("backend.services.tool_creation_service.ToolCodeGenerationService") as mock_gen_class, \
         patch("backend.services.tool_creation_service.ToolFactory") as mock_factory_class:
        
        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(return_value={
            "code_template": "result = {'ok': True}",
            "tool_name": "custom_tiers_tool",
            "parameters": []
        })
        mock_gen_class.return_value = mock_gen
        
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        with patch.object(ToolCreationService, "propose_tool") as mock_propose:
            mock_propose.return_value = {"proposed": True, "tool_name": "custom_tiers_tool", "status": "activated"}
            
            service = ToolCreationService(db)
            import asyncio
            asyncio.run(service.create_from_natural_language(
                description="Tool with custom tiers",
                agent_id="10001",
                authorized_tiers=["0xxxx", "1xxxx", "2xxxx"]
            ))
            
            # Verify propose_tool was called with correct authorized_tiers
            call_args = mock_propose.call_args[0][0]
            assert isinstance(call_args, ToolCreationRequest)
            assert call_args.authorized_tiers == ["0xxxx", "1xxxx", "2xxxx"]


def test_create_from_natural_language_handles_generation_error():
    db = MagicMock()
    
    with patch("backend.services.tool_creation_service.ToolCodeGenerationService") as mock_gen_class, \
         patch("backend.services.tool_creation_service.ToolFactory") as mock_factory_class:
        
        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(side_effect=ValueError("Code generation failed: LLM error"))
        mock_gen_class.return_value = mock_gen
        
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCreationService(db)
        import asyncio
        result = asyncio.run(service.create_from_natural_language(
            description="Simple tool",
            agent_id="00001"
        ))
    
    assert result["proposed"] is False
    assert "Code generation failed" in result["error"]