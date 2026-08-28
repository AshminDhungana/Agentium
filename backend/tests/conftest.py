# tests/conftest.py
import os
os.environ["ENCRYPTION_KEY"] = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.orm import Session
from backend.main import app
from backend.models.database import get_db, engine
from backend.models.entities.user import User
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus
from backend.core.auth import create_access_token
import uuid

@pytest.fixture(scope="function")
def db_session():
    """Function-scoped DB session with rollback."""
    from sqlalchemy.orm import sessionmaker
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest_asyncio.fixture(scope="function")
async def auth_client(db_session):
    """Authenticated AsyncClient with sovereign JWT."""
    # Ensure sovereign user exists
    sovereign = db_session.query(User).filter_by(username="admin").first()
    if not sovereign:
        sovereign = User(
            username="admin",
            email="admin@agentium.local",
            hashed_password=User.hash_password("admin"),
            is_admin=True,
            is_active=True,
            is_pending=False,
        )
        db_session.add(sovereign)
        db_session.commit()
        db_session.refresh(sovereign)
    
    token = create_access_token(data={"sub": str(sovereign.id), "username": "admin", "is_admin": True})
    
    async def get_test_db():
        yield db_session
    
    app.dependency_overrides[get_db] = get_test_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client
    
    app.dependency_overrides.clear()

@pytest.fixture
def model_config_factory(db_session):
    """Factory for creating test model configs."""
    def _create(
        provider: ProviderType = ProviderType.OPENAI,
        config_name: str = None,
        default_model: str = "gpt-4o",
        api_key: str = "sk-test1234567890",
        is_default: bool = False,
        **kwargs,
    ):
        if config_name is None:
            config_name = f"Test {provider.value} {uuid.uuid4().hex[:6]}"
        
        from backend.core.security import encrypt_api_key
        
        config = UserModelConfig(
            user_id="sovereign",
            provider=provider,
            config_name=config_name,
            default_model=default_model,
            api_key_encrypted=encrypt_api_key(api_key) if api_key else None,
            api_key_masked=f"...{api_key[-4:]}" if api_key else None,
            is_default=is_default,
            status=ConnectionStatus.ACTIVE,
            **kwargs,
        )
        db_session.add(config)
        db_session.commit()
        db_session.refresh(config)
        return config
    return _create