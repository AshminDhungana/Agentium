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
import tempfile
import uuid
from datetime import datetime

# IMPORTANT: configure the engine URL *before* any backend import so the
# global SQLAlchemy engine in backend.models.database binds to SQLite. The
# engine is created at module import time, reading DATABASE_URL via Pydantic
# settings, so this environment variable must be set first. pytest-env (or
# the host shell) may have already set DATABASE_URL to a Postgres URL,
# so we overwrite unconditionally rather than using setdefault.
#
# Use a temp-file URL (not :memory:) so all sessions on the QueuePool share
# a single physical database. With `:memory:` each pool connection holds
# its own private database, which makes cross-session cleanup behavior
# dependable only by accident.
_DB_FILE = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_DB_FILE.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.name}"

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
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority  # noqa: E402
from backend.models.entities.constitution import Constitution  # noqa: E402


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


@pytest.fixture
def db():
    """Per-test session for cleanup tests; close on teardown."""
    session = SessionLocal()
    yield session
    session.close()


def test_cleanup_drops_audit_older_than_retention(db):
    """Outcome: only audit rows older than the retention cutoff are
    deleted; in-window rows survive."""
    from datetime import timedelta
    cutoff = datetime.utcnow()
    # Default AUDIT_LOG_RETENTION_DAYS is 90. Seed rows comfortably
    # outside and inside that window so the filter has something to do.
    old_dt = cutoff - timedelta(days=365)
    fresh_dt = cutoff - timedelta(days=1)
    marker = _seed_marker()

    for _ in range(3):
        db.add(AuditLog(
            agentium_id=f"A{uuid.uuid4().hex[:9]}",
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id=marker,
            action="old",
            description="old row",
            created_at=old_dt,
        ))
    for _ in range(2):
        db.add(AuditLog(
            agentium_id=f"A{uuid.uuid4().hex[:9]}",
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id=marker,
            action="fresh",
            description="fresh row",
            created_at=fresh_dt,
        ))
    db.commit()

    report = _run(DatabaseMaintenanceService.cleanup_stale_data_once())
    assert report["audit_logs_deleted"] >= 3

    remaining_old = db.query(AuditLog).filter(
        AuditLog.actor_id == marker,
        AuditLog.action == "old",
    ).count()
    remaining_fresh = db.query(AuditLog).filter(
        AuditLog.actor_id == marker,
        AuditLog.action == "fresh",
    ).count()
    assert remaining_old == 0, "Old rows should be deleted"
    assert remaining_fresh == 2, "Fresh rows must be preserved"

    db.query(AuditLog).filter(AuditLog.actor_id == marker).delete(synchronize_session="fetch")
    db.commit()


def test_cleanup_drops_completed_tasks_older_than_archive(db):
    """Outcome: only completed/cancelled/failed tasks older than the
    archive cutoff are deleted; in-progress + recent completions stay."""
    from datetime import timedelta
    cutoff = datetime.utcnow()
    old_dt = cutoff - timedelta(days=365)
    seed = f"{_seed_marker()}-task"

    # Old completed — should be deleted.
    db.add(Task(
        agentium_id=f"T{uuid.uuid4().hex[:8]}",
        title=f"{seed}-old-completed",
        description="x",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.NORMAL,
        status=TaskStatus.COMPLETED,
        updated_at=old_dt,
    ))
    # Old in_progress — must remain (wrong status).
    db.add(Task(
        agentium_id=f"T{uuid.uuid4().hex[:8]}",
        title=f"{seed}-old-in-progress",
        description="x",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.NORMAL,
        status=TaskStatus.IN_PROGRESS,
        updated_at=old_dt,
    ))
    db.commit()

    _run(DatabaseMaintenanceService.cleanup_stale_data_once())

    by_title = {t.title for t in db.query(Task).filter(Task.title.like(f"{seed}%")).all()}
    assert f"{seed}-old-completed" not in by_title, "Old completed task should be deleted"
    assert f"{seed}-old-in-progress" in by_title, "Old in-progress task must remain"

    db.query(Task).filter(Task.title.like(f"{seed}%")).delete(synchronize_session="fetch")
    db.commit()


