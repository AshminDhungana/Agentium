# backend/tests/unit/test_token_optimizer.py
import pytest
from unittest.mock import MagicMock, patch
from backend.services.token_optimizer import TokenOptimizer

def test_trim_context_for_agent_respects_context_window():
    """trim_context_for_agent should trim messages to fit within context_window * 0.85 - system_tokens."""
    optimizer = TokenOptimizer()
    
    # Mock api_manager with a model that has small context_window
    mock_model = MagicMock()
    mock_model.context_window = 4096  # Small context window
    
    with patch("backend.services.token_optimizer.api_manager_module.api_manager") as mock_api_manager:
        mock_api_manager.models = {"config-123": mock_model}
        
        # System prompt ~100 tokens, each message ~50 tokens
        system_prompt = "x" * 400  # ~100 tokens
        messages = [
            {"role": "user", "content": "a" * 200},   # ~50 tokens
            {"role": "assistant", "content": "b" * 200}, # ~50 tokens
            {"role": "user", "content": "c" * 200},   # ~50 tokens
            {"role": "assistant", "content": "d" * 200}, # ~50 tokens
            {"role": "user", "content": "e" * 200},   # ~50 tokens
        ]  # Total ~350 tokens
        
        # Available = 4096 * 0.85 - 100 = ~3381 tokens
        # All messages fit, should return all
        result = optimizer.trim_context_for_agent(messages, system_prompt, "config-123")
        assert len(result) == 5
    
def test_trim_context_for_agent_trims_when_over_budget():
    """trim_context_for_agent should drop oldest messages when over budget."""
    optimizer = TokenOptimizer()
    
    mock_model = MagicMock()
    mock_model.context_window = 256  # Very small context window
    
    with patch("backend.services.token_optimizer.api_manager_module.api_manager") as mock_api_manager:
        mock_api_manager.models = {"config-123": mock_model}
        
        system_prompt = "x" * 400  # ~100 tokens
        messages = [
            {"role": "user", "content": "a" * 200},   # ~50 tokens
            {"role": "assistant", "content": "b" * 200}, # ~50 tokens
            {"role": "user", "content": "c" * 200},   # ~50 tokens
            {"role": "assistant", "content": "d" * 200}, # ~50 tokens
            {"role": "user", "content": "e" * 200},   # ~50 tokens
        ]  # Total ~350 tokens
        
        # Available = 512 * 0.85 - 100 = ~335 tokens
        # 350 > 335 so some will be trimmed
        many_messages = messages * 4  # 20 messages ~1400 tokens
        
        result = optimizer.trim_context_for_agent(many_messages, system_prompt, "config-123")
        # Should keep most recent messages that fit
        assert len(result) < len(many_messages)
        # Should preserve the LAST message
        assert result[-1]["content"] == "e" * 200

def test_trim_context_for_agent_defaults_when_model_not_found():
    """Should default to 128000 when model config not found."""
    optimizer = TokenOptimizer()
    
    with patch("backend.services.token_optimizer.api_manager_module.api_manager") as mock_api_manager:
        mock_api_manager.models = {}  # Empty - model not found
        
        system_prompt = "x" * 400
        messages = [{"role": "user", "content": "test"}]
        
        # Should not crash, use default 128000
        result = optimizer.trim_context_for_agent(messages, system_prompt, "nonexistent")
        assert result == messages  # All fit in default 128000

def test_trim_context_for_agent_keeps_last_message():
    """Even when aggressively trimming, should keep at least the last message."""
    optimizer = TokenOptimizer()
    
    mock_model = MagicMock()
    mock_model.context_window = 100  # Tiny - only fits ~85 tokens after reserve
    
    with patch("backend.services.token_optimizer.api_manager_module.api_manager") as mock_api_manager:
        mock_api_manager.models = {"config-123": mock_model}
        
        system_prompt = "x" * 400  # 100 tokens - already over budget!
        messages = [
            {"role": "user", "content": "a" * 200},
            {"role": "assistant", "content": "b" * 200},
        ]
        
        result = optimizer.trim_context_for_agent(messages, system_prompt, "config-123")
        # Should keep at least the last message
        assert len(result) >= 1
        assert result[-1]["content"] == "b" * 200