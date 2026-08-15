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
def test_admin_cannot_deactivate_self(client, seeded_db):
    """Test that admin cannot deactivate their own account."""
    # Login as admin
    login_resp = client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get admin user ID
    admin_user = seeded_db.query(User).filter(User.username == "admin").first()
    assert admin_user is not None
    
    # Try to deactivate self - should fail
    resp = client.patch(
        f"/api/v1/admin/users/{admin_user.id}/status",
        json={"is_active": False},
        headers=headers
    )
    assert resp.status_code == 400
    data = resp.json()
    print(f"Response data: {data}")
    # Check either detail or error field
    error_msg = data.get("detail") or data.get("error") or str(data)
    assert "Cannot deactivate your own account" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
