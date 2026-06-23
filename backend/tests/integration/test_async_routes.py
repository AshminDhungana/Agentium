"""Smoke tests for the async HTTP client fixture."""
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_async_health_check(async_client):
    """Verify the async client can hit the health endpoint."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
