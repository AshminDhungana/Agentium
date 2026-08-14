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