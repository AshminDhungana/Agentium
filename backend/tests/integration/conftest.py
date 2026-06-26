"""
Fixture factory for integration tests.
Connects to the running docker-compose stack on localhost.
"""

import os
import json
import logging
import pytest
import pytest_asyncio
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import redis.asyncio as redis
import redis as sync_redis
import httpx
from httpx import ASGITransport

# Set environment variables for the test session
# This ensures that imported modules pick up the test configuration.
# Only set defaults when not already provided — CI (GitHub Actions)
# sets these to localhost because tests run on the runner host, not
# inside the Docker network where "postgres"/"redis"/"chromadb" resolve.
os.environ.setdefault("DATABASE_URL", "postgresql://agentium:agentium@postgres:5432/agentium_test")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/1")
os.environ.setdefault("CHROMA_HOST", "chromadb")
os.environ.setdefault("CHROMA_PORT", "8001")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("TESTING", "true")


from backend.main import app
from backend.models.database import Base, get_db
from backend.core.vector_store import get_vector_store, VectorStore
from backend.services.initialization_service import InitializationService
from backend.celery_app import celery_app
from backend.models.entities.user import User

logger = logging.getLogger(__name__)

# Engine for the test database
# Use the default postgres db just to create the test db if it doesn't exist
TEST_DB_URL = os.environ["DATABASE_URL"]
# Derive the default-db URL from the test-db URL so it works with whatever
# host the env is configured for (localhost in CI, postgres in Docker).
# We connect to the 'postgres' system database (guaranteed to exist) for
# admin operations like CREATE DATABASE, rather than assuming a custom
# 'agentium' database exists in all environments.
DEFAULT_URL = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="session")
def db_engine():
    """Create the test database and all tables, tear down at the end."""
    engine_default = create_engine(DEFAULT_URL, isolation_level="AUTOCOMMIT")
    with engine_default.connect() as conn:
        # Always start with a clean test database to avoid stale data
        # from a previous run whose tear-down failed (e.g. missing
        # named constraints in metadata vs. actual DB).
        conn.execute(text("DROP DATABASE IF EXISTS agentium_test"))
        conn.execute(text("CREATE DATABASE agentium_test ENCODING 'UTF8' TEMPLATE template0"))
    engine_default.dispose()

    # Create all tables in the test database
    engine_test = create_engine(TEST_DB_URL)

    # Import all models to ensure they are registered with Base
    import backend.models.entities

    Base.metadata.create_all(bind=engine_test)

    yield engine_test

    # Best-effort tear down: named constraints created with use_alter=True
    # may have a different name in the DB than in the model (migrations,
    # circular dependencies, etc).  If drop_all fails, we still dispose so a
    # subsequent run can recreate the DB from scratch.
    try:
        Base.metadata.drop_all(bind=engine_test)
    except Exception:
        pass
    finally:
        engine_test.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    connection = db_engine.connect()
    # Begin a non-ORM transaction
    transaction = connection.begin()
    
    # Bind an individual Session to the connection
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    
    yield session
    
    # Rollback everything that happened with the Session above
    session.close()
    transaction.rollback()
    connection.close()


@pytest_asyncio.fixture(scope="function")
async def seeded_db(db_session: Session) -> Session:
    """Provide a database session fully seeded via the genesis protocol."""
    try:
        # Ensure default admin exists
        admin = db_session.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@agentium.local",
                hashed_password=User.hash_password("admin"),
                is_active=True,
                is_pending=False,
                is_admin=True
            )
            db_session.add(admin)
            db_session.flush()

        # Pass db_session directly so all genesis writes (including capability grants)
        # land on the same session identity map that the test will query.
        # Without this, grant_capability() flushes onto a different session's objects
        # and custom_capabilities is never visible to the test's parent query.
        init_service = InitializationService(db=db_session)
        if not init_service.is_system_initialized():
            # Temporarily mock the API key check to allow genesis to proceed in tests
            original_check = init_service._has_any_active_api_key
            init_service._has_any_active_api_key = lambda: True

            try:
                await init_service.run_genesis_protocol(force=True, country_name="TestNation")
            finally:
                init_service._has_any_active_api_key = original_check

        # Flush so all pending writes (agent rows, custom_capabilities, audit logs)
        # are visible within this session before the test begins querying.
        db_session.flush()

        # Ensure there is an Agent with agentium_id="admin" to prevent ForeignKey violations
        # when voting as "admin" via HTTP endpoints.
        from backend.models.entities.agents import Agent, AgentType, AgentStatus
        admin_agent = db_session.query(Agent).filter_by(agentium_id="admin").first()
        if not admin_agent:
            admin_agent = Agent(
                agentium_id="admin",
                name="Admin User Agent",
                agent_type=AgentType.COUNCIL_MEMBER,
                status=AgentStatus.ACTIVE,
            )
            db_session.add(admin_agent)
            db_session.flush()

    except Exception as e:
        # A flush-time failure (e.g. a constraint violation during genesis)
        # leaves the underlying Postgres transaction aborted — every query
        # after that point in this fixture (and in the test body, if the
        # exception were swallowed) would fail with a confusing secondary
        # "current transaction is aborted" error instead of the real one.
        # Roll back explicitly so the original exception is what surfaces.
        db_session.rollback()
        logger.error(f"seeded_db fixture failed: {e}")
        raise

    return db_session