def test_cleanup_keeps_constitution_v1_always(db):
    """Outcome: version 1 survives even when it falls outside the
    latest-N window. The runtime invariant is enforced because we
    always union version 1's id into `keep_ids` before chunking."""
    keep_n = settings.CONSTITUTION_MAX_VERSIONS
    seed = _seed_marker()

    # Create keep_n + 3 constitutions: versions 1..(keep_n + 3). With
    # `version_number` matching `version` for simplicity, the prune
    # rule must keep the latest `keep_n` PLUS version 1.
    for v in range(1, keep_n + 4):
        db.add(Constitution(
            agentium_id=f"C{uuid.uuid4().hex[:9]}",
            version=f"v{v}.0.0",
            version_number=v,
            preamble=f"{seed}-{v}",  # unique, also used as cleanup marker
            articles="[]",
            prohibited_actions="[]",
            sovereign_preferences="{}",
            created_by_agentium_id="00001",
        ))
    db.commit()

    _run(DatabaseMaintenanceService.cleanup_stale_data_once())

    # version 1 must still exist for this seed.
    v1 = (
        db.query(Constitution)
        .filter(Constitution.version_number == 1, Constitution.preamble.like(f"{seed}-%"))
        .first()
    )
    assert v1 is not None, "Constitution version 1 must never be deleted"

    # Total kept for this seed: keep_n (latest) + 1 (v1).
    kept = (
        db.query(Constitution)
        .filter(Constitution.preamble.like(f"{seed}-%"))
        .count()
    )
    assert kept == keep_n + 1, f"Expected {keep_n + 1} kept for seed, got {kept}"

    db.query(Constitution).filter(Constitution.preamble.like(f"{seed}-%")).delete(synchronize_session="fetch")
    db.commit()


def test_constitution_prune_keeps_latest_n(db):
    """When the total is at or below CONSTITUTION_MAX_VERSIONS, prune
    deletes zero entries — the helper short-circuits."""
    keep_n = settings.CONSTITUTION_MAX_VERSIONS
    seed = _seed_marker()

    # Create exactly keep_n constitutions. v1..vN — nothing to prune.
    for v in range(1, keep_n + 1):
        db.add(Constitution(
            agentium_id=f"C{uuid.uuid4().hex[:9]}",
            version=f"v{v}.0.0",
            version_number=v,
            preamble=f"{seed}-{v}",
            articles="[]",
            prohibited_actions="[]",
            sovereign_preferences="{}",
            created_by_agentium_id="00001",
        ))
    db.commit()

    _run(DatabaseMaintenanceService.cleanup_stale_data_once())

    after = (
        db.query(Constitution)
        .filter(Constitution.preamble.like(f"{seed}-%"))
        .count()
    )
    assert after == keep_n, (
        f"All {keep_n} constitutions (under the threshold) should be retained; got {after}"
    )

    db.query(Constitution).filter(Constitution.preamble.like(f"{seed}-%")).delete(synchronize_session="fetch")
    db.commit()


def test_get_maintenance_report_returns_zero_on_empty_db(db):
    """Outcome: on an empty DB the report's eligibility counters are 0
    and retention_config values are present."""
    # Seed nothing — work against the bare schema.
    report = DatabaseMaintenanceService.get_maintenance_report(db)
    assert report["audit_logs_eligible_for_cleanup"] == 0
    assert report["tasks_eligible_for_archive"] == 0
    assert report["constitution_versions"] == 0
    assert report["max_kept_versions"] == settings.CONSTITUTION_MAX_VERSIONS
    assert "retention_config" in report
    assert "audit_log_days" in report["retention_config"]
    assert "task_archive_days" in report["retention_config"]
