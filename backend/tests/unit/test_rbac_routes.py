"""
Unit tests for RBAC API routes and permission enforcement.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from backend.api.routes import rbac as rbac_routes
from backend.api.dependencies.require_rbac import require_permission, require_admin_or_sovereign
from backend.models.entities.user import User, ROLE_PRIMARY_SOVEREIGN, ROLE_OBSERVER
from backend.core.auth import create_access_token
from backend.models.database import get_db


@pytest.fixture
def rbac_app():
    app = FastAPI()
    app.include_router(rbac_routes.router, prefix="/api/v1")

    @app.get("/api/v1/protected-feature")
    def protected_feature(user=Depends(require_permission("configure_agents"))):
        return {"status": "ok", "user": user.username}

    @app.get("/api/v1/admin-feature")
    def admin_feature(user=Depends(require_admin_or_sovereign)):
        return {"status": "ok", "user": user.username}

    return app


def test_2_4_1_list_and_assign_roles(rbac_app):
    """2.4.1 — GET/POST /api/v1/rbac/roles CRUD works."""
    admin_user = User(
        id="usr-admin",
        username="admin",
        email="admin@test.com",
        is_admin=True,
        is_active=True,
        role=ROLE_PRIMARY_SOVEREIGN,
    )
    admin_user.delegations_received = []

    target_user = User(
        id="usr-target",
        username="target",
        email="target@test.com",
        is_admin=False,
        is_active=True,
        role=ROLE_OBSERVER,
    )
    target_user.delegations_received = []

    admin_token = create_access_token({"sub": "admin", "user_id": "usr-admin", "is_admin": True})

    def mock_get_db():
        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = admin_user
        query_mock.filter.return_value = filter_mock
        query_mock.all.return_value = [admin_user, target_user]
        db.query.return_value = query_mock
        yield db

    rbac_app.dependency_overrides[get_db] = mock_get_db
    client = TestClient(rbac_app)

    # 1. GET /api/v1/rbac/roles
    res_get = client.get(
        "/api/v1/rbac/roles",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_get.status_code == 200
    data = res_get.json()
    assert len(data) == 2
    assert "effective_role" in data[0]

    # 2. POST /api/v1/rbac/roles
    with patch("backend.services.rbac_service.RBACService.assign_role") as mock_assign:
        mock_assign.return_value = target_user
        res_post = client.post(
            "/api/v1/rbac/roles",
            json={"user_id": "usr-target", "role": "deputy_sovereign"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_post.status_code == 200
        mock_assign.assert_called_once()


def test_2_4_4_admin_only_routes_reject_non_admin(rbac_app):
    """2.4.4 — Admin-only routes reject non-admin users."""
    normal_user = User(
        id="usr-normal",
        username="normal",
        email="normal@test.com",
        is_admin=False,
        is_active=True,
        role=ROLE_OBSERVER,
    )
    normal_user.delegations_received = []

    normal_token = create_access_token({"sub": "normal", "user_id": "usr-normal", "is_admin": False})

    def mock_get_db():
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = normal_user
        yield db

    rbac_app.dependency_overrides[get_db] = mock_get_db
    client = TestClient(rbac_app)

    # Calling /rbac/roles as non-admin -> 403
    res = client.get(
        "/api/v1/rbac/roles",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert res.status_code == 403

    # Calling require_admin_or_sovereign route as non-admin -> 403
    res_admin_feat = client.get(
        "/api/v1/admin-feature",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert res_admin_feat.status_code == 403


def test_2_4_2_capability_enforced_on_protected_endpoints(rbac_app):
    """2.4.2 — Permission checking via require_permission dependency."""
    normal_user = User(
        id="usr-normal",
        username="normal",
        email="normal@test.com",
        is_admin=False,
        is_active=True,
        role=ROLE_OBSERVER,
    )
    normal_user.delegations_received = []

    normal_token = create_access_token({"sub": "normal", "user_id": "usr-normal", "is_admin": False})

    def mock_get_db():
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = normal_user
        yield db

    rbac_app.dependency_overrides[get_db] = mock_get_db
    client = TestClient(rbac_app)

    # Observer does not have configure_agents -> 403
    res = client.get(
        "/api/v1/protected-feature",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert res.status_code == 403
