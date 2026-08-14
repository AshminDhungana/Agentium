import time
import pytest
from datetime import timedelta
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from backend.core.security_middleware import SessionLimitMiddleware, clear_user_session
from backend.core.auth import create_access_token, get_current_active_user


def test_session_limit_enforced_for_multiple_sessions():
    """Verify SessionLimitMiddleware enforces max_sessions limit and returns 429 SESSION_LIMIT_EXCEEDED."""
    app = FastAPI()

    @app.get("/api/v1/protected")
    async def protected_route(current_user=Depends(get_current_active_user)):
        return {"status": "ok", "user": current_user.get("username")}

    app.add_middleware(SessionLimitMiddleware, max_sessions=2, enforce_in_testing=True)

    client = TestClient(app)

    token1 = create_access_token({"sub": "user1", "user_id": "usr-100", "is_admin": False, "jti": "session-1"})
    token2 = create_access_token({"sub": "user1", "user_id": "usr-100", "is_admin": False, "jti": "session-2"})
    token3 = create_access_token({"sub": "user1", "user_id": "usr-100", "is_admin": False, "jti": "session-3"})

    # Session 1 & 2 succeed
    res1 = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token1}"})
    assert res1.status_code == 200

    res2 = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token2}"})
    assert res2.status_code == 200

    # Session 3 exceeds max_sessions (limit: 2) -> 429 SESSION_LIMIT_EXCEEDED
    res3 = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token3}"})
    assert res3.status_code == 429
    json_data = res3.json()
    assert "SESSION_LIMIT_EXCEEDED" in json_data.get("code", "") or "SESSION_LIMIT_EXCEEDED" in str(json_data)


def test_session_limit_auto_purges_expired_sessions():
    """Verify expired sessions are automatically purged when evaluating session limit."""
    app = FastAPI()

    @app.get("/api/v1/protected")
    async def protected_route(current_user=Depends(get_current_active_user)):
        return {"status": "ok", "user": current_user.get("username")}

    app.add_middleware(SessionLimitMiddleware, max_sessions=1, enforce_in_testing=True)
    client = TestClient(app)

    # Token 1 is expired (expires -10 seconds ago)
    expired_token = create_access_token(
        {"sub": "user2", "user_id": "usr-200", "is_admin": False},
        expires_delta=timedelta(seconds=-10),
    )
    # Token 2 is valid
    valid_token = create_access_token(
        {"sub": "user2", "user_id": "usr-200", "is_admin": False},
        expires_delta=timedelta(minutes=30),
    )

    # Attempt with expired token
    client.get("/api/v1/protected", headers={"Authorization": f"Bearer {expired_token}"})

    # Valid token request should succeed as expired token is purged
    res = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {valid_token}"})
    assert res.status_code == 200


def test_clear_user_session_frees_session_slot():
    """Verify clear_user_session removes token session allowing new login within max limit."""
    app = FastAPI()

    @app.get("/api/v1/protected")
    async def protected_route(current_user=Depends(get_current_active_user)):
        return {"status": "ok", "user": current_user.get("username")}

    app.add_middleware(SessionLimitMiddleware, max_sessions=1, enforce_in_testing=True)
    client = TestClient(app)

    token1 = create_access_token({"sub": "user3", "user_id": "usr-300", "is_admin": False, "jti": "s1"})
    token2 = create_access_token({"sub": "user3", "user_id": "usr-300", "is_admin": False, "jti": "s2"})

    # 1st session succeeds
    res1 = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token1}"})
    assert res1.status_code == 200

    # 2nd session blocked (limit = 1)
    res2 = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token2}"})
    assert res2.status_code == 429

    # Clear 1st session via helper
    clear_user_session("usr-300", token1)

    # 2nd session now succeeds
    res2_retry = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token2}"})
    assert res2_retry.status_code == 200
