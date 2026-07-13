"""Smoke tests for the async HTTP client fixture."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_async_health_check(async_client):
    """Verify the async client can hit the health endpoint."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_mobile_voice_degradation_message(async_client, auth_headers):
    """Task 15: synchronous provider exhaustion must return a friendly 503,
    never a stack trace / raw exception string."""
    from backend.services.agent_orchestrator import AgentOrchestrator

    mock_orch = MagicMock()
    mock_orch.route_message = AsyncMock(
        side_effect=RuntimeError("exhausted all providers")
    )
    mock_orch.process_intent = AsyncMock(
        side_effect=RuntimeError("exhausted all providers")
    )
    with patch(
        "backend.services.agent_orchestrator.AgentOrchestrator",
        return_value=mock_orch,
    ):
        response = await async_client.post(
            "/api/v1/mobile/voice-command",
            headers=auth_headers,
            json={"transcribed_text": "do the thing", "language": "en"},
        )

    assert response.status_code == 503
    body = response.json()
    assert "temporarily unavailable" in body["error"]
    assert body["code"] == "PROVIDER_EXHAUSTED"

