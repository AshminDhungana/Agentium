import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.auth import create_access_token


def test_2_5_2_logout_endpoint_clears_session():
    """Verify POST /api/v1/auth/logout succeeds with valid token and returns success status."""
    client = TestClient(app)

    token = create_access_token({
        "sub": "logoutuser",
        "username": "logoutuser",
        "user_id": "usr-logout-123",
        "is_admin": False,
        "role": "user"
    })

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Logged out successfully" in data["message"]


def test_logout_without_token_returns_401():
    """Verify POST /api/v1/auth/logout without Authorization header returns 401 Unauthorized."""
    client = TestClient(app)

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 401
