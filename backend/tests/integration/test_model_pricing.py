import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text

from backend.models.entities.model_pricing import ModelPricing
from backend.services.pricing_sync_service import PricingSyncService
from backend.services.model_provider import calculate_cost, ProviderType, ModelService
from backend.services.api_manager import APIManager
from backend.models.entities.user_config import UserModelConfig, ConnectionStatus

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pricing_synchronization(db_session):
    """Verify that PricingSyncService can fetch, parse, and persist pricing data."""
    # Ensure database table is empty initially
    db_session.execute(text("DELETE FROM model_pricings"))
    db_session.commit()
    
    # Clean cache
    PricingSyncService._cache.clear()
    PricingSyncService._initialized = False
    
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {
        "gpt-4o-mini": {
            "input_cost_per_token": 0.00000015,   # $0.15 per 1M tokens
            "output_cost_per_token": 0.00000060,  # $0.60 per 1M tokens
            "litellm_provider": "openai"
        },
        "claude-3-5-sonnet": {
            "input_cost_per_token": 0.000003,      # $3.00 per 1M tokens
            "output_cost_per_token": 0.000015,     # $15.00 per 1M tokens
            "litellm_provider": "anthropic"
        },
        "ignored-model": {
            "input_cost_per_token": None,
            "output_cost_per_token": 0.000015
        }
    }
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await PricingSyncService.sync_prices(db_session)
        
    assert result["success"] is True
    assert result["added"] == 2
    assert result["updated"] == 0
    
    # Verify database records
    pricings = db_session.query(ModelPricing).all()
    assert len(pricings) == 2
    
    mini = db_session.query(ModelPricing).filter_by(model_id="gpt-4o-mini").first()
    assert mini is not None
    assert mini.provider == "OPENAI"
    assert mini.input_rate_per_1m == pytest.approx(0.15)
    assert mini.output_rate_per_1m == pytest.approx(0.60)
    
    # Verify in-memory cache
    assert PricingSyncService.get_price("gpt-4o-mini") == (pytest.approx(0.15), pytest.approx(0.60))
    assert PricingSyncService.get_price("GPT-4O-MINI ") == (pytest.approx(0.15), pytest.approx(0.60))  # Case / whitespace insensitivity
    
    # Verify updates
    mock_response.json = lambda: {
        "gpt-4o-mini": {
            "input_cost_per_token": 0.00000020,   # change to $0.20 per 1M tokens
            "output_cost_per_token": 0.00000060,
            "litellm_provider": "openai"
        },
        "claude-3-5-sonnet": {
            "input_cost_per_token": 0.000003,
            "output_cost_per_token": 0.000015,
            "litellm_provider": "anthropic"
        }
    }
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result_update = await PricingSyncService.sync_prices(db_session)
        
    assert result_update["success"] is True
    assert result_update["added"] == 0
    assert result_update["updated"] == 1
    
    updated_mini = db_session.query(ModelPricing).filter_by(model_id="gpt-4o-mini").first()
    assert updated_mini.input_rate_per_1m == pytest.approx(0.20)
    assert PricingSyncService.get_price("gpt-4o-mini") == (pytest.approx(0.20), pytest.approx(0.60))


@pytest.mark.asyncio
async def test_calculate_cost_with_dynamic_pricing(db_session):
    """Verify that calculate_cost() leverages dynamic database rates when available."""
    # Ensure cache and DB have dynamic rate for a custom model
    db_session.execute(text("DELETE FROM model_pricings"))
    db_session.commit()
    
    PricingSyncService._cache.clear()
    
    custom_pricing = ModelPricing(
        model_id="my-super-smart-model",
        provider="CUSTOM",
        input_rate_per_1m=10.0,  # $10.00 per 1M tokens
        output_rate_per_1m=20.0, # $20.00 per 1M tokens
        is_active=True
    )
    db_session.add(custom_pricing)
    db_session.commit()
    
    # Trigger load to cache
    PricingSyncService.load_cache_from_db(db_session)
    
    # Calculate cost (100K prompt, 50K completion)
    cost = calculate_cost(
        model_name="my-super-smart-model",
        provider=ProviderType.CUSTOM,
        prompt_tokens=100_000,
        completion_tokens=50_000
    )
    # Expected cost = (100k / 1M) * 10 + (50k / 1M) * 20 = 1 + 1 = 2.0
    assert cost == pytest.approx(2.0)
    
    # Test case insensitivity lookup
    cost_mixed_casing = calculate_cost(
        model_name="My-Super-Smart-Model",
        provider=ProviderType.CUSTOM,
        prompt_tokens=100_000,
        completion_tokens=50_000
    )
    assert cost_mixed_casing == pytest.approx(2.0)
    
    # Test fallback lookup (not in DB)
    fallback_cost = calculate_cost(
        model_name="gpt-4o-mini",  # hardcoded fallback
        provider=ProviderType.OPENAI,
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000
    )
    assert fallback_cost == pytest.approx(0.15 + 0.60)


