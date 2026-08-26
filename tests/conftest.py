# tests/conftest.py
import subprocess
import time
import sys
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

# Add project root to Python path for backend imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

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
    """Wait for all docker-compose.test.yml services to report healthy."""
    # Only check the 4 test services defined in docker-compose.test.yml
    required_services = {"postgres", "redis", "chromadb", "minio"}
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
            # Filter to only required test services
            test_services = [s for s in services if s.get("Service") in required_services]
            if len(test_services) == len(required_services) and all(s.get("Health") == "healthy" for s in test_services):
                return
        time.sleep(2)
    raise TimeoutError("Test services did not become healthy in time")


@pytest.fixture(scope="session")
def db_engine(docker_services):
    """SQLAlchemy engine connected to test postgres."""
    # Use localhost since tests run on host machine, not inside Docker
    engine = create_engine("postgresql://agentium:agentium@localhost:5432/agentium_test")
    yield engine
    # Dispose connection pool at session end to avoid "connection abort" warnings
    engine.dispose()


@pytest.fixture(scope="function")
def cleanup_db(db_engine):
    """Truncate all tables after each test to isolate lifespan side effects."""
    yield
    # Post-test cleanup: delete from tables (faster than TRUNCATE with CASCADE on 74 tables)
    with db_engine.connect() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
        for table in reversed(Base.metadata.sorted_tables):
            try:
                conn.execute(text(f"DELETE FROM {table.name}"))
            except Exception:
                pass  # Ignore errors for tables that don't exist or are empty
        conn.execute(text("SET session_replication_role = 'origin'"))
        conn.commit()


@pytest.fixture(scope="function")
def app(cleanup_db, db_engine, monkeypatch):
    """FastAPI app with test database URL (TESTING mode NOT set by default)."""
    # Override DATABASE_URL for this test
    test_db_url = "postgresql://agentium:agentium@localhost:5432/agentium_test"
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    # Also override other test-specific settings
    monkeypatch.setenv("MINIO_ROOT_USER", "testuser")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "testpassword")
    # Note: TESTING is NOT set by default - tests that need it should set it themselves
    
    # Clear the settings cache so new env vars are picked up
    import backend.core.config as config_module
    config_module.get_settings.cache_clear()
    
    # Re-import to pick up new env vars - must reload database module first since engine is created at import time
    import importlib
    import backend.models.database
    importlib.reload(backend.models.database)
    
    # Replace the engine in the database module with the shared db_engine
    from sqlalchemy.orm import sessionmaker
    
    # Replace the engine in the database module
    import backend.models.database as db_module
    db_module.engine = db_engine
    db_module.SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=db_engine
    )
    
    import backend.main
    importlib.reload(backend.main)
    from backend.main import app as reloaded_app
    
    # Return app without TestClient context - tests will create their own
    yield reloaded_app


@pytest.fixture(scope="function")
def app_testing_mode(cleanup_db, db_engine, monkeypatch):
    """FastAPI app with test database URL AND TESTING mode enabled."""
    test_db_url = "postgresql://agentium:agentium@localhost:5432/agentium_test"
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setenv("MINIO_ROOT_USER", "testuser")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "testpassword")
    monkeypatch.setenv("TESTING", "true")
    
    import backend.core.config as config_module
    config_module.get_settings.cache_clear()
    
    import importlib
    import backend.models.database
    importlib.reload(backend.models.database)
    
    from sqlalchemy.orm import sessionmaker
    
    import backend.models.database as db_module
    db_module.engine = db_engine
    db_module.SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=db_engine
    )
    
    import backend.main
    importlib.reload(backend.main)
    from backend.main import app as reloaded_app
    
    yield reloaded_app