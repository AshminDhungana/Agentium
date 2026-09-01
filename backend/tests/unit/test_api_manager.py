# backend/tests/unit/test_api_manager.py
import pytest
from unittest.mock import MagicMock, patch
from backend.services.api_manager import ModelConfig, APIManager
from backend.models.entities.user_config import UserModelConfig, ProviderType

def test_model_config_has_context_window_field():
    """ModelConfig dataclass should have context_window field."""
    config = ModelConfig(
        provider="OPENAI",
        model_name="gpt-4o",
        config_id="test-config-id",
        cost_per_1k_tokens=0.01,
        max_context_length=4000,
        rate_limit_per_minute=60,
        capability="CODE",
        context_window=128000  # NEW FIELD
    )
    assert config.context_window == 128000

def test_model_config_context_window_default():
    """context_window should default to 128000."""
    config = ModelConfig(
        provider="OPENAI",
        model_name="gpt-4o",
        config_id="test-config-id",
        cost_per_1k_tokens=0.01,
        max_context_length=4000,
        rate_limit_per_minute=60,
        capability="CODE"
        # context_window not provided
    )
    assert config.context_window == 128000

def test_config_to_model_populates_context_window_from_pricing():
    """_config_to_model should populate context_window from PricingSyncService."""
    mock_db = MagicMock()
    
    # Create mock UserModelConfig
    user_config = MagicMock(spec=UserModelConfig)
    user_config.id = "config-123"
    user_config.provider = ProviderType.OPENAI
    user_config.default_model = "gpt-4o"
    user_config.max_tokens = 4000
    user_config.requests_per_minute = 60
    user_config.is_key_healthy.return_value = True
    
    # Mock PricingSyncService.get_price to return (input_rate, output_rate, context_window)
    # The import is inside the method, so we patch at the module where it's used
    with patch("backend.services.pricing_sync_service.PricingSyncService.get_price") as mock_get_price:
        mock_get_price.return_value = (2.5, 10.0, 128000)
        
        api_manager = APIManager(mock_db)
        model_config = api_manager._config_to_model(user_config)
    
    assert model_config is not None
    assert model_config.context_window == 128000
    # Called twice: once for cache check (no db), once for DB lookup
    assert mock_get_price.call_count == 2
    mock_get_price.assert_any_call("gpt-4o")
    mock_get_price.assert_any_call("gpt-4o", mock_db)