@pytest.mark.asyncio
async def test_api_manager_dynamic_cost(db_session):
    """Verify that APIManager dynamically resolves cost_per_1k_tokens using pricing database."""
    db_session.execute(text("DELETE FROM model_pricings"))
    db_session.execute(text("DELETE FROM user_model_configs"))
    db_session.commit()
    
    PricingSyncService._cache.clear()
    
    # Create pricing in DB
    custom_pricing = ModelPricing(
        model_id="test-load-balanced-model",
        provider="OPENAI",
        input_rate_per_1m=5.0,  # $5.00 per 1M tokens
        output_rate_per_1m=10.0,
        is_active=True
    )
    db_session.add(custom_pricing)
    
    # Create configuration using this model
    config = UserModelConfig(
        config_name="Test Model Config",
        provider=ProviderType.OPENAI,
        default_model="test-load-balanced-model",
        is_default=True,
        is_active=True,
        status=ConnectionStatus.ACTIVE,
        requests_per_minute=100,
        max_tokens=4000
    )
    db_session.add(config)
    db_session.commit()
    
    PricingSyncService.load_cache_from_db(db_session)
    
    # Initialize APIManager
    manager = APIManager(db_session)
    assert config.id in manager.models
    
    # Verify cost_per_1k_tokens is resolved dynamically: (1000 / 1_000_000) * $5.00 = $0.005
    assert manager.models[config.id].cost_per_1k_tokens == pytest.approx(0.005)


def test_sync_admin_endpoint(client, auth_headers):
    """Verify that admin POST /admin/pricing/sync route successfully triggers synchronization."""
    mock_sync_result = {
        "success": True,
        "added": 15,
        "updated": 2,
        "total_cached": 150
    }
    
    with patch("backend.services.pricing_sync_service.PricingSyncService.sync_prices", return_value=mock_sync_result):
        resp = client.post("/api/v1/admin/pricing/sync", headers=auth_headers)
        
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["added"] == 15
    assert data["updated"] == 2
    assert data["total_cached"] == 150


# ── fetch_model_pricing: live, provider-sourced pricing ──────────────────────

