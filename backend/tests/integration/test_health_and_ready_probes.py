"""
Tests for Kubernetes Liveness (/healthz) and Readiness (/ready) probes (Phase 21.5.4).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os
from collections import namedtuple

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_healthz_liveness_probe_healthy(async_client):
    """Verify /healthz returns 200 OK immediately with status ok."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_alias_probe_healthy(async_client):
    """Verify /health alias returns 200 OK."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_probe_all_healthy(async_client):
    """Verify /ready returns 200 OK when DB, Redis, and disk are healthy."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    Usage = namedtuple("Usage", ["total", "used", "free"])
    mock_usage = Usage(total=100 * 1024 * 1024 * 1024, used=20 * 1024 * 1024 * 1024, free=80 * 1024 * 1024 * 1024)

    with patch("backend.models.database.check_health", return_value={"status": "healthy", "database": "connected"}), \
         patch("backend.core.redis.get_redis_client", return_value=mock_redis), \
         patch("shutil.disk_usage", return_value=mock_usage):

        response = await async_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"]["status"] == "healthy"
        assert data["checks"]["redis"]["status"] == "healthy"
        assert data["checks"]["disk"]["status"] == "healthy"
        assert data["checks"]["disk"]["free_mb"] > 500.0


@pytest.mark.asyncio
async def test_readyz_alias(async_client):
    """Verify /readyz alias returns same readiness structure."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    Usage = namedtuple("Usage", ["total", "used", "free"])
    mock_usage = Usage(total=100 * 1024 * 1024 * 1024, used=20 * 1024 * 1024 * 1024, free=80 * 1024 * 1024 * 1024)

    with patch("backend.models.database.check_health", return_value={"status": "healthy", "database": "connected"}), \
         patch("backend.core.redis.get_redis_client", return_value=mock_redis), \
         patch("shutil.disk_usage", return_value=mock_usage):

        response = await async_client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_ready_probe_database_failure(async_client):
    """Verify /ready returns 503 Service Unavailable when DB is down."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    with patch("backend.main.check_health", return_value={"status": "unhealthy", "error": "connection refused"}), \
         patch("backend.core.redis.get_redis_client", return_value=mock_redis):

        response = await async_client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_ready_probe_redis_failure(async_client):
    """Verify /ready returns 503 Service Unavailable when Redis is unreachable."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("Redis connection refused"))
    mock_redis.aclose = AsyncMock()

    with patch("backend.models.database.check_health", return_value={"status": "healthy", "database": "connected"}), \
         patch("backend.core.redis.get_redis_client", return_value=mock_redis):

        response = await async_client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["redis"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_ready_probe_disk_space_failure(async_client):
    """Verify /ready returns 503 when free disk space is below 500 MB threshold."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    Usage = namedtuple("Usage", ["total", "used", "free"])
    # 200 MB free (below 500 MB threshold)
    mock_usage = Usage(total=100 * 1024 * 1024 * 1024, used=99 * 1024 * 1024 * 1024, free=200 * 1024 * 1024)

    with patch("backend.models.database.check_health", return_value={"status": "healthy", "database": "connected"}), \
         patch("backend.core.redis.get_redis_client", return_value=mock_redis), \
         patch("shutil.disk_usage", return_value=mock_usage):

        response = await async_client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["disk"]["status"] == "unhealthy"
        assert data["checks"]["disk"]["free_mb"] < 500.0


@pytest.mark.asyncio
async def test_liveness_probe_still_200_when_deps_down(async_client):
    """Verify /healthz stays 200 OK even when DB and Redis are completely down (liveness decoupling)."""
    with patch("backend.models.database.check_health", return_value={"status": "unhealthy", "error": "DB crash"}), \
         patch("backend.core.redis.get_redis_client", side_effect=Exception("Redis down")):

        response = await async_client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
