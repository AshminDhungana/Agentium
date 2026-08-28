# tests/unit/test_provider_enum.py
import pytest
from backend.models.entities.user_config import ProviderType

# Minimum required providers per TODO 5.1.4
REQUIRED_PROVIDERS = {
    "OPENAI",
    "ANTHROPIC", 
    "GEMINI",
    "GROQ",
    "DEEPSEEK",
    "MISTRAL",
    "OPENROUTER",
    "XAI",
    "LOCAL",
}

def test_provider_enum_contains_required():
    """ProviderType enum must contain all required providers per TODO 5.1.4."""
    actual = {p.name for p in ProviderType}
    missing = REQUIRED_PROVIDERS - actual
    assert not missing, f"Missing required providers: {missing}"

def test_provider_enum_values_are_uppercase():
    """All enum values must be uppercase strings."""
    for p in ProviderType:
        assert p.value == p.value.upper(), f"{p.name} value not uppercase: {p.value}"
        assert isinstance(p.value, str), f"{p.name} value not string: {type(p.value)}"

def test_provider_enum_no_duplicates():
    """No duplicate values in enum."""
    values = [p.value for p in ProviderType]
    assert len(values) == len(set(values)), "Duplicate provider values found"