def _make_httpx_ctx(payload):
    """Build a mock `async with httpx.AsyncClient(...) as client` context."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json = lambda: payload
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_fetch_model_pricing_openai_style():
    """OpenAI-compatible (OpenRouter) payload exposes a `pricing` object."""
    payload = {
        "data": [
            {
                "id": "openai/gpt-4o",
                "pricing": {"prompt": "0.000005", "completion": "0.000015"},
            },
            {
                "id": "anthropic/claude-3-5-sonnet",
                "pricing": {"prompt": "0.000003", "completion": "0.000015"},
            },
        ]
    }
    ctx = _make_httpx_ctx(payload)
    with patch("backend.services.model_provider.httpx.AsyncClient", return_value=ctx):
        result = await ModelService.fetch_model_pricing(
            ProviderType.CUSTOM, None, "https://openrouter.ai/api/v1"
        )
    # Strings (per-token USD) -> per-1M USD.
    assert result["openai/gpt-4o"] == (5.0, 15.0)
    assert result["anthropic/claude-3-5-sonnet"] == (3.0, 15.0)


@pytest.mark.asyncio
async def test_fetch_model_pricing_litellm_shape():
    """LiteLLM-style flat cost-per-token fields are also handled."""
    payload = {
        "data": [
            {
                "id": "my-model",
                "input_cost_per_token": 0.00000010,
                "output_cost_per_token": 0.00000030,
            },
        ]
    }
    ctx = _make_httpx_ctx(payload)
    with patch("backend.services.model_provider.httpx.AsyncClient", return_value=ctx):
        result = await ModelService.fetch_model_pricing(
            ProviderType.OPENAI_COMPATIBLE, None, "https://gate.example/v1"
        )
    assert result["my-model"] == (0.10, 0.30)


@pytest.mark.asyncio
async def test_fetch_model_pricing_anthropic_no_pricing():
    """Anthropic /v1/models returns metadata only — no pricing -> all None."""
    payload = {
        "data": [
            {"id": "claude-opus-4-6", "type": "model"},
            {"id": "claude-sonnet-4-5", "type": "model"},
        ]
    }
    ctx = _make_httpx_ctx(payload)
    with patch("backend.services.model_provider.httpx.AsyncClient", return_value=ctx):
        result = await ModelService.fetch_model_pricing(
            ProviderType.ANTHROPIC, "sk-test", None
        )
    # Every model resolves to None (free / unknown -> UI suppresses).
    assert result["claude-opus-4-6"] is None
    assert result["claude-sonnet-4-5"] is None


@pytest.mark.asyncio
async def test_fetch_model_pricing_openai_style_no_pricing_fields():
    """OpenAI-style model with NO pricing fields -> None (suppressed), not a crash."""
    payload = {"data": [{"id": "gpt-4o"}]}
    ctx = _make_httpx_ctx(payload)
    with patch("backend.services.model_provider.httpx.AsyncClient", return_value=ctx):
        result = await ModelService.fetch_model_pricing(
            ProviderType.OPENAI_COMPATIBLE, None, "https://example/v1"
        )
    assert result["gpt-4o"] is None


@pytest.mark.asyncio
async def test_fetch_model_pricing_local_and_native_openai_no_key():
    """Local models and native OpenAI without a key expose no prices -> {}."""
    assert await ModelService.fetch_model_pricing(ProviderType.LOCAL, None, None) == {}
    # No api_key and no base_url -> nothing to fetch.
    assert await ModelService.fetch_model_pricing(ProviderType.OPENAI, None, None) == {}


@pytest.mark.asyncio
async def test_get_config_pricing_paid_and_free(client, db_session):
    """GET /configs/{id}/pricing returns price for paid, null for free."""
    from backend.models.entities.user_config import ConnectionStatus

    db_session.execute(text("DELETE FROM model_pricings"))
    db_session.commit()
    PricingSyncService._cache.clear()

    paid = UserModelConfig(
        config_name="Paid Cfg",
        provider=ProviderType.OPENAI,
        default_model="gpt-4o",
        is_active=True,
        status=ConnectionStatus.ACTIVE,
        requests_per_minute=60,
        max_tokens=4000,
        user_id="sovereign",
    )
    free = UserModelConfig(
        config_name="Free Cfg",
        provider=ProviderType.LOCAL,
        default_model="llama3.2",
        is_active=True,
        status=ConnectionStatus.ACTIVE,
        requests_per_minute=60,
        max_tokens=4000,
        user_id="sovereign",
    )
    db_session.add_all([paid, free])
    db_session.add(ModelPricing(
        model_id="gpt-4o",
        provider="OPENAI",
        input_rate_per_1m=5.0,
        output_rate_per_1m=15.0,
        is_active=True,
    ))
    db_session.commit()
    db_session.refresh(paid)
    db_session.refresh(free)
    PricingSyncService.load_cache_from_db(db_session)

    paid_resp = client.get(f"/api/v1/models/configs/{paid.id}/pricing")
    assert paid_resp.status_code == 200
    paid_data = paid_resp.json()
    assert paid_data["pricing"]["input_rate_per_1m"] == 5.0
    assert paid_data["pricing"]["output_rate_per_1m"] == 15.0

    # Free model has no pricing row -> null (UI suppresses).
    free_resp = client.get(f"/api/v1/models/configs/{free.id}/pricing")
    assert free_resp.status_code == 200
    assert free_resp.json()["pricing"] is None
