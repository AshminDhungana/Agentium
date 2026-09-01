# backend/tests/unit/test_model_pricing.py
import pytest
from backend.models.entities.model_pricing import ModelPricing

def test_model_pricing_has_context_window_column():
    """ModelPricing entity should have context_window column."""
    pricing = ModelPricing(
        model_id="test-model",
        provider="OPENAI",
        input_rate_per_1m=10.0,
        output_rate_per_1m=30.0,
        context_window=4096
    )
    assert pricing.context_window == 4096

def test_model_pricing_context_window_default():
    """context_window should default to 128000."""
    pricing = ModelPricing(
        model_id="test-model",
        provider="OPENAI",
        input_rate_per_1m=10.0,
        output_rate_per_1m=30.0
    )
    assert pricing.context_window == 128000