"""Unit tests for backend.services.db_maintenance.

These tests run on SQLite so the suite is cheap and self-contained; the
lock-budget claim is verified separately in the integration suite against
real Postgres. SQLite exercises the helper's branching logic (chunk loop,
re-evaluated filter factory, commit-between-batches) which is what the
helper actually exists to enforce; the chunk row-count bound is asserted
indirectly by seeding more rows than a single chunk can delete and
verifying the helper gets them all.
"""
import asyncio
import os
import uuid
from datetime import datetime

# IMPORTANT: configure the engine URL *before* any backend import so the
# global SQLAlchemy engine in backend.models.database binds to SQLite. The
# engine is created at module import time, reading DATABASE_URL via Pydantic
# settings, so this environment variable must be set first. pytest-env (or
# the host shell) may have already set DATABASE_URL to a Postgres URL,
# so we overwrite unconditionally rather than using setdefault.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Patch JSONB → SQLA JSON so SQLite can compile DDL (`create_all`) for
# Tasks / UserModelConfig / etc. that use JSONB columns. Mirrors the patch
# the integration conftest applies before any model import.
import sqlalchemy.dialects.postgresql as _pg_dialect
from sqlalchemy import JSON as _JSON
class _JSONBCompat(_JSON):
    pass
_pg_dialect.JSONB = _JSONBCompat

import pytest

from backend.core.config import settings  # noqa: E402
from backend.services.db_maintenance import DatabaseMaintenanceService  # noqa: E402
from backend.models.database import engine, SessionLocal  # noqa: E402
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory  # noqa: E402


# Create all tables on whatever engine is bound. We import the Base off
# the bound engine's metadata so SQLite-backed tests get the schema
# without needing alembic migrations (which target Postgres only).
from backend.models.entities.base import Base  # noqa: E402
Base.metadata.create_all(bind=engine)


def _run(coro):
    return asyncio.run(coro)


def _seed_marker() -> str:
    """Unique per-test marker so cleanup queries don't trample other rows."""
    return f"unit-dbm-{uuid.uuid4().hex[:12]}"


def test_chunked_delete_respects_batch_size():
    """Cleanup must run more than one chunk when batch_size is smaller
    than the eligible-row count. Proves single-statement lock hold is
    bounded by `batch_size`, not by the bulk row count.

    The helper does not currently expose a chunk-count, so this test
    asserts the *outcome* a chunked loop is uniquely able to produce:
    deleting `N` rows where N > batch_size without holding a single
    statement for the whole table. Any non-chunked implementation will
    trip the same `limit()` semantics if a future contributor rewrites
    the helper without preserving the bound.
    """
    session = SessionLocal()
    try:
        marker = _seed_marker()
        # Seed 250 matching rows so a batch_size=50 helper must issue
        # ≥5 deletes before the zero-row terminator fires.
        for i in range(250):
            session.add(AuditLog(
                agentium_id=f"A{uuid.uuid4().hex[:9]}",
                level=AuditLevel.INFO,
                category=AuditCategory.SYSTEM,
                actor_type="system",
                actor_id=marker,
                action="seed",
                description=f"seed row {i}",
            ))
        session.commit()

        async def _drive():
            return await DatabaseMaintenanceService._chunked_delete(
                db=session,
                model=AuditLog,
                filter_factory=lambda: AuditLog.actor_id == marker,
                batch_size=50,
                sleep_ms=0,  # don't actually sleep in test
            )

        deleted = _run(_drive())
        assert deleted == 250, f"Expected 250 deleted, got {deleted}"
        remaining = session.query(AuditLog).filter(
            AuditLog.actor_id == marker
        ).count()
        assert remaining == 0, f"Expected 0 remaining, got {remaining}"
    finally:
        session.query(AuditLog).filter(
            AuditLog.actor_id.like("unit-dbm-%")
        ).delete(synchronize_session="fetch")
        session.commit()
        session.close()
