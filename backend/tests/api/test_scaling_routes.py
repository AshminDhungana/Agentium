# backend/tests/api/test_scaling_routes.py
"""
Tests for the Scaling Dashboard API endpoints.

Covers:
  - GET  /api/v1/scaling/predictions/load  (auth + predictions)
  - GET  /api/v1/scaling/history           (auth + history)
  - POST /api/v1/scaling/override          (admin auth + spawn/liquidate/invalid)
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.models.database import get_db
from backend.core.auth import get_current_user


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def mock_db():
    """Mock DB session returning empty audit logs or query results."""
    db = MagicMock()
    # Mock query chain for AuditLog and Agent queries
    query_mock = MagicMock()
    filter_mock = MagicMock()
    order_mock = MagicMock()
    limit_mock = MagicMock()

    db.query.return_value = query_mock
    query_mock.filter.return_value = filter_mock
    query_mock.filter_by.return_value.first.return_value = MagicMock()
    filter_mock.order_by.return_value = order_mock
    filter_mock.limit.return_value.all.return_value = [MagicMock()]
    filter_mock.all.return_value = []
    order_mock.limit.return_value = limit_mock
    limit_mock.all.return_value = []

    return db


@pytest_asyncio.fixture(scope="function")
async def admin_client(mock_db):
    """Authenticated AsyncClient with admin role dependency override."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "admin-uuid",
        "username": "admin",
        "is_admin": True,
        "is_active": True,
        "role": "admin",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def nonadmin_client(mock_db):
    """Authenticated AsyncClient with non-admin role (is_admin=False)."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "viewer-uuid",
        "username": "viewer",
        "is_admin": False,
        "is_active": True,
        "role": "user",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def unauth_client(mock_db):
    """Unauthenticated AsyncClient — no dependency override for auth, no token."""
    app.dependency_overrides[get_db] = lambda: mock_db
    # Do not override get_current_user so real auth fails (401)
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── Mock predictions ───────────────────────────────────────────────────────────

MOCK_PREDICTIONS = {
    "next_1h": 5.4,
    "next_6h": 7.2,
    "next_24h": 4.1,
    "current_capacity": 3,
    "recommendation": "neutral",
    "token_spend": 2.75,
    "budget_limit": 10.0,
}


# ── GET /scaling/predictions/load ──────────────────────────────────────────────

class TestGetLoadPredictions:
    """Tests for the load predictions endpoint."""

    @pytest.mark.asyncio
    async def test_returns_200_with_prediction_fields(self, admin_client):
        """Authenticated request returns prediction data."""
        with patch(
            "backend.api.routes.scaling.predictive_scaling_service"
        ) as mock_svc:
            mock_svc.get_predictions.return_value = MOCK_PREDICTIONS
            resp = await admin_client.get("/api/v1/scaling/predictions/load")

        assert resp.status_code == 200
        data = resp.json()
        assert data["next_1h"] == 5.4
        assert data["current_capacity"] == 3
        assert data["recommendation"] == "neutral"
        assert data["token_spend"] == 2.75
        assert data["budget_limit"] == 10.0

    @pytest.mark.asyncio
    async def test_returns_401_without_auth(self, unauth_client):
        """Unauthenticated request is rejected."""
        resp = await unauth_client.get("/api/v1/scaling/predictions/load")
        assert resp.status_code == 401


# ── GET /scaling/history ───────────────────────────────────────────────────────

class TestGetScalingHistory:
    """Tests for the scaling history endpoint."""

    @pytest.mark.asyncio
    async def test_returns_200_with_history_array(self, admin_client):
        """Authenticated request returns history list."""
        resp = await admin_client.get("/api/v1/scaling/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    @pytest.mark.asyncio
    async def test_returns_401_without_auth(self, unauth_client):
        """Unauthenticated request is rejected."""
        resp = await unauth_client.get("/api/v1/scaling/history")
        assert resp.status_code == 401


# ── POST /scaling/override ─────────────────────────────────────────────────────

class TestManualScalingOverride:
    """Tests for the manual scaling override endpoint."""

    @pytest.mark.asyncio
    async def test_spawn_returns_200_for_admin(self, admin_client):
        """Admin can spawn agents via override."""
        with patch(
            "backend.api.routes.scaling.ReincarnationService"
        ) as mock_reincarnation:
            mock_reincarnation.spawn_task_agent.return_value = MagicMock()
            resp = await admin_client.post("/api/v1/scaling/override", json={
                "action": "spawn",
                "count": 1,
                "tier": 3,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "spawned" in data

    @pytest.mark.asyncio
    async def test_liquidate_returns_200_for_admin(self, admin_client):
        """Admin can liquidate agents via override."""
        resp = await admin_client.post("/api/v1/scaling/override", json={
            "action": "liquidate",
            "count": 1,
            "tier": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "liquidated" in data

    @pytest.mark.asyncio
    async def test_returns_403_for_nonadmin(self, nonadmin_client):
        """Non-admin user is forbidden from overrides."""
        resp = await nonadmin_client.post("/api/v1/scaling/override", json={
            "action": "spawn",
            "count": 1,
            "tier": 3,
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_action(self, admin_client):
        """Invalid action string returns 400."""
        resp = await admin_client.post("/api/v1/scaling/override", json={
            "action": "invalid_action",
            "count": 1,
            "tier": 3,
        })
        assert resp.status_code == 400
