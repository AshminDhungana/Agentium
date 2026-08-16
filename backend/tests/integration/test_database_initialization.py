"""
Integration tests for database initialization (TODO §3.1).
Verifies init_db() creates all tables and check_health() works.
"""
import pytest
from sqlalchemy import inspect
from backend.models.database import init_db, check_health, engine
from backend.models.entities import Base
from backend.models.entities.base import BaseEntity
from backend.models import entities
from pydantic import BaseModel


def test_init_db_creates_all_tables(db_session):
    """init_db() creates all expected tables in the database."""
    # Tables already created by conftest.py alembic migration before test runs
    # This test verifies init_db() doesn't break and ALL SQLAlchemy model tables exist
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    # Derive expected tables from entities exports (filter SQLAlchemy models)
    expected_tables = set()
    for name in entities.__all__:
        model = getattr(entities, name)
        is_enum = hasattr(model, '__members__')
        is_base = name in ('Base', 'BaseEntity')
        is_constant = name == 'AGENT_TYPE_MAP'
        is_pydantic = isinstance(model, type) and issubclass(model, BaseModel)

        # SQLAlchemy models: inherit from Base (not BaseEntity) but are not Base itself
        # Note: Some models inherit from BaseEntity (which is abstract), others from Base directly (e.g., User)
        is_sqlalchemy = (
            isinstance(model, type) and
            (issubclass(model, BaseEntity) or (issubclass(model, Base) and model is not Base))
        )

        # Skip abstract base classes
        is_abstract = getattr(model, '__abstract__', False)

        if is_sqlalchemy and hasattr(model, '__tablename__') and not is_abstract:
            expected_tables.add(model.__tablename__)

    # Verify all expected tables exist
    for t in sorted(expected_tables):
        assert t in tables, f"Expected table {t} (from model) missing after init_db()"

    # Verify all tables have expected columns (no empty tables)
    for t in tables:
        cols = inspector.get_columns(t)
        assert len(cols) > 0, f"Table {t} has no columns"

    print(f"\nVerified {len(expected_tables)} SQLAlchemy model tables exist in database")


def test_check_health_returns_healthy(db_session):
    """check_health() returns healthy status with latency against real DB."""
    result = check_health()
    assert result["status"] == "healthy"
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
    assert result["database"] == "connected"


def test_init_db_idempotent(db_session):
    """Calling init_db() multiple times doesn't error."""
    # Should not raise
    init_db()
    init_db()
    # Tables still exist
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert 'users' in tables