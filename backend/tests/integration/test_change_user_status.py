import pytest
import uuid
from backend.models.entities.user import User
from backend.models.entities.audit import AuditLog


def _create_active_user(db, is_admin=False) -> User:
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


@pytest.mark.integration
def test_change_user_status_integration(client, seeded_db):
    """Test full activate/deactivate flow with audit log."""
    # Create a test user
    test_user = _create_active_user(seeded_db)
    seeded_db.flush()
    
    # Login as admin (client fixture uses the seeded_db with admin already created)
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
    
    # Verify audit log created (use metadata_json property)
    audit = seeded_db.query(AuditLog).filter(
        AuditLog.action == "user_status_changed"
    ).order_by(AuditLog.created_at.desc()).first()
    assert audit is not None
    # The metadata_json is stored as a JSON string, to_dict() parses it
    audit_dict = audit.to_dict()
    assert audit_dict["metadata"]["new_status"] is False
    assert audit_dict["metadata"]["target_username"] == test_user.username
    
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
    audits = seeded_db.query(AuditLog).filter(
        AuditLog.action == "user_status_changed"
    ).order_by(AuditLog.created_at.desc()).all()
    assert len(audits) >= 2
    audit_dict = audits[0].to_dict()
    assert audit_dict["metadata"]["new_status"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
