"""
Unit test for TaskEvent.agentium_id generation.

TaskEvent.agentium_id is unique across the entire table (base.py line 24).
It is auto-generated from the wall clock. A task that transitions through
two STATES in rapid succession — e.g. the legal
PENDING -> APPROVED -> IN_PROGRESS path used by the workflow and DAG
dispatch code — emits two STATUS_CHANGED events back-to-back.

Regression: the generator previously used millisecond precision
(E + HHMMSS + 3 ms digits). Two events created within the same
millisecond therefore got identical agentium_id values, violating the
UNIQUE constraint on task_events.agentium_id and rolling back the whole
dispatch transaction.
"""

import pytest

from backend.models.entities.task_events import TaskEvent, TaskEventType


def _make_event() -> TaskEvent:
    # Only construction is exercised; no flush, so missing FK/id values are fine.
    return TaskEvent(
        task_id="00000000-0000-0000-0000-000000000000",
        event_type=TaskEventType.STATUS_CHANGED,
        actor_id="system",
    )


def test_rapid_task_events_get_distinct_agentium_ids():
    """
    Events created back-to-back (the realistic APPROVED->IN_PROGRESS pair
    emitted by set_status during dispatch) must not collide on the
    agentium_id UNIQUE constraint.
    """
    count = 30
    ids = [_make_event().agentium_id for _ in range(count)]

    assert len(ids) == len(set(ids)), (
        f"duplicate TaskEvent.agentium_id generated across {count} rapid "
        f"constructions: {ids}"
    )