# backend/tests/integration/test_scheduled_tasks_end_to_end.py
"""End-to-end verification tests for the §10.4 scheduled-tasks machinery.

These run over a real (migrated) Postgres DB and exercise the full
claim -> build -> state-machine -> advance/COMPLETED path and the real
SCHEDULE-trigger -> task-build path.  Only the broker enqueue step
(`_submit_execution`) and the Redis helpers are stubbed, so no Celery broker or
Redis round-trip is made; the live beat-tick + worker run is the manual smoke
step at the end of the plan.
"""
import json
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


def test_cron_fire_dispatches_once_and_advances(seeded_db, monkeypatch):
    from backend.models.entities.scheduled_task import (
        ScheduledTask, ScheduledTaskExecution, ScheduledTaskStatus,
    )
    from backend.services.tasks import scheduled_task_dispatcher as d

    monkeypatch.setattr(d, "_submit_execution", lambda task_id, agent_id: None)

    rec = ScheduledTask(
        name="Cron Fire", cron_expression="0 9 * * *", run_once=False,
        task_payload=json.dumps({"action_type": "execution", "params": {}}),
        owner_agentium_id="00001",
    )
    rec.next_execution_at = datetime(2020, 1, 1)  # force due
    seeded_db.add(rec)
    seeded_db.commit()

    out = d._sweep(seeded_db)
    assert out["dispatched"] == 1

    seeded_db.refresh(rec)
    assert rec.status == ScheduledTaskStatus.ACTIVE
    assert rec.next_execution_at is not None and rec.next_execution_at.year >= 2026

    execs = seeded_db.query(ScheduledTaskExecution).filter_by(scheduled_task_id=rec.id).all()
    assert len(execs) == 1 and execs[0].status.value == "success"


def test_one_time_fires_once_to_completed_and_not_again(seeded_db, monkeypatch):
    from backend.models.entities.scheduled_task import (
        ScheduledTask, ScheduledTaskStatus,
    )
    from backend.services.tasks import scheduled_task_dispatcher as d

    monkeypatch.setattr(d, "_submit_execution", lambda task_id, agent_id: None)

    rec = ScheduledTask(
        name="One Shot", cron_expression=None, run_once=True,
        run_at=datetime(2020, 1, 1),
        task_payload=json.dumps({"action_type": "execution", "params": {}}),
        owner_agentium_id="00001",
    )
    seeded_db.add(rec)
    seeded_db.commit()

    assert d._sweep(seeded_db)["dispatched"] == 1
    seeded_db.refresh(rec)
    assert rec.status == ScheduledTaskStatus.COMPLETED

    # Retained done-record is NEVER re-dispatched.
    assert d._sweep(seeded_db)["dispatched"] == 0
    assert rec.status == ScheduledTaskStatus.COMPLETED


def test_schedule_trigger_dispatches_a_real_task(seeded_db, monkeypatch):
    import backend.services.event_processor as ep
    from backend.models.entities.event_trigger import EventTrigger, TriggerType
    from backend.models.entities.task import Task, TaskStatus
    from backend.services.tasks import scheduled_task_dispatcher as d

    monkeypatch.setattr(d, "_submit_execution", lambda task_id, agent_id: None)
    monkeypatch.setattr(ep, "_check_rate_limit", lambda t, db: False)
    monkeypatch.setattr(ep, "_is_trigger_paused", lambda t: False)

    trg = EventTrigger(
        name="Tick", trigger_type=TriggerType.SCHEDULE,
        config={
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "cooldown_seconds": 60,
            "task_payload": {"action_type": "execution", "title": "tick task",
                             "description": "scheduled tick"},
        },
        last_fired_at=datetime(2020, 1, 1),
        max_fires_per_minute=1000,
    )
    seeded_db.add(trg)
    seeded_db.commit()

    r = ep.EventProcessorService.evaluate_schedule_triggers(seeded_db)
    assert r["fired"] == 1
    t = seeded_db.query(Task).filter_by(title="tick task").first()
    assert t is not None
    assert t.status in (TaskStatus.APPROVED, TaskStatus.IN_PROGRESS)