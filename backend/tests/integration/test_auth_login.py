import pytest
import uuid
from datetime import timedelta
from jose import jwt
from backend.models.entities.user import User
from backend.core.auth import create_access_token, ALGORITHM
from backend.core.config import settings

pytestmark = pytest.mark.integration


def _create_active_user(client, is_admin=False) -> User:
    """Helper to create an active, approved user in the DB."""
    from backend.models.database import get_db
    from backend.main import app

    db_gen = app.dependency_overrides[get_db]()
    db_session = next(db_gen)

    username = f"activeuser_{uuid.uuid4().hex[:6]}"
    user = User.create_user(
        db=db_session,
        username=username,
        email=f"{username}@example.com",
        password="ValidPassword123!",
        is_active=True,
        is_pending=False,
        is_admin=is_admin,
    )
    return user


def test_2_2_1_login_returns_valid_jwt_token(client):
    """2.2.1 — POST /api/v1/auth/login returns valid JWT token"""
    user = _create_active_user(client)

    response = client.post("/api/v1/auth/login", json={
        "username": user.username,
        "password": "ValidPassword123!"
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == user.username


def test_2_2_2_token_contains_correct_claims(client):
    """2.2.2 — Token contains correct claims (user_id, username, is_admin, exp)"""
    user = _create_active_user(client, is_admin=True)

    response = client.post("/api/v1/auth/login", json={
        "username": user.username,
        "password": "ValidPassword123!"
    })

    assert response.status_code == 200
    access_token = response.json()["access_token"]

    payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["user_id"] == user.id
    assert payload["username"] == user.username
    assert payload["sub"] == user.username
    assert payload["is_admin"] is True
    assert "exp" in payload


def test_2_2_3_token_refresh_mechanism_works(client):
    """2.2.3 — Token refresh mechanism works"""
    user = _create_active_user(client)

    # First login to get refresh token
    login_resp = client.post("/api/v1/auth/login", json={
        "username": user.username,
        "password": "ValidPassword123!"
    })
    refresh_token = login_resp.json()["refresh_token"]

    # Call /refresh with refresh_token
    refresh_resp = client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token
    })

    assert refresh_resp.status_code == 200
    refreshed_data = refresh_resp.json()
    assert "access_token" in refreshed_data
    assert "refresh_token" in refreshed_data
    assert refreshed_data["user"]["username"] == user.username


def test_2_2_4_expired_token_returns_401(client):
    """2.2.4 — Expired token returns 401 Unauthorized"""
    expired_token = create_access_token(
        data={"sub": "someuser", "user_id": "fake-id"},
        expires_delta=timedelta(seconds=-10)
    )

    response = client.get(
        "/api/v1/auth/verify-session",
        headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert response.status_code == 401