@pytest.fixture(scope="function")
def redis_client():
    """Provide a flushed Redis database for the test."""
    client = sync_redis.Redis.from_url(os.environ["REDIS_URL"])
    client.flushdb()
    
    # Patch the application's redis functions if necessary,
    # though setting the REDIS_URL env var before imports usually suffices.
    yield client
    
    client.flushdb()
    client.close()


@pytest.fixture(scope="function")
def vector_store():
    """Provide a clean ChromaDB instance for testing."""
    # Use the test host/port
    vs = VectorStore(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ["CHROMA_PORT"])
    )

    # Prefix all collection names so test data is fully isolated from production.
    original_names = vs.COLLECTIONS.copy()
    for key in list(vs.COLLECTIONS.keys()):
        vs.COLLECTIONS[key] = f"test_{vs.COLLECTIONS[key]}"

    # Purge any leftover test collections from a previous run BEFORE calling
    # initialize().  The previous order was:
    #
    #   initialize()  → creates collections, caches Collection objects (UUID-A)
    #   delete loop   → removes UUID-A from the server
    #   initialize()  → may not refresh the internal cache; objects still hold
    #                    UUID-A → every subsequent .add()/.query() returns 404
    #
    # Deleting first means initialize() runs exactly once and the cached
    # Collection objects always point at live, valid server UUIDs.
    for coll_name in vs.COLLECTIONS.values():
        try:
            vs.client.delete_collection(name=coll_name)
        except Exception:
            pass

    # Reset client and collection cache so that initialize() runs fully and
    # re-populates _collections with live UUIDs.  Without this reset the
    # early-return guard inside initialize() ("if self._client is not None:
    #   return") would skip re-creation, leaving _collections full of stale
    # UUID references pointing at the collections we just deleted.
    vs._client = None
    vs._collections = {}
    # Single initialize — creates fresh, empty collections with correct UUIDs.
    vs.initialize()

    yield vs

    # Teardown: remove test collections so the next run starts clean.
    for coll_name in vs.COLLECTIONS.values():
        try:
            vs.client.delete_collection(name=coll_name)
        except Exception:
            pass

    # Restore original collection names so production code is unaffected.
    vs.COLLECTIONS.update(original_names)


@pytest.fixture(scope="session")
def celery_eager():
    """Configure Celery to run tasks synchronously in-process."""
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    yield celery_app


class MockCall:
    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.user_message = kwargs.get("user_message", "")
        self.system_prompt = kwargs.get("system_prompt", kwargs.get("system_prompt_override", ""))


class MockAIProvider:
    def __init__(self):
        self.calls = []
        self.default_response = {
            "content": "Mock deterministic response",
            "tokens_used": 100,
            "prompt_tokens": 60,
            "completion_tokens": 40,
            "latency_ms": 15,
            "model": "mock-deterministic-v1",
            "cost_usd": 0.001,
            "finish_reason": "stop",
        }
        self.custom_responses = []

    async def mock_generate(self, *args, **kwargs):
        call = MockCall(kwargs)
        self.calls.append(call)
        
        if self.custom_responses:
            resp = self.custom_responses.pop(0)
            # Merge with default to ensure required fields
            full_resp = self.default_response.copy()
            full_resp.update(resp)
            return full_resp
            
        # Echo back some input for test verification
        resp = self.default_response.copy()
        resp["content"] = f"Mock response to: {call.user_message[:50]}..."
        return resp
        
    @property
    def call_count(self):
        return len(self.calls)
        
    @property
    def last_call(self):
        return self.calls[-1] if self.calls else None
        
    def set_response(self, **kwargs):
        self.custom_responses.append(kwargs)


@pytest.fixture(scope="function")
def mock_ai_provider(monkeypatch):
    """Patch the ModelService to return deterministic mock responses."""
    from backend.services.model_provider import ModelService
    
    mock = MockAIProvider()
    
    # Patch both generation methods used in the codebase
    monkeypatch.setattr(ModelService, "generate_with_agent", mock.mock_generate)
    monkeypatch.setattr(ModelService, "generate_with_agent_tools", mock.mock_generate)
    
    yield mock


@pytest.fixture(scope="function")
def client(db_session, redis_client, vector_store, celery_eager):
    """FastAPI TestClient with dependency overrides."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    # Also patch the global get_vector_store to return our test instance
    import backend.core.vector_store
    original_get_vector_store = backend.core.vector_store.get_vector_store
    backend.core.vector_store.get_vector_store = lambda: vector_store
    
    with TestClient(app) as test_client:
        yield test_client
        
    # Restore override
    backend.core.vector_store.get_vector_store = original_get_vector_store
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session, redis_client, vector_store, celery_eager):
    """Async httpx client with ASGI transport for testing async FastAPI routes."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    import backend.core.vector_store
    original_get_vector_store = backend.core.vector_store.get_vector_store
    backend.core.vector_store.get_vector_store = lambda: vector_store

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    backend.core.vector_store.get_vector_store = original_get_vector_store
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers(client, seeded_db):
    """Return authorization headers for the default admin user."""
    # Login to get JWT token
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 200, f"Login failed: status={response.status_code}, body={response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}