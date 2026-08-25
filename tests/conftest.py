# tests/conftest.py
import subprocess
import time
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

# Import Base and all models for table metadata
from backend.models.entities import Base


@pytest.fixture(scope="session")
def docker_services():
    """Start postgres, redis, minio, chromadb via docker-compose.test.yml"""
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d"],
        check=True,
        capture_output=True,
    )
    # Wait for healthchecks to pass
    _wait_for_healthchecks()
    yield
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "down", "-v"],
        check=True,
        capture_output=True,
    )


def _wait_for_healthchecks(timeout: int = 60):
    """Wait for all docker-compose services to report healthy."""
    start = time.time()
    while time.time() - start < timeout:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.test.yml", "ps", "--format", "json"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            import json
            services = [json.loads(line) for line in result.stdout.strip().split("\n") if line]
            if all(s.get("Health") == "healthy" for s in services):
                return
        time.sleep(2)
    raise TimeoutError("Services did not become healthy in time")


@pytest.fixture(scope="session")
def db_engine(docker_services):
    """SQLAlchemy engine connected to test postgres."""
    return create_engine("postgresql://agentium:agentium@localhost:5432/agentium_test")


@pytest.fixture(scope="function")
def cleanup_db(db_engine):
    """Truncate all tables after each test to isolate lifespan side effects."""
    yield
    # Post-test cleanup: truncate all tables in reverse FK order
    with db_engine.connect() as conn:
        # Disable FK checks, truncate, re-enable
        conn.execute(text("SET session_replication_role = 'replica'"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))
        conn.commit()


@pytest.fixture(scope="function")
def app(cleanup_db, monkeypatch):
    """FastAPI app with test database URL."""
    # Override DATABASE_URL for this test
    monkeypatch.setenv("DATABASE_URL", "postgresql://agentium:agentium@localhost:5432/agentium_test")
    # Also override other test-specific settings
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("MINIO_ROOT_USER", "testuser")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "testpassword")
    
    # Re-import to pick up new env vars
    import importlib
    import backend.main
    importlib.reload(backend.main)
    from backend.main import app as reloaded_app
    
    # Return app without TestClient context - tests will create their own
    yield reloaded_app