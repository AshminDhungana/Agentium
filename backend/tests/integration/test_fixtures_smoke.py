import pytest
from sqlalchemy import text
from backend.models.entities.agents import HeadOfCouncil, CouncilMember
from backend.models.entities.constitution import Constitution
from backend.models.entities.user import User

pytestmark = pytest.mark.integration


def test_db_session(db_session):
    """Verify db_session can execute queries and is empty initially."""
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
    
    # Should not have any agents yet
    agent_count = db_session.query(HeadOfCouncil).count()
    assert agent_count == 0


@pytest.mark.asyncio
async def test_seeded_db(seeded_db):
    """Verify seeded_db contains the genesis data."""
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert head is not None
    assert head.is_active is True
    
    # Genesis creates exactly two council members (10001, 10002).
    # The seeded_db fixture also provisions a separate admin council agent
    # (10003) used by other integration tests, so count the genesis
    # members explicitly rather than every CouncilMember row.
    council_count = (
        seeded_db.query(CouncilMember)
        .filter(CouncilMember.agentium_id.in_(["10001", "10002"]))
        .count()
    )
    assert council_count == 2
    
    constitution = seeded_db.query(Constitution).filter_by(is_active=True).first()
    assert constitution is not None
    
    admin = seeded_db.query(User).filter_by(username="admin").first()
    assert admin is not None


def test_redis_client(redis_client):
    """Verify redis connection works and is flushed."""
    # It should be empty
    keys = redis_client.keys("*")
    assert len(keys) == 0
    
    redis_client.set("test_key", "test_value")
    val = redis_client.get("test_key").decode("utf-8")
    assert val == "test_value"


def test_vector_store(vector_store):
    """Verify vector_store initializes and uses test collections."""
    assert vector_store.client is not None
    # Add a document
    collection = vector_store.get_collection("constitution")
    collection.add(
        ids=["test_doc_1"],
        documents=["This is a test document"],
        metadatas=[{"source": "test"}]
    )
    
    results = collection.get()
    assert len(results["ids"]) == 1
    assert results["ids"][0] == "test_doc_1"


def test_celery_eager(celery_eager):
    """Verify Celery tasks run synchronously."""
    @celery_eager.task
    def add(x, y):
        return x + y
        
    result = add.delay(4, 4)
    assert result.successful()
    assert result.result == 8


@pytest.mark.asyncio
async def test_mock_ai_provider(mock_ai_provider):
    """Verify the mock AI provider intercepts generation."""
    response = await mock_ai_provider.mock_generate(user_message="Hello AI")
    assert response["content"] == "Mock response to: Hello AI..."
    assert mock_ai_provider.call_count == 1
    assert mock_ai_provider.last_call.user_message == "Hello AI"
    
    mock_ai_provider.set_response(content="Custom mock", tokens_used=5)
    response2 = await mock_ai_provider.mock_generate(user_message="Second call")
    assert response2["content"] == "Custom mock"
    assert response2["tokens_used"] == 5
    assert mock_ai_provider.call_count == 2


def test_client_and_auth(client, auth_headers):
    """Verify FastAPI TestClient and auth_headers work."""
    # Unauthenticated health check
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    
    # Authenticated request
    resp2 = client.get("/api/v1/auth/verify-session", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["user"]["username"] == "admin"
