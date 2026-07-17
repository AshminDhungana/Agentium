"""
Fixtures for unit tests in backend/tests/unit.

Provides a `db_session` fixture over a live PostgreSQL database so the Ethos
tool's model-backed tests can run. Mirrors the transactional-scope pattern
used by tests/integration/conftest.py (connect, begin a transaction, bind a
Session, roll back on teardown) but is scoped to the unit test directory and
points at the local developer PostgreSQL instance.
"""

import os

os.environ.setdefault("TESTING", "true")
# The working developer PostgreSQL instance (docker-compose default).
# pytest.ini also sets DATABASE_URL; force our value so the engine below
# connects to the correct user/db regardless of ini precedence.
DB_URL = "postgresql://agentium:agentium@localhost:5432/agentium"
os.environ["DATABASE_URL"] = DB_URL

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.models.database import Base


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Provide a transactional-scoped SQLAlchemy session over PostgreSQL."""
    engine = create_engine(DB_URL)
    # Import all models so they are registered on Base.metadata.
    import backend.models.entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
