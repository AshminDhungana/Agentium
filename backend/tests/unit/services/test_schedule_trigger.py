# backend/tests/unit/services/test_schedule_trigger.py
"""Unit tests for the EventTrigger SCHEDULE evaluator.

These use a self-contained in-memory SQLite DB so they run without a live
Postgres broker/worker. The Celery enqueue path (_dispatch_action) is
monkeypatched; only the synchronous evaluate_schedule_triggers sweep logic is
exercised. Redis helpers (_check_rate_limit) and the pause circuit breaker
(_is_trigger_paused) are also stubbed so no external connection is opened.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.database import Base
from backend.models.entities.event_trigger import EventTrigger, TriggerType

# Register the models whose tables the sweep touches so create_all builds a
# complete schema: EventTrigger FKs target_workflow_id -> workflows and
# target_agent_id -> agents, so those tables must exist too.
import backend.models.entities.agents  # noqa: F401
import backend.models.entities.event_trigger  # noqa: F401
import backend.models.entities.workflow  # noqa: F401


@pytest.fixture
def db_session():
    """Self-contained in-memory SQLite session (shadows root conftest)."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_schedule_trigger_fires_once_when_due(db_session, monkeypatch):
    import backend.services.event_processor as ep

    # Pin the EventLog id generator so no second (Postgres) connection is opened
    # when evaluate_schedule_triggers persists the fired EventLog row.
    monkeypatch.setattr(ep.EventLog, "_generate_log_id", lambda self: "EL-TEST-1")

    trigger = EventTrigger(
        agentium_id="ET10001",
        name="EveryMinute",
        trigger_type=TriggerType.SCHEDULE,
        config={"cron_expression": "* * * * *", "timezone": "UTC", "cooldown_seconds": 60},
        last_fired_at=datetime(2020, 1, 1, 0, 0),
        max_fires_per_minute=1000,
    )
    db_session.add(trigger)
    db_session.commit()

    monkeypatch.setattr(ep, "_is_trigger_paused", lambda t: False)
    monkeypatch.setattr(ep, "_check_rate_limit", lambda t, db: False)
    calls = []
    monkeypatch.setattr(
        ep.EventProcessorService, "_dispatch_action",
        staticmethod(lambda t, p, db, dispatch_task_when_no_workflow=False:
                     calls.append({"trigger": t.id, "flag": dispatch_task_when_no_workflow})),
    )

    r1 = ep.EventProcessorService.evaluate_schedule_triggers(db_session)
    assert r1["fired"] == 1
    assert db_session.query(ep.EventLog).filter_by(trigger_id=trigger.id).count() == 1
    assert len(calls) == 1 and calls[0]["flag"] is True

    # Second sweep must NOT re-fire (last_fired_at advanced + cooldown).
    r2 = ep.EventProcessorService.evaluate_schedule_triggers(db_session)
    assert r2["fired"] == 0
    assert db_session.query(ep.EventLog).filter_by(trigger_id=trigger.id).count() == 1


def test_schedule_trigger_skips_when_not_due(db_session, monkeypatch):
    import backend.services.event_processor as ep

    trigger = EventTrigger(
        agentium_id="ET10002",
        name="FarFarFuture",
        trigger_type=TriggerType.SCHEDULE,
        config={"cron_expression": "0 9 * * *", "timezone": "UTC", "cooldown_seconds": 0},
        last_fired_at=datetime(2099, 1, 1),  # future -> deterministically not due
        max_fires_per_minute=1000,
    )
    db_session.add(trigger)
    db_session.commit()

    monkeypatch.setattr(ep, "_is_trigger_paused", lambda t: False)
    monkeypatch.setattr(ep, "_check_rate_limit", lambda t, db: False)

    r = ep.EventProcessorService.evaluate_schedule_triggers(db_session)
    assert r["fired"] == 0
    assert r["skipped"] == 1