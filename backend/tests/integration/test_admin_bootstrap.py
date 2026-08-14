import pytest
from backend.models.entities.user import User
from backend.main import create_default_admin
from backend.models.database import get_db
from backend.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="function")
def fresh_db(db_session):
    """
    Provide a database session WITHOUT the default admin user.
    The seeded_db fixture creates admin; this fixture ensures admin does NOT exist.
    """
    # Delete any existing admin user from this session
    admin = db_session.query(User).filter(User.username == "admin").first()
    if admin:
        db_session.delete(admin)
        db_session.flush()
    yield db_session


def test_create_default_admin_creates_user(fresh_db):
    """2.3.1 — create_default_admin() creates admin user on first boot."""
    # Call the function directly
    created = create_default_admin(fresh_db)

    # Should return True (admin was created)
    assert created is True

    # Verify admin exists in DB with correct attributes
    admin = fresh_db.query(User).filter(User.username == "admin").first()
    assert admin is not None
    assert admin.username == "admin"
    assert admin.email == "admin@agentium.local"
    assert admin.is_active is True
    assert admin.is_pending is False
    assert admin.is_admin is True
    # Password should be hashed
    assert admin.hashed_password.startswith("$2b$")
    # Verify password works
    assert User.verify_password("admin", admin.hashed_password) is True