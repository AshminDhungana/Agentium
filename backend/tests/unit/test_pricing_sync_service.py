# backend/tests/unit/test_pricing_sync_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.pricing_sync_service import PricingSyncService

@pytest.mark.asyncio
async def test_sync_prices_stores_context_window():
    """sync_prices should extract max_tokens from litellm JSON and store in ModelPricing.context_window."""
    mock_db = MagicMock()
    
    # Create a proper async context manager mock
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "gpt-4o": {
            "input_cost_per_token": 0.0000025,
            "output_cost_per_token": 0.00001,
            "max_tokens": 128000,
            "litellm_provider": "openai"
        },
        "claude-3-opus": {
            "input_cost_per_token": 0.000015,
            "output_cost_per_token": 0.000075,
            "max_tokens": 200000,
            "litellm_provider": "anthropic"
        }
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await PricingSyncService.sync_prices(mock_db)
    
    assert result["success"] is True
    # Verify ModelPricing was called with context_window
    added_model = mock_db.add.call_args[0][0]
    assert hasattr(added_model, 'context_window')
    assert added_model.context_window in [128000, 200000]

@pytest.mark.asyncio
async def test_sync_prices_handles_missing_max_tokens():
    """sync_prices should default to 128000 when max_tokens not in litellm data."""
    mock_db = MagicMock()
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "custom-model": {
            "input_cost_per_token": 0.000001,
            "output_cost_per_token": 0.000002,
            "litellm_provider": "custom"
            # No max_tokens field
        }
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await PricingSyncService.sync_prices(mock_db)
    
    assert result["success"] is True
    added_model = mock_db.add.call_args[0][0]
    assert added_model.context_window == 128000