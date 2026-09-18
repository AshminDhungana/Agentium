# backend/tests/unit/services/test_create_reminder.py
"""Regression test: create_reminder must persist a valid one-time ScheduledTask.

The tool previously passed nonexistent model kwargs (``task_type``/``payload``/
``scheduled_for``/plain-string ``status``/manual ``id``), so ScheduledTask.__init__
raised, the except swallowed it, and only a log was written — reminders never
persisted.  This pins the corrected behavior: a run_once + run_at row is written.
"""
import asyncio
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest

from backend.models.database import Base
from backend.models.entities.scheduled_task import ScheduledTask, ScheduledTaskStatus


@pytest.fixture
def db_session():
    """Self-contained in-memory SQLite session (shadows root Postgres-bound fixture)."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _persist(db_session):
    @contextmanager
    def _ctx():
        yield db_session
    return _ctx


def test_create_reminder_persists_valid_one_time_schedule(db_session, monkeypatch):
    import backend.services.workflow_tools as wt

    # Route the tool's get_db_context() to the in-memory test session.
    monkeypatch.setattr("backend.models.database.get_db_context", _persist(db_session))

    result = asyncio.run(wt._create_reminder({"message": "buy milk", "delay_seconds": 300}))
    assert result["created"] is True

    row = db_session.query(ScheduledTask).one()
    assert row.run_once is True
    assert row.run_at is not None
    assert row.cron_expression is None
    assert row.status == ScheduledTaskStatus.ACTIVE
    assert row.next_execution_at is not None  # set so the dispatcher will fire it
    assert result["reminder_id"] == row.agentium_id