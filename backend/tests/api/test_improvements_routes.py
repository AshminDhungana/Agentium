# backend/tests/api/test_improvements_routes.py
"""
Tests for Continuous Improvement / Autonomous Learning API endpoints.

Covers:
  - GET  /api/v1/improvements/impact        (auth + schema + calculated metrics)
  - GET  /api/v1/improvements/patterns      (auth + vector store patterns)
  - POST /api/v1/improvements/consolidate   (admin auth + 403 non-admin + execution)
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.core.auth import get_current_user
from backend.main import app
from backend.models.database import get_db
from backend.models.entities.critics import CritiqueReview, CriticVerdict


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def mock_db():
    """Mock DB session returning empty review lists or mock reviews."""
    db = MagicMock()
    query_mock = MagicMock()
    filter_mock = MagicMock()
    order_mock = MagicMock()

    db.query.return_value = query_mock
    query_mock.filter.return_value = filter_mock
    query_mock.filter_by.return_value.first.return_value = MagicMock()
    filter_mock.order_by.return_value = order_mock
    filter_mock.count.return_value = 0
    filter_mock.all.return_value = []
    order_mock.all.return_value = []

    return db


@pytest_asyncio.fixture(scope="function")
async def admin_client(mock_db):
    """Authenticated AsyncClient with admin / primary_sovereign role."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "admin-uuid",
        "username": "sovereign",
        "is_admin": True,
        "is_active": True,
        "role": "primary_sovereign",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def nonadmin_client(mock_db):
    """Authenticated AsyncClient with regular observer role (not admin)."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "observer-uuid",
        "username": "observer",
        "is_admin": False,
        "is_active": True,
        "role": "observer",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def unauth_client(mock_db):
    """Unauthenticated AsyncClient without user token."""
    app.dependency_overrides[get_db] = lambda: mock_db
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_learning_impact_authenticated(admin_client):
    """GET /impact returns the expected schema fields for authenticated user."""
    response = await admin_client.get("/api/v1/improvements/impact")
    assert response.status_code == 200
    data = response.json()

    assert "success_rate_delta" in data
    assert "tools_generated" in data
    assert "anti_patterns_warned" in data
    assert "total_reviews_processed" in data
    assert "history" in data
    assert isinstance(data["history"], list)
    assert len(data["history"]) == 7

    for entry in data["history"]:
        assert "date" in entry
        assert "success_rate" in entry


@pytest.mark.asyncio
async def test_get_learning_impact_unauthenticated(unauth_client):
    """GET /impact returns 401 when no auth token is provided."""
    response = await unauth_client.get("/api/v1/improvements/impact")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_patterns_authenticated(admin_client):
    """GET /patterns returns patterns list for authenticated user."""
    with patch("backend.core.vector_store.get_vector_store") as mock_vs:
        mock_coll = MagicMock()
        mock_coll.get.return_value = {
            "ids": ["bp_01", "ap_01"],
            "documents": ["Use indexed DB columns", "Avoid non-paginated queries"],
            "metadatas": [
                {"type": "best_practice", "confidence": 0.95},
                {"type": "anti_pattern", "confidence": 0.85},
            ],
        }
        mock_vs.return_value.get_collection.return_value = mock_coll

        response = await admin_client.get("/api/v1/improvements/patterns")
        assert response.status_code == 200
        data = response.json()

        assert "patterns" in data
        assert len(data["patterns"]) == 2
        assert data["patterns"][0]["id"] == "bp_01"
        assert data["patterns"][0]["type"] == "best_practice"
        assert data["patterns"][0]["confidence"] == 0.95
        assert data["patterns"][1]["id"] == "ap_01"
        assert data["patterns"][1]["type"] == "anti_pattern"


@pytest.mark.asyncio
async def test_get_patterns_unauthenticated(unauth_client):
    """GET /patterns returns 401 when unauthenticated."""
    response = await unauth_client.get("/api/v1/improvements/patterns")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trigger_consolidation_admin(admin_client):
    """POST /consolidate triggers learning consolidation for admin user."""
    with patch("backend.services.autonomous_learning.AutonomousLearningEngine.analyze_outcomes") as mock_analyze:
        mock_analyze.return_value = {
            "processed": 5,
            "best_practices": 2,
            "anti_patterns": 1,
            "stored": 3,
        }

        response = await admin_client.post("/api/v1/improvements/consolidate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"]["processed"] == 5
        assert data["result"]["stored"] == 3


@pytest.mark.asyncio
async def test_trigger_consolidation_forbidden_for_non_admin(nonadmin_client):
    """POST /consolidate returns 403 for non-admin user."""
    response = await nonadmin_client.post("/api/v1/improvements/consolidate")
    assert response.status_code == 403
    data = response.json()
    assert "ADMIN_PERMISSIONS_REQUIRED" in str(data) or "Admin permissions required" in str(data)


@pytest.mark.asyncio
async def test_trigger_consolidation_unauthenticated(unauth_client):
    """POST /consolidate returns 401 when unauthenticated."""
    response = await unauth_client.post("/api/v1/improvements/consolidate")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_learning_impact_with_db_reviews(mock_db, admin_client):
    """GET /impact computes real metrics from database reviews."""
    now = datetime.utcnow()

    # Create 3 pass reviews and 1 reject review
    r1 = MagicMock(spec=CritiqueReview)
    r1.reviewed_at = now - timedelta(days=1)
    r1.created_at = r1.reviewed_at
    r1.verdict = CriticVerdict.PASS

    r2 = MagicMock(spec=CritiqueReview)
    r2.reviewed_at = now - timedelta(days=2)
    r2.created_at = r2.reviewed_at
    r2.verdict = CriticVerdict.PASS

    r3 = MagicMock(spec=CritiqueReview)
    r3.reviewed_at = now - timedelta(days=8)
    r3.created_at = r3.reviewed_at
    r3.verdict = CriticVerdict.REJECT

    # Configure query chain
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [r3, r2, r1]
    mock_db.query.return_value.filter.return_value.count.return_value = 2

    response = await admin_client.get("/api/v1/improvements/impact")
    assert response.status_code == 200
    data = response.json()

    assert data["total_reviews_processed"] >= 2
    # In current 7-day period: 2 passes out of 2 = 100%. Previous 7-day period: 0 passes out of 1 = 0%. Delta = 100.0
    assert data["success_rate_delta"] == 100.0
