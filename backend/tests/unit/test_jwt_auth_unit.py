import pytest
from datetime import timedelta, datetime, timezone
from jose import jwt
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from backend.core.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_user,
    get_current_active_user,
    ALGORITHM,
)
from backend.core.config import settings
from backend.core.exceptions import UnauthorizedError


def test_2_2_1_create_and_verify_valid_access_token():
    """2.2.1 — Access token generation and verification."""
    data = {"sub": "testuser", "user_id": "usr-12345", "is_admin": False}
    token = create_access_token(data)

    payload = verify_token(token)
    assert payload is not None
    assert payload["type"] == "access"
    assert payload["sub"] == "testuser"


def test_2_2_2_token_contains_correct_claims():
    """2.2.2 — Token contains user_id, username/sub, is_admin, and exp claims."""
    data = {
        "sub": "adminuser",
        "username": "adminuser",
        "user_id": "usr-9999",
        "is_admin": True,
        "role": "admin",
    }
    token = create_access_token(data)

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["user_id"] == "usr-9999"
    assert payload["username"] == "adminuser"
    assert payload["sub"] == "adminuser"
    assert payload["is_admin"] is True
    assert "exp" in payload
    assert isinstance(payload["exp"], int)


def test_2_2_3_token_refresh_mechanism():
    """2.2.3 — Token refresh mechanism creates valid refresh tokens."""
    data = {"sub": "refreshuser", "user_id": "usr-refresh", "is_admin": False}
    refresh_token = create_refresh_token(data)

    payload = verify_token(refresh_token)
    assert payload is not None
    assert payload["type"] == "refresh"
    assert payload["sub"] == "refreshuser"
    assert payload["user_id"] == "usr-refresh"

    # Now create a new access token from refresh payload
    new_access_token = create_access_token({
        "sub": payload["sub"],
        "user_id": payload["user_id"],
        "is_admin": payload["is_admin"],
    })
    new_payload = verify_token(new_access_token)
    assert new_payload["type"] == "access"
    assert new_payload["sub"] == "refreshuser"


def test_2_2_4_expired_token_returns_401():
    """2.2.4 — Expired token returns 401 Unauthorized."""
    app = FastAPI()

    @app.get("/protected")
    async def protected_route(current_user=Depends(get_current_active_user)):
        return {"status": "ok", "user": current_user}

    client = TestClient(app)

    # Create an expired token
    expired_token = create_access_token(
        data={"sub": "expireduser", "user_id": "usr-expired"},
        expires_delta=timedelta(seconds=-10)
    )

    response = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert response.status_code == 401
    assert "detail" in response.json() or "error" in response.json()


def test_invalid_token_returns_401():
    """Invalid token returns 401 Unauthorized."""
    app = FastAPI()

    @app.get("/protected")
    async def protected_route(current_user=Depends(get_current_active_user)):
        return {"status": "ok", "user": current_user}

    client = TestClient(app)

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer invalid.jwt.token"}
    )

    assert response.status_code == 401
