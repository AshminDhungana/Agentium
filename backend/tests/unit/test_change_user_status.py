import json
import pytest
import uuid
from backend.models.entities.user import User
from backend.models.entities.audit import AuditLog
from backend.models.database import get_db
from backend.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _create_active_user(db: Session, is_admin=False) -> User:
    """Helper to create an active, approved user in the DB."""
    username = f"testuser_{uuid.uuid4().hex[:6]}"
    user = User.create_user(
        db=db,
        username=username,
        email=f"{username}@example.com",
        password="ValidPassword123!",
        is_active=True,
        is_pending=False,
        is_admin=is_admin,
    )
    return user


@pytest.fixture
def client(db_session):
    """TestClient over the real app with get_db pointed at db_session.

    tests/unit has no shared `client` fixture (only the integration suite's
    conftest defines one), so this file builds its own. No `with` block, so
    the app lifespan never fires; requests still run the middleware stack.
    """
    admin = db_session.query(User).filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@agentium.local",
            hashed_password=User.hash_password("admin"),
            is_admin=True,
            is_active=True,
            is_pending=False,
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)

    def get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = get_test_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_change_user_status_integration(client, db_session):
    """Test full activate/deactivate flow with audit log."""
    from backend.models.entities.user import User

    # Create a test user. The client fixture overrides get_db with db_session,
    # so the API endpoints see the same (uncommitted) rows this test creates.
    test_user = _create_active_user(db_session)
    db_session.flush()
    
    # Login as admin
    login_resp = client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Deactivate user
    resp = client.patch(
        f"/api/v1/admin/users/{test_user.id}/status",
        json={"is_active": False},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["is_active"] is False
    
    # Verify audit log created
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "user_status_changed"
    ).order_by(AuditLog.created_at.desc()).first()
    assert audit is not None
    # AuditLog's JSON column is metadata_json (the `metadata` attribute name
    # is reserved by SQLAlchemy) — other tests read it via json.loads().
    meta = json.loads(audit.metadata_json) if audit.metadata_json else {}
    assert meta["new_status"] is False
    assert meta["target_username"] == test_user.username
    
    # Reactivate user
    resp = client.patch(
        f"/api/v1/admin/users/{test_user.id}/status",
        json={"is_active": True},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["is_active"] is True
    
    # Verify second audit log
    audits = db_session.query(AuditLog).filter(
        AuditLog.action == "user_status_changed"
    ).order_by(AuditLog.created_at.desc()).all()
    assert len(audits) >= 2
    meta_first = json.loads(audits[0].metadata_json) if audits[0].metadata_json else {}
    assert meta_first["new_status"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
