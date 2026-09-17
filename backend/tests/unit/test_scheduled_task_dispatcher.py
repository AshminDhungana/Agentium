# backend/tests/unit/test_scheduled_task_dispatcher.py
"""Unit tests for the ScheduledTask dispatcher sweep + CAS claim.

These use a self-contained in-memory SQLite DB (mirroring the models
conftest) so they run without a live Postgres broker/worker. The Celery
enqueue is monkeypatched; only the synchronous sweep logic is exercised.
"""
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.database import Base
from backend.models.entities.scheduled_task import ScheduledTask, ScheduledTaskStatus
from backend.models.entities.task import Task, TaskStatus

# Register every model whose table the dispatch path touches so create_all
# builds a complete schema (Task status transitions write TaskEvent rows via
# the `events` relationship, and _audit writes AuditLog rows).
import backend.models.entities.agents  # noqa: F401
import backend.models.entities.audit  # noqa: F401
import backend.models.entities.checkpoint  # noqa: F401
import backend.models.entities.task  # noqa: F401
import backend.models.entities.task_events  # noqa: F401


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def past():
    # A timestamp guaranteed far in the past, so "due" holds without time mocking.
    return datetime(2020, 1, 1, 0, 0)


def _one_time(db, past):
    t = ScheduledTask(
        name="OneShot", cron_expression=None, run_once=True, run_at=past,
        task_payload=json.dumps({"action_type": "execution", "params": {"m": 1}}),
        owner_agentium_id="00001",
    )
    db.add(t)
    db.commit()
    return t


def _cron(db, past):
    t = ScheduledTask(
        name="Daily", cron_expression="0 9 * * *", run_once=False,
        task_payload=json.dumps({"action_type": "execution", "params": {}}),
        owner_agentium_id="00001",
    )
    t.next_execution_at = past  # force due
    db.add(t)
    db.commit()
    return t


def test_one_time_task_dispatches_once_then_completed(db_session, past, monkeypatch):
    from backend.services.tasks import scheduled_task_dispatcher as d

    _one_time(db_session, past)
    dispatched = []
    monkeypatch.setattr(d, "_submit_execution",
                        lambda task_id, agent_id: dispatched.append((task_id, agent_id)))
    monkeypatch.setattr(d, "_allocate_task_id", lambda db: "T90001")

    out = d._sweep(db_session)
    assert out["dispatched"] == 1
    assert len(dispatched) == 1
    # The one-time row is now COMPLETED (retained done-record), never re-fired.
    row = db_session.query(ScheduledTask).one()
    assert row.status == ScheduledTaskStatus.COMPLETED
    # The dispatched Task existed and was routed through the state machine.
    t = db_session.query(Task).filter_by(agentium_id="T90001").one()
    assert t.status == TaskStatus.IN_PROGRESS  # handed off to the executor
    # Second sweep: nothing to do — already COMPLETED.
    assert d._sweep(db_session)["dispatched"] == 0


def test_cron_task_advances_next_execution_at(db_session, past, monkeypatch):
    from backend.services.tasks import scheduled_task_dispatcher as d

    _cron(db_session, past)
    monkeypatch.setattr(d, "_submit_execution", lambda task_id, agent_id: None)
    monkeypatch.setattr(d, "_allocate_task_id", lambda db: "T90002")

    out = d._sweep(db_session)
    assert out["dispatched"] == 1
    row = db_session.query(ScheduledTask).one()
    assert row.status == ScheduledTaskStatus.ACTIVE
    # next_execution_at advanced to the future (strictly after now).
    assert row.next_execution_at is not None and row.next_execution_at.year >= 2026


def test_cas_claim_prevents_double_fire(db_session, past, monkeypatch):
    from backend.services.tasks import scheduled_task_dispatcher as d

    row = _one_time(db_session, past)
    # Simulate a concurrent worker already RUNNING this row.
    row.status = ScheduledTaskStatus.RUNNING
    db_session.commit()
    monkeypatch.setattr(d, "_submit_execution", lambda task_id, agent_id: None)
    monkeypatch.setattr(d, "_allocate_task_id", lambda db: "T90003")
    out = d._sweep(db_session)
    assert out["dispatched"] == 0  # row stayed RUNNING, not double-fired