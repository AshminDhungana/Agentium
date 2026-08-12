import pytest
from backend.models.entities.user import User


def test_register_creates_pending_user(client):
    """POST /register creates user with is_pending=True, is_active=False"""
    response = client.post("/api/v1/auth/register", json={
        "username": "newuser123",
        "email": "newuser123@example.com",
        "password": "securepassword123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "user_id" in data
    assert "awaiting admin approval" in data["message"].lower()


def test_register_duplicate_username_returns_400(client):
    """Duplicate username returns 400 with correct error code"""
    # First registration
    client.post("/api/v1/auth/register", json={
        "username": "duptest",
        "email": "dup1@example.com",
        "password": "securepassword123"
    })
    # Second registration with same username
    response = client.post("/api/v1/auth/register", json={
        "username": "duptest",
        "email": "dup2@example.com",
        "password": "securepassword123"
    })
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "USERNAME_OR_EMAIL_ALREADY_REGISTERED"


def test_register_duplicate_email_returns_400(client):
    """Duplicate email returns 400 with correct error code"""
    client.post("/api/v1/auth/register", json={
        "username": "user1",
        "email": "same@example.com",
        "password": "securepassword123"
    })
    response = client.post("/api/v1/auth/register", json={
        "username": "user2",
        "email": "same@example.com",
        "password": "securepassword123"
    })
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "USERNAME_OR_EMAIL_ALREADY_REGISTERED"


def test_register_password_is_hashed(client):
    """Verify stored password is bcrypt hash, not plaintext"""
    client.post("/api/v1/auth/register", json={
        "username": "hashtest",
        "email": "hashtest@example.com",
        "password": "plaintextpassword"
    })

    # Get user from the test database session - use db_session fixture
    db = client.app.dependency_overrides
    # Use the db_session that was passed to the client fixture
    from backend.models.database import get_db
    from backend.main import app
    db_gen = app.dependency_overrides[get_db]()
    db_session = next(db_gen)

    user = db_session.query(User).filter(User.username == "hashtest").first()
    assert user is not None
    # bcrypt hashes start with $2b$ (version identifier)
    assert user.hashed_password.startswith("$2b$")
    # Verify the hash works
    assert User.verify_password("plaintextpassword", user.hashed_password) is True


def test_register_pending_user_cannot_login(client):
    """Pending user (is_pending=True) gets 403 on login"""
    client.post("/api/v1/auth/register", json={
        "username": "pendinglogin",
        "email": "pendinglogin@example.com",
        "password": "securepassword123"
    })
    response = client.post("/api/v1/auth/login", json={
        "username": "pendinglogin",
        "password": "securepassword123"
    })
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == "ACCOUNT_PENDING_APPROVAL_OR_DEACTIVATED"