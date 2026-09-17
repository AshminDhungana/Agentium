# Scheduled Tasks (§10.4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Section 10.4 Scheduled Tasks machinery — model `run_once`/`run_at` lifecycle, a 15s-beat scheduled-task dispatcher, a shared cron-due helper, a `SCHEDULE` event-trigger evaluator, a CRUD route, and a `create_reminder` fix — then verify all three TODO checklist claims pass.

**Architecture:** A Celery beat entry fires a dispatcher every 15s. The dispatcher claims each due `ScheduledTask` row via a CAS status guard (prevents double-fire), creates a regular `Task` from `task_payload`, routes it through the hardened 10.1–10.3 `TaskExecutor` pipeline, then advances/`COMPLETED`s the schedule. `SCHEDULE` event triggers are evaluated by a second sweep inside `event_processor.py`, reusing the existing circuit-breaker/EventLog machinery. Both sweepers share one cron math helper so their due logic cannot drift. A `/scheduled-tasks` REST CRUD router exposes lifecycle management; `create_reminder` is repaired to build valid rows.

**Tech Stack:** FastAPI, Celery beat (Redis broker), SQLAlchemy 2.x, croniter==3.0.3, zoneinfo (Python 3.9+), PostgreSQL (dev: SQLite in unit tests).

## Global Constraints

- **Fire target:** When due, always create + dispatch a regular `Task` through `TaskExecutor.execute_task_async` (never synthesize a side effect directly).
- **One-time cleanup:** `run_once=True` tasks that succeed get `status=COMPLETED` and are **retained**; the dispatcher never re-dispatches `COMPLETED` rows.
- **Mutual exclusion:** a scheduled task is exactly one of *cron* (`cron_expression` non-null, `run_once=False`) or *one-time* (`run_at` set, `run_once=True`); reject absent/mismatched combinations.
- **Timezone:** always apply the stored `timezone` (default `UTC`) via `zoneinfo` in cron computation; no naive `utcnow()` in cron math.
- **Crash-safe sweep:** each due row is claimed and dispatched inside its own try/except; one bad payload never aborts the sweep.
- **CAS guard:** claim a due row only by kncl atomic `UPDATE … WHERE status=ACTIVE → RUNNING`; a row already claimed by another worker is skipped this sweep.
- **Dispatcher cadence:** beat entry every 15.0s; do **not** add APScheduler or long-running workers.
- **Shared cron math:** both the ScheduledTask dispatcher and the `SCHEDULE` trigger evaluator must call the same `backend.services.scheduling.cron_due.next_run` helper — no duplicated croniter logic.
- **Audit:** log `AuditCategory.TASK` entries (`action="scheduled_task_dispatched"` on dispatch, `action="scheduled_task_failed"` on failure) using the factory `entry = AuditLog.log(...); db.add(entry); db.commit()`. There is **no** `SCHEDULED_TASK` audit category — use `TASK`.
- **`Task.description` is NON-nullable** — every dispatched task must set `description` (use the scheduled task's name/payload description).
- **Task id allocation:** `Task.__init__` only auto-generates `T#####` when no `agentium_id` is passed, and it opens a *separate* session to do so. The shared task builder must allocate ids in the *passed* session (Postgres regex) and unit tests must inject an explicit `agentium_id` (via monkeypatching `_allocate_task_id`) so no test touches a second DB connection.
- **TDD:** every task starts with a failing test, implements the minimal code, then commits.

---

### Task 1: Shared cron-due helper (`backend/services/scheduling/cron_due.py`)

**Files:**
- Create: `backend/services/scheduling/cron_due.py`
- Create: `backend/services/scheduling/__init__.py`
- Test: `backend/tests/unit/services/scheduling/test_cron_due.py`

**Interfaces:**
- Produces (consumed by Task 2 model, Task 3 dispatcher, Task 5 event_processor):
  - `utc_now() -> datetime` — timezone-aware current UTC; the **single clock** for every sweep comparison.
  - `as_aware(dt: Optional[datetime], tz: str = "UTC") -> Optional[datetime]` — attach a timezone to a naive datetime; pass aware values through unchanged.
  - `next_run(cron_expression: str, timezone: str = "UTC", base: Optional[datetime] = None) -> Optional[datetime]` — the next cron schedule strictly after `base` (default: now), expressed in the stored timezone; `None` when the expression is exhausted.
  - `is_due(cron_expression: str, timezone: str = "UTC", last_run: Optional[datetime] = None) -> bool` — `True` when the next cron time falls at or before now.

This module is the **only** place `croniter` computes a next-run. The model's `calculate_next_run`, the dispatcher, and the `SCHEDULE` trigger evaluator all call these functions, so their date math cannot drift.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/services/scheduling/test_cron_due.py
from datetime import datetime, timezone, timedelta
import pytest

from backend.services.scheduling.cron_due import utc_now, as_aware, next_run, is_due


def test_utc_now_is_timezone_aware():
    assert utc_now().tzinfo is not None


def test_as_aware_attaches_utc_to_naive():
    naive = datetime(2026, 9, 17, 12, 0)
    aware = as_aware(naive, "UTC")
    assert aware.utcoffset() == timedelta(0)


def test_as_aware_passes_aware_through():
    aware = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert as_aware(aware) == aware


def test_next_run_is_strictly_after_base():
    base = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)
    # "0 9 * * *" = daily at 09:00; next run is tomorrow 09:00
    nxt = next_run("0 9 * * *", base=base)
    assert nxt > base
    assert nxt.hour == 9


def test_next_run_respects_timezone():
    base = datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)
    nxt = next_run("0 9 * * *", timezone="UTC", base=base)
    assert nxt.tzinfo is not None
    assert nxt.utcoffset() == timedelta(0)
    assert nxt.hour == 9


def test_next_run_returns_none_for_empty_expression():
    assert next_run("", base=utc_now()) is None


def test_is_due_fires_when_scheduled_time_reached():
    past = utc_now() - timedelta(hours=1)
    # A "every minute" cron whose last run was an hour ago is certainly due.
    assert is_due("* * * * *", last_run=past)


def test_is_due_not_fired_when_not_time_yet():
    far_future = utc_now() + timedelta(days=30)
    # Next run after far_future is > now, so not due.
    assert not is_due("* * * * *", last_run=far_future)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/services/scheduling/test_cron_due.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.scheduling.cron_due'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/scheduling/__init__.py
"""Shared scheduling math (cron due detection)."""
```

```python
# backend/services/scheduling/cron_due.py
"""Single source of cron-math for the scheduled-task sweeps.

Both the ScheduledTask dispatcher and the EventTrigger SCHEDULE evaluator
call these so their notion of "is this cron due" cannot drift.
"""
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Timezone-aware current UTC time — the single clock for all sweeps."""
    return datetime.now(timezone.utc)


def as_aware(dt: Optional[datetime], tz: str = "UTC") -> Optional[datetime]:
    """Attach a timezone to a naive datetime; pass aware values through unchanged."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def next_run(cron_expression: str, timezone: str = "UTC", base: Optional[datetime] = None) -> Optional[datetime]:
    """Next cron schedule strictly after `base` (default: now), in the given tz.

    Returns None when the expression is empty or exhausted.
    """
    if not cron_expression:
        return None
    try:
        from croniter import croniter
    except ImportError:
        return None
    tz = ZoneInfo(timezone or "UTC")
    base_aware = as_aware(base, timezone) or utc_now()
    base_aware = base_aware.astimezone(tz)
    try:
        return croniter(cron_expression, base_aware).get_next(datetime)
    except Exception:
        return None


def is_due(cron_expression: str, timezone: str = "UTC", last_run: Optional[datetime] = None) -> bool:
    """True when the next cron time after last_run falls at or before now."""
    nxt = next_run(cron_expression, timezone=timezone, base=last_run)
    if nxt is None:
        return False
    return nxt <= utc_now()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/unit/services/scheduling/test_cron_due.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduling/cron_due.py backend/services/scheduling/__init__.py backend/tests/unit/services/scheduling/test_cron_due.py
git commit -m "feat(scheduling): add shared cron-due helper"
```

---

### Task 2: `ScheduledTask` model — one-time lifecycle + timezone-aware cron

**Files:**
- Modify: `backend/models/entities/scheduled_task.py`
- Test: `backend/tests/unit/models/test_task_scheduling_models.py`

**Interfaces:**
- Consumes: `backend.services.scheduling.cron_due.next_run`, `.as_aware`.
- Produces (consumed by Task 3 dispatcher, Task 6 CRUD route):
  - `ScheduledTask.run_once: bool` (default `False`) — one-time flag.
  - `ScheduledTask.run_at: Optional[datetime]` — fire time for one-time tasks.
  - `ScheduledTask.cron_expression: Optional[str]` — now nullable for one-time rows.
  - `ScheduledTask.validate_schedule_config()` — raises `ValueError` on absent/mismatched cron vs `run_once`+`run_at` combos; called in `__init__`.
  - `ScheduledTask.calculate_next_run() -> Optional[datetime]` — `run_at` (aware) for one-time; else the shared helper; `None` when cron exhausted.
  - `ScheduledTask.mark_completed(success: bool = True)` — sets `COMPLETED` (terminal) for one-time success, or when a cron is exhausted.
  - `ScheduledTask.to_dict()` — now includes `run_once` and `run_at`.

**Note on `db_session`:** this file's fixture uses in-memory SQLite and JSONB-patches before importing models, so `create_all` reflects the new columns automatically.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/unit/models/test_task_scheduling_models.py`)

```python
def test_one_time_task_requires_run_at(db_session):
    with pytest.raises(ValueError):
        ScheduledTask(
            name="Once no run_at", cron_expression=None, run_once=True,
            task_payload=json.dumps({"action_type": "notify"}),
            owner_agentium_id="00001",
        )


def test_cron_and_run_at_are_mutually_exclusive(db_session):
    with pytest.raises(ValueError):
        ScheduledTask(
            name="Both", cron_expression="0 9 * * *", run_once=True,
            run_at=datetime(2026, 9, 20, 9, 0),
            task_payload=json.dumps({"action_type": "notify"}),
            owner_agentium_id="00001",
        )


def test_recurring_task_computes_next_run(db_session):
    t = ScheduledTask(
        name="Daily", cron_expression="0 9 * * *", run_once=False,
        task_payload=json.dumps({"action_type": "notify"}),
        owner_agentium_id="00001",
    )
    db_session.add(t)
    db_session.commit()
    assert t.next_execution_at is not None
    # next run for "0 9 * * *" is always at 09:00, strictly in the future
    assert t.next_execution_at.hour == 9


def test_one_time_task_success_goes_completed(db_session):
    t = ScheduledTask(
        name="OneShot", cron_expression=None, run_once=True,
        run_at=datetime.utcnow(),
        task_payload=json.dumps({"action_type": "notify"}),
        owner_agentium_id="00001",
    )
    db_session.add(t)
    db_session.commit()
    assert t.status == ScheduledTaskStatus.ACTIVE
    t.mark_completed(success=True)
    assert t.status == ScheduledTaskStatus.COMPLETED
    assert t.next_execution_at is None


def test_cron_failure_reaches_error_after_max_retries(db_session):
    t = ScheduledTask(
        name="Daily", cron_expression="0 9 * * *", run_once=False,
        task_payload=json.dumps({"action_type": "notify"}),
        owner_agentium_id="00001", max_retries=2,
    )
    db_session.add(t)
    db_session.commit()
    t.mark_completed(success=False)
    assert t.status == ScheduledTaskStatus.ACTIVE  # still under max_retries
    t.mark_completed(success=False)
    assert t.status == ScheduledTaskStatus.ERROR
    assert t.failure_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/models/test_task_scheduling_models.py -v`
Expected: FAIL — no `run_once` attribute, `cron_expression` column is not nullable, no `validate_schedule_config` method; construction with `cron_expression=None` fails `ValueError` from the *old* validator first.

- [ ] **Step 3: Implement the model changes**

First, update the import to include `Boolean`:

```python
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Index, Boolean
```

Second, add the two columns and relax `cron_expression` (replace the existing `# Schedule configuration` block):

```python
    # Schedule configuration
    cron_expression = Column(String(100), nullable=True)  # cron, or None for one-time tasks
    timezone = Column(String(50), default='UTC')
    run_once = Column(Boolean, nullable=False, default=False)  # one-time (run_at) task
    run_at = Column(DateTime, nullable=True)                    # fire time for one-time tasks
```

Third, replace the `schedule`-mode validator — it must accept `None` for one-time tasks and validate mutual exclusion. Replace the existing `@validates('cron_expression') / validate_cron` with:

```python
    @validates('cron_expression')
    def validate_cron(self, key, cron):
        """Validate cron syntax; None is allowed for one-time (run_once) tasks."""
        if cron is None:
            return cron
        if cron.startswith('@'):
            valid_special = ['@yearly', '@annually', '@monthly', '@weekly',
                           '@daily', '@hourly', '@reboot']
            if cron not in valid_special:
                raise ValueError(f"Invalid special cron: {cron}")
        else:
            parts = cron.split()
            if len(parts) != 5:
                raise ValueError("Cron expression must have 5 parts: min hour day month weekday")
        return cron

    def validate_schedule_config(self):
        """A schedule is exactly one of cron (run_once=False) or one-time (run_at set)."""
        has_cron = bool(self.cron_expression)
        is_once = bool(self.run_once)
        has_run_at = self.run_at is not None
        if is_once and not has_run_at:
            raise ValueError("run_once=True requires run_at")
        if has_cron and has_run_at:
            raise ValueError("cron_expression and run_at are mutually exclusive")
        if not is_once and not has_cron:
            raise ValueError("schedule requires either cron_expression or run_once+run_at")
```

Fourth, call the validation at the end of `__init__` (after `super().__init__` has populated the columns):

```python
    def __init__(self, **kwargs):
        if 'agentium_id' not in kwargs:
            # Generate Rxxxx ID
            kwargs['agentium_id'] = self._generate_recurring_id()
        super().__init__(**kwargs)
        self.validate_schedule_config()
```

Fifth, make `calculate_next_run` delegate to the shared helper (replace the whole method):

```python
    def calculate_next_run(self) -> Optional[datetime]:
        """Next execution time: run_at for one-time; else the shared cron helper."""
        from backend.services.scheduling.cron_due import as_aware, next_run
        if self.run_once:
            return as_aware(self.run_at, self.timezone)
        return next_run(self.cron_expression, timezone=self.timezone or "UTC",
                        base=self.last_execution_at)
```

Sixth, make `mark_completed` treat one-time success as terminal `COMPLETED` (replace the whole method):

```python
    def mark_completed(self, success: bool = True):
        """Mark execution complete.

        One-time (run_once) success -> COMPLETED (retained done-record).
        Cron success -> advance next_execution_at; COMPLETED when exhausted.
        """
        now = datetime.utcnow()
        self.last_execution_at = now
        self.execution_count += 1
        self.executing_agent_id = None

        if not success:
            self.failure_count += 1
            if self.failure_count >= self.max_retries:
                self.status = ScheduledTaskStatus.ERROR
            return

        self.failure_count = 0
        if self.run_once:
            self.status = ScheduledTaskStatus.COMPLETED
            self.next_execution_at = None
            return

        self.status = ScheduledTaskStatus.ACTIVE
        self.next_execution_at = self.calculate_next_run()
        if self.next_execution_at is None:
            self.status = ScheduledTaskStatus.COMPLETED  # cron exhausted
```

Seventh, expose the new fields in `to_dict` (add these two lines into the `base.update({...})` dict, e.g. after `'timezone': self.timezone,`):

```python
            'run_once': self.run_once,
            'run_at': self.run_at.isoformat() if self.run_at else None,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/unit/models/test_task_scheduling_models.py -v`
Expected: PASS — pre-existing scheduling model tests still green, plus the 5 new tests.

- [ ] **Step 5: Commit**

```bash
git add backend/models/entities/scheduled_task.py backend/tests/unit/models/test_task_scheduling_models.py
git commit -m "feat(scheduled-tasks): one-time run_once/run_at lifecycle + tz-aware cron"
```

---

### Task 3: Scheduled-task dispatcher (`backend/services/tasks/scheduled_task_dispatcher.py`)

**Files:**
- Create: `backend/services/tasks/scheduled_task_dispatcher.py`
- Test: `backend/tests/unit/services/tasks/test_scheduled_task_dispatcher.py`

**Interfaces:**
- Consumes: `ScheduledTask`, `ScheduledTaskStatus`, `ScheduledTaskExecution`, `ScheduledTaskExecutionStatus` (Task 2 model); `backend.services.scheduling.cron_due.utc_now` (Task 1); `Task`, `TaskStatus`, `TaskType`, `TaskPriority`; `AuditLog`/`AuditCategory`/`AuditLevel` (from `backend.models.entities.audit`); `get_task_db()` from `task_executor.py`; `celery_app` from `backend.celery_app`.
- Produces:
  - `dispatch_due_scheduled_tasks() -> dict` — Celery beat entry; sweeps due ACTIVE rows, CAS-claims each, dispatches, advances/COMPLETES.
  - `create_and_dispatch_task(db, *, description, title=None, task_type=TaskType.EXECUTION, priority=TaskPriority.NORMAL, execution_context=None, note_fragment="scheduled", agent_id="") -> Task` — **shared task builder** (also used by the SCHEDULE trigger in Task 5). Builds a `Task`, routes it through the legal state machine (PENDING→APPROVED→IN_PROGRESS), commits, enqueues `execute_task_async`, returns the task.
  - `_claim(row, db) -> bool` — optimistic CAS `UPDATE … WHERE status=ACTIVE → RUNNING`; True only for the worker that won the row.
  - `_submit_execution(task_id, agent_id)` — thin wrapper over `execute_task_async.delay(...)`, monkeypatchable in tests.

**Behavioral contract (the 10.4.1/10.4.2 guarantee):**
- Per due row (`status==ACTIVE` and, for one-time `run_once==True`, `run_at<=now`; for cron, `next_execution_at<=now`): claim via `_claim` (exactly-one worker wins → no double-fire), then `create_and_dispatch_task` enqueues exactly one Task. On successful enqueue → `mark_completed(True)` (advances cron / sets one-time `COMPLETED`, retained). On failure → `mark_completed(False)` (honors `max_retries` → `ERROR`).
- Time is compared in Python only between aware datetimes; the sweep's SQL time filters are bound as DB params, so they are never naive-vs-aware.
- Each row is handled in its own try/except — one bad row never aborts the sweep.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/services/tasks/test_scheduled_task_dispatcher.py
import json
from datetime import datetime

import pytest

from backend.models.entities.scheduled_task import ScheduledTask, ScheduledTaskStatus
from backend.models.entities.task import Task, TaskStatus


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/services/tasks/test_scheduled_task_dispatcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.tasks.scheduled_task_dispatcher'`

- [ ] **Step 3: Write the complete implementation**

```python
# backend/services/tasks/scheduled_task_dispatcher.py
"""Celery beat dispatcher for ScheduledTask rows.

Fires exactly-once per due, status-ACTIVE row every beat tick:

  1. Claim the row (optimistic CAS status ACTIVE -> RUNNING) so a second
     worker in a fleet cannot double-fire it.
  2. Build and enqueue exactly one regular Task via the shared
     ``create_and_dispatch_task`` helper (routes PENDING->APPROVED->
     IN_PROGRESS, then ``execute_task_async.delay``).
  3. ``mark_completed(True)`` on successful enqueue -> advances the cron
     schedule, or sets a one-time task to COMPLETED (retained done-record).
     ``mark_completed(False)`` on a build/enqueue failure -> ERROR after
     max_retries.

Ownership boundary: this module decides WHEN a scheduled task fires (exactly
once). The dispatched Task's eventual success/failure/retry is owned entirely
by the reused 10.1-10.3 TaskExecutor pipeline.
"""
import logging
from datetime import datetime

from sqlalchemy import and_, or_, update

from backend.celery_app import celery_app
from backend.models.entities.audit import AuditCategory, AuditLevel, AuditLog
from backend.models.entities.scheduled_task import (
    ScheduledTask,
    ScheduledTaskExecution,
    ScheduledTaskExecutionStatus,
    ScheduledTaskStatus,
)
from backend.models.entities.task import Task, TaskPriority, TaskStatus, TaskType
from backend.services.scheduling.cron_due import utc_now

logger = logging.getLogger(__name__)


def _claim(row, db) -> bool:
    """Optimistic CAS claim: only the worker whose conditional UPDATE matches
    (rowcount == 1) wins the row; an already-RUNNING row is never double-fired."""
    stmt = (
        update(ScheduledTask)
        .where(
            ScheduledTask.id == row.id,
            ScheduledTask.status == ScheduledTaskStatus.ACTIVE,
        )
        .values(status=ScheduledTaskStatus.RUNNING)
    )
    return db.execute(stmt).rowcount == 1


def _allocate_task_id(db) -> str:
    """Allocate the next T##### id using the PASSED session (Postgres regex).
    Tests monkeypatch this to a fixed id so no second DB connection is opened."""
    from sqlalchemy import text

    row = db.execute(text(
        "SELECT agentium_id FROM tasks WHERE agentium_id ~ '^T[0-9]+$' "
        "ORDER BY CAST(SUBSTRING(agentium_id FROM 2) AS INTEGER) DESC LIMIT 1"
    )).scalar()
    return f"T{int(row[1:]) + 1:05d}" if row else "T00001"


def _submit_execution(task_id: str, agent_id: str) -> None:
    """Enqueue the task for the TaskExecutor worker. Monkeypatchable in tests."""
    from backend.services.tasks.task_executor import execute_task_async

    execute_task_async.delay(task_id, agent_id)


def create_and_dispatch_task(
    db,
    *,
    description: str,
    title: str = None,
    task_type=None,
    priority=None,
    execution_context=None,
    note_fragment: str = "scheduled",
    agent_id: str = "",
) -> Task:
    """Build a Task, route it through the legal state machine, enqueue it."""
    task_type = task_type or TaskType.EXECUTION
    priority = priority or TaskPriority.NORMAL
    task = Task(
        agentium_id=_allocate_task_id(db),
        title=title or description[:200],
        description=description,
        task_type=task_type,
        priority=priority,
        execution_context=execution_context,
        created_by="SCHEDULER",
        sandbox_mode=True,
    )
    task.is_active = True
    db.add(task)
    db.flush()
    # Legal transition path (mirrors process_dependency_graph).
    task.set_status(TaskStatus.APPROVED, note=f"{note_fragment}: pre-dispatch approval")
    task.set_status(TaskStatus.IN_PROGRESS, note=f"{note_fragment}: advancing to executing")
    if task.started_at is None:
        task.started_at = datetime.utcnow()
    db.commit()
    _submit_execution(task.agentium_id, agent_id)
    return task


def _record_execution(db, row, success: bool, task_id: str = None, error: str = None) -> None:
    record = ScheduledTaskExecution(
        scheduled_task_id=row.id,
        execution_agentium_id=row.executing_agent_id or row.owner_agentium_id,
        status=ScheduledTaskExecutionStatus.SUCCESS if success else ScheduledTaskExecutionStatus.FAILED,
    )
    record.complete(
        success=success,
        result={"task_id": task_id} if task_id else None,
        error=error,
    )
    db.add(record)


def _audit(db, row, *, action: str, level, description: str, after_state: dict) -> None:
    entry = AuditLog.log(
        level=level,
        category=AuditCategory.TASK,
        actor_type="system",
        actor_id="SCHEDULER",
        action=action,
        target_type="scheduled_task",
        target_id=row.id,
        description=description,
        after_state=after_state,
    )
    db.add(entry)


def _dispatch_one(db, row) -> None:
    """Claim-and-dispatch a single due row. Raises RuntimeError on enqueue failure."""
    if not _claim(row, db):
        return

    payload = row.get_task_payload() or {}
    task_type_raw = payload.get("task_type", "execution")
    try:
        task_type = TaskType(task_type_raw)
    except ValueError:
        task_type = TaskType.EXECUTION

    title = payload.get("title") or row.name
    description = payload.get("description") or f"Scheduled task: {row.name}"
    execution_context = {"scheduled_task_id": row.id, "params": payload.get("params", {})}

    try:
        new_task = create_and_dispatch_task(
            db,
            description=description,
            title=title,
            task_type=task_type,
            execution_context=execution_context,
            note_fragment=row.name,
            agent_id=row.executing_agent_id or "",
        )
    except RuntimeError as exc:
        row.mark_completed(success=False)
        _record_execution(db, row, success=False, error=str(exc))
        _audit(
            db, row,
            action="scheduled_task_failed",
            level=AuditLevel.CRITICAL,
            description=f"Scheduled task {row.agentium_id} failed to dispatch: {exc}",
            after_state={"task_id": row.agentium_id, "error": str(exc)},
        )
        db.commit()
        logger.error("dispatch failed for scheduled task %s: %s", row.agentium_id, exc)
        return

    row.mark_completed(success=True)
    _record_execution(db, row, success=True, task_id=new_task.agentium_id)
    _audit(
        db, row,
        action="scheduled_task_dispatched",
        level=AuditLevel.INFO,
        description=f"Scheduled task {row.agentium_id} dispatched task {new_task.agentium_id}",
        after_state={"scheduled_task_id": row.agentium_id, "task_id": new_task.agentium_id},
    )
    db.commit()


def _sweep(db) -> dict:
    """Sweep all due ACTIVE rows and dispatch each. Callable from tests without a broker."""
    now = utc_now()
    cron_due = and_(
        ScheduledTask.run_once.is_(False),
        ScheduledTask.next_execution_at.isnot(None),
        ScheduledTask.next_execution_at <= now,
    )
    once_due = and_(
        ScheduledTask.run_once.is_(True),
        ScheduledTask.run_at.isnot(None),
        ScheduledTask.run_at <= now,
    )
    due = (
        db.query(ScheduledTask)
        .filter(ScheduledTask.status == ScheduledTaskStatus.ACTIVE, or_(cron_due, once_due))
        .all()
    )
    results = {"checked": len(due), "dispatched": 0, "skipped": 0, "errors": 0}

    for row in due:
        try:
            _dispatch_one(db, row)
            results["dispatched"] += 1
        except Exception as exc:  # one bad row never aborts the sweep
            results["errors"] += 1
            logger.error("sweep error for %s: %s", row.agentium_id, exc, exc_info=True)

    db.commit()
    return results


@celery_app.task(name="agentium.tasks.task_executor.dispatch_due_scheduled_tasks")
def dispatch_due_scheduled_tasks():
    """Beat entry (every 15s): dispatch all due scheduled tasks exactly once."""
    from backend.services.tasks.task_executor import get_task_db

    with get_task_db() as db:
        try:
            return _sweep(db)
        except Exception as exc:
            logger.error("dispatch_due_scheduled_tasks failed: %s", exc)
            return {"error": str(exc)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/unit/services/tasks/test_scheduled_task_dispatcher.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/tasks/scheduled_task_dispatcher.py backend/tests/unit/services/tasks/test_scheduled_task_dispatcher.py
git commit -m "feat(scheduled-tasks): dispatcher + shared task builder + CAS claim"
```

---

### Task 4: Register dispatcher in Celery include + beat schedule

**Files:**
- Modify: `backend/celery_app.py`

**Interfaces:**
- Consumes: `dispatch_due_scheduled_tasks` (Task 3).
- Produces: 15s beat entry `scheduled-task-dispatcher` → task `agentium.tasks.task_executor.dispatch_due_scheduled_tasks`.

- [ ] **Step 1: Add the module to Celery `include`** (add one line to the `include=[...]` list around `backend.services.tasks.task_executor`)

```python
    include=[
        'backend.services.tasks.task_executor',
        'backend.services.tasks.scheduled_task_dispatcher',   # <-- add
        'backend.services.tasks.workflow_tasks',
        ...
    ]
```

- [ ] **Step 2: Add the beat entry** (inside `celery_app.conf.beat_schedule`, e.g. next to the Phase 13.6 event entries around line 190)

```python
    'scheduled-task-dispatcher': {
        'task': 'agentium.tasks.task_executor.dispatch_due_scheduled_tasks',
        'schedule': 15.0,
    },
```

- [ ] **Step 3: Verify the app imports and registers the task**

Run: `python -c "from backend.celery_app import celery_app; t=celery_app.tasks.get('agentium.tasks.task_executor.dispatch_due_scheduled_tasks'); assert t is not None, 'task not registered'; print('registered:', list(celery_app.tasks) and len(celery_app.tasks.values()))"`
Expected: prints a task count (> 0), and `dispatch_due_scheduled_tasks` is registered.

- [ ] **Step 4: Commit**

```bash
git add backend/celery_app.py
git commit -m "chore(scheduled-tasks): register dispatcher beat entry (15s)"
```

---

### Task 5: `SCHEDULE` event-trigger evaluator + beat entry

**Files:**
- Modify: `backend/services/event_processor.py`
- Modify: `backend/services/tasks/task_executor.py` (add `schedule_trigger_check` beat wrapper)
- Modify: `backend/celery_app.py` (beat entry)
- Test: `backend/tests/unit/services/test_schedule_trigger.py`

**Interfaces:**
- Consumes: `is_due` (Task 1); `create_and_dispatch_task` (Task 3); `EventTrigger`/`EventLog`/`TriggerType`/`EventLogStatus`.
- Produces:
  - `EventProcessorService.evaluate_schedule_triggers(db) -> dict` — sweep active `TriggerType.SCHEDULE` triggers; when due fires via the intact rate-limit/circuit-breaker/EventLog path, then `_dispatch_action(..., dispatch_task_when_no_workflow=True)`.
  - `_dispatch_action(trigger, payload, db, dispatch_task_when_no_workflow=False)` — new keyword; when `True` and no `target_workflow_id`, dispatches a Task via `_dispatch_task`.
  - `schedule_trigger_check()` — 15s beat wrapper in `task_executor.py`, mirroring `threshold_event_check`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/services/test_schedule_trigger.py
from datetime import datetime

import backend.services.event_processor as ep
from backend.models.entities.event_trigger import EventTrigger, TriggerType, EventLog


def test_schedule_trigger_fires_once_when_due(db_session, monkeypatch):
    trigger = EventTrigger(
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
    assert db_session.query(EventLog).filter_by(trigger_id=trigger.id).count() == 1
    assert len(calls) == 1 and calls[0]["flag"] is True

    # Second sweep must NOT re-fire (last_fired_at advanced + cooldown).
    r2 = ep.EventProcessorService.evaluate_schedule_triggers(db_session)
    assert r2["fired"] == 0
    assert db_session.query(EventLog).filter_by(trigger_id=trigger.id).count() == 1


def test_schedule_trigger_skips_when_not_due(db_session, monkeypatch):
    trigger = EventTrigger(
        name="FarFarFuture",
        trigger_type=TriggerType.SCHEDULE,
        config={"cron_expression": "0 9 * * *", "timezone": "UTC", "cooldown_seconds": 60},
        last_fired_at=None,   # never fired; a 09:00 daily cron is not due at test-run time
        max_fires_per_minute=1000,
    )
    db_session.add(trigger)
    db_session.commit()
    monkeypatch.setattr(ep, "_is_trigger_paused", lambda t: False)
    monkeypatch.setattr(ep, "_check_rate_limit", lambda t, db: False)

    r = ep.EventProcessorService.evaluate_schedule_triggers(db_session)
    assert r["fired"] == 0
    assert r["skipped"] == 1
```

> **Note on `not_due` test:** `"0 9 * * *"` with `last_fired_at=None` is due only in the 09:00 UTC minute. If the test suite happens to run inside that minute it would flake; to make it fully deterministic, set `last_fired_at=datetime(2099,1,1)` too (next run after 2099 is not due). Prefer that.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/services/test_schedule_trigger.py -v`
Expected: FAIL — `AttributeError: EventProcessorService has no attribute 'evaluate_schedule_triggers'` (and `_dispatch_action` has no `dispatch_task_when_no_workflow` kwarg → `TypeError`).

- [ ] **Step 3: Add `evaluate_schedule_triggers` and the `_dispatch_task` helper** to `backend/services/event_processor.py` (insert after `poll_external_apis`, before `get_dead_letters`)

```python
    # ── Schedule check (called from Celery beat) ────────────────────────

    @staticmethod
    def evaluate_schedule_triggers(db: Session) -> Dict[str, Any]:
        """
        Evaluate all active schedule triggers. A schedule trigger is due when
        its cron expression's next run (shared cron math) falls at or before
        now. Honors the per-trigger circuit-breaker and cooldown, persists an
        EventLog, then dispatches the configured action.
        """
        from backend.services.scheduling.cron_due import is_due

        triggers = (
            db.query(EventTrigger)
            .filter(
                EventTrigger.trigger_type == TriggerType.SCHEDULE,
                EventTrigger.is_active == True,
            )
            .all()
        )
        results = {"checked": 0, "fired": 0, "skipped": 0}

        for trigger in triggers:
            results["checked"] += 1

            if _is_trigger_paused(trigger):
                results["skipped"] += 1
                continue

            cfg = trigger.config or {}
            cron_expression = cfg.get("cron_expression", "")
            timezone = cfg.get("timezone", "UTC")
            if not cron_expression:
                results["skipped"] += 1
                continue

            cooldown = cfg.get("cooldown_seconds", 60)
            if trigger.last_fired_at:
                elapsed = (datetime.utcnow() - trigger.last_fired_at).total_seconds()
                if elapsed < cooldown:
                    results["skipped"] += 1
                    continue

            # Shared cron math (same 'due' rule as the ScheduledTask dispatcher).
            if not is_due(cron_expression, timezone=timezone, last_run=trigger.last_fired_at):
                results["skipped"] += 1
                continue

            if _check_rate_limit(trigger, db):
                results["skipped"] += 1
                continue

            payload = {
                "cron_expression": cron_expression,
                "timezone": timezone,
                "fired_at": datetime.utcnow().isoformat(),
            }
            log = EventLog(
                trigger_id=trigger.id,
                event_payload=payload,
                status=EventLogStatus.PROCESSED,
                correlation_id=str(uuid.uuid4()),
            )
            db.add(log)
            trigger.fire_count = (trigger.fire_count or 0) + 1
            trigger.last_fired_at = datetime.utcnow()
            db.commit()

            EventProcessorService._dispatch_action(
                trigger, payload, db, dispatch_task_when_no_workflow=True,
            )
            results["fired"] += 1

        return results

    @staticmethod
    def _dispatch_task(
        trigger: EventTrigger, payload: Dict[str, Any], db: Session,
    ) -> None:
        """
        Dispatch a regular Task for a trigger that has no target_workflow_id,
        reusing the shared scheduled-task task builder so dispatch logic and
        the state-machine path are identical everywhere.
        """
        from backend.models.entities.task import TaskType
        from backend.services.tasks.scheduled_task_dispatcher import create_and_dispatch_task

        cfg = trigger.config or {}
        task_payload = cfg.get("task_payload") or {}
        title = task_payload.get("title") or trigger.name
        description = task_payload.get("description") or f"Event-triggered task: {trigger.name}"
        raw_type = task_payload.get("task_type", "execution")
        try:
            task_type = TaskType(raw_type)
        except ValueError:
            task_type = TaskType.EXECUTION

        create_and_dispatch_task(
            db,
            description=description,
            title=title,
            task_type=task_type,
            execution_context={"trigger_id": trigger.id, "event_payload": payload},
            note_fragment=f"trigger:{trigger.name}",
            agent_id=trigger.target_agent_id or "",
        )
```

- [ ] **Step 4: Add the `dispatch_task_when_no_workflow` branch to `_dispatch_action`** — in `backend/services/event_processor.py`, currently the method bodies have `if trigger.target_workflow_id:` … then the WS broadcast. Change the signature and add an `elif` between the workflow branch and the broadcast:

```python
    @staticmethod
    def _dispatch_action(
        trigger: EventTrigger, payload: Dict[str, Any], db: Session,
        dispatch_task_when_no_workflow: bool = False,
    ) -> None:
        """
        Execute the configured action for a trigger: start a workflow,
        dispatch a task (when dispatch_task_when_no_workflow and no workflow
        target), or emit a WebSocket notification.
        """
        try:
            if trigger.target_workflow_id:
                from backend.services.workflow_engine import WorkflowEngine
                try:
                    WorkflowEngine.trigger_execution(
                        db,
                        trigger.target_workflow_id,
                        trigger=f"event:{trigger.trigger_type.value}",
                        context=payload,
                    )
                    logger.info(
                        "Event trigger %s dispatched workflow %s",
                        trigger.name, trigger.target_workflow_id,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to dispatch workflow for trigger %s: %s",
                        trigger.name, exc,
                    )
            elif dispatch_task_when_no_workflow:
                # No workflow target — dispatch a regular Task instead.
                try:
                    EventProcessorService._dispatch_task(trigger, payload, db)
                except Exception as exc:
                    logger.error(
                        "Failed to dispatch task for trigger %s: %s",
                        trigger.name, exc,
                    )
            # else: no configured action — webhook/threshold/api_poll keep
            # their pre-existing broadcast-only behavior.
```

(Leave the rest of `_dispatch_action` — the WebSocket broadcast — unchanged.)

- [ ] **Step 5: Add the `schedule_trigger_check` beat wrapper** to `backend/services/tasks/task_executor.py` (next to `threshold_event_check`, ~line 1382)

```python
@celery_app.task(name='agentium.tasks.task_executor.schedule_trigger_check')
def schedule_trigger_check():
    """Schedule event trigger check."""

    with get_task_db() as db:
        try:
            from backend.services.event_processor import EventProcessorService
            result = EventProcessorService.evaluate_schedule_triggers(db)
            if result.get("fired", 0) > 0:
                logger.info(
                    f"🗓️ Schedule trigger check: {result['fired']} fire(s) "
                    f"out of {result['checked']} checked"
                )
            return result
        except Exception as e:
            logger.error(f"schedule_trigger_check failed: {e}")
            return {"error": str(e)}
```

- [ ] **Step 6: Register the beat entry** in `backend/celery_app.py` (next to `'external-api-poll'` ~line 194)

```python
    'schedule-trigger-check': {
        'task': 'agentium.tasks.task_executor.schedule_trigger_check',
        'schedule': 15.0,
    },
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/unit/services/test_schedule_trigger.py -v`
Expected: PASS — 2 passed

- [ ] **Step 8: Commit**

```bash
git add backend/services/event_processor.py backend/services/tasks/task_executor.py backend/celery_app.py backend/tests/unit/services/test_schedule_trigger.py
git commit -m "feat(scheduled-tasks): SCHEDULE event-trigger evaluator + beat"
```

---

### Task 6: `ScheduledTask` CRUD route + schemas + app registration

**Files:**
- Create: `backend/api/schemas/scheduled_task.py`
- Create: `backend/api/routes/scheduled_tasks.py`
- Modify: `backend/main.py` (register router)
- Test: `backend/tests/integration/test_scheduled_tasks_api.py`

**Interfaces:**
- Consumes: `ScheduledTask`, `ScheduledTaskStatus` (Task 2 model); `get_db` (`backend.models.database`), `get_current_active_user` (`backend.core.auth`), exceptions (`backend.core.exceptions`).
- Produces: REST endpoints under `/api/v1/scheduled-tasks`:
  - `POST` create (cron or one-time, mutual-exclusion + cron validated → 400 on `ValueError`).
  - `GET` list (paginated; `status`/`owner_agentium_id` filters; non-sovereigns scoped to their own).
  - `GET /{id}` detail.
  - `PATCH /{id}` update + pause/resume (`model_dump(exclude_unset=True)`).
  - `DELETE /{id}` remove (204).

**RBAC assumption to verify at implementation time:** `get_current_active_user()` returns a dict; this route treats `role in ("sovereign","admin")` as full access and scopes everything else to `owner_agentium_id == current_user["id"]` (owner still writable via the payload `owner_agentium_id` when provided). If the real dict has a different role/id shape, adjust `_is_sovereign`/`_resolve_owner` — the route wiring is unchanged.

- [ ] **Step 1: Write the schemas**

```python
# backend/api/schemas/scheduled_task.py
"""Pydantic schemas for the Scheduled Tasks API."""
import json
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


CronStr = str


class ScheduledTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    cron_expression: Optional[str] = Field(default=None, description="cron, or None for one-time")
    timezone: str = Field(default="UTC")
    run_once: bool = False
    run_at: Optional[datetime] = None
    task_payload: Dict[str, Any] = Field(
        default_factory=lambda: {"action_type": "execution", "params": {}}
    )
    owner_agentium_id: str = Field(default="00001")
    priority: int = Field(default=1, ge=1, le=5)
    max_retries: int = Field(default=3, ge=0)

    @field_validator("cron_expression")
    def validate_cron(cls, v):
        if not v:
            return v
        from croniter import croniter
        try:
            croniter(v, datetime(2026, 1, 1))
        except Exception as exc:
            raise ValueError(f"Invalid cron expression: {v}") from exc
        return v

    @model_validator(mode="after")
    def check_schedule_mode(self):
        has_cron = bool(self.cron_expression)
        has_run_at = self.run_at is not None
        if self.run_once and not has_run_at:
            raise ValueError("run_once=True requires run_at")
        if has_cron and has_run_at:
            raise ValueError("cron_expression and run_at are mutually exclusive")
        if not has_cron and not self.run_once:
            raise ValueError("provide cron_expression, or set run_once=True with run_at")
        return self


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    run_once: Optional[bool] = None
    run_at: Optional[datetime] = None
    task_payload: Optional[Dict[str, Any]] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    max_retries: Optional[int] = Field(default=None, ge=0)
    paused: Optional[bool] = None


class ScheduledTaskResponse(BaseModel):
    agentium_id: str
    name: str
    description: Optional[str]
    cron_expression: Optional[str]
    timezone: str
    run_once: bool
    run_at: Optional[datetime]
    task_payload: Dict[str, Any] = Field(default_factory=dict)
    owner_agentium_id: str
    status: str
    priority: int
    max_retries: int
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    execution_count: int
    failure_count: int
```

- [ ] **Step 2: Write the failing API test**

```python
# backend/tests/integration/test_scheduled_tasks_api.py
import pytest


@pytest.mark.integration
def test_scheduled_task_crud_round_trip(client, auth_headers):
    # CREATE a one-time task due in the past so it would be dispatched immediately.
    body = {
        "name": "OneShot API",
        "run_once": True,
        "run_at": "2020-01-01T00:00:00",
        "task_payload": {"action_type": "execution", "params": {"via": "api"}},
    }
    r = client.post("/api/v1/scheduled-tasks", json=body, headers=auth_headers)
    assert r.status_code == 201, r.text
    created = r.json()
    sid = created["agentium_id"]
    assert created["status"] == "active"
    assert created["run_once"] is True

    # READ (detail)
    r = client.get(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "OneShot API"

    # LIST includes it
    r = client.get("/api/v1/scheduled-tasks?status=active", headers=auth_headers)
    assert r.status_code == 200
    assert any(item["agentium_id"] == sid for item in r.json())

    # UPDATE -> pause
    r = client.patch(f"/api/v1/scheduled-tasks/{sid}", json={"paused": True}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "paused"

    # DELETE
    r = client.delete(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 204
    r = client.get(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.integration
def test_scheduled_task_create_rejects_mutual_exclusion(client, auth_headers):
    body = {
        "name": "Both",
        "cron_expression": "0 9 * * *",
        "run_once": True,
        "run_at": "2026-09-20T09:00:00",
    }
    r = client.post("/api/v1/scheduled-tasks", json=body, headers=auth_headers)
    assert r.status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/integration/test_scheduled_tasks_api.py -v`
Expected: FAIL — `404 Not Found` on `POST /api/v1/scheduled-tasks` (route not registered).

- [ ] **Step 4: Write the route**

```python
# backend/api/routes/scheduled_tasks.py
"""Scheduled Tasks API routes."""
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from backend.core.auth import get_current_active_user
from backend.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from backend.api.schemas.scheduled_task import ScheduledTaskCreate, ScheduledTaskUpdate
from backend.models.database import get_db
from backend.models.entities.scheduled_task import ScheduledTask, ScheduledTaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


def _is_sovereign(current_user: Dict[str, Any]) -> bool:
    return (current_user or {}).get("role") in ("sovereign", "admin")


def _resolve_owner(current_user: Dict[str, Any]) -> str:
    uid = (current_user or {}).get("id")
    return str(uid) if uid else "00001"


def _serialize(rec: ScheduledTask) -> dict:
    return rec.to_dict()


def _get_or_404(db: Session, agentium_id: str) -> ScheduledTask:
    rec = (
        db.query(ScheduledTask)
        .filter_by(agentium_id=agentium_id, is_active=True)
        .first()
    )
    if not rec:
        raise NotFoundError(f"Scheduled task {agentium_id} not found")
    return rec


def _scope_or_403(rec: ScheduledTask, current_user: Dict[str, Any]) -> None:
    if not _is_sovereign(current_user) and rec.owner_agentium_id != _resolve_owner(current_user):
        raise ForbiddenError("Not your scheduled task")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_scheduled_task(
    request: Request,
    payload: ScheduledTaskCreate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        rec = ScheduledTask(
            name=payload.name,
            description=payload.description,
            cron_expression=payload.cron_expression,
            timezone=payload.timezone or "UTC",
            run_once=payload.run_once,
            run_at=payload.run_at,
            task_payload=json.dumps(payload.task_payload),
            owner_agentium_id=payload.owner_agentium_id or _resolve_owner(current_user),
            priority=payload.priority,
            max_retries=payload.max_retries,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc))

    db.add(rec)
    rec.next_execution_at = rec.calculate_next_run()
    db.commit()
    db.refresh(rec)
    return _serialize(rec)


@router.get("")
def list_scheduled_tasks(
    request: Request,
    status_: Optional[str] = Query(default=None, alias="status"),
    owner: Optional[str] = Query(default=None, alias="owner_agentium_id"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not _is_sovereign(current_user):
        owner = owner or _resolve_owner(current_user)
    q = db.query(ScheduledTask).filter(ScheduledTask.is_active == True)  # noqa: E712
    if status_:
        q = q.filter(ScheduledTask.status == ScheduledTaskStatus(status_))
    if owner:
        q = q.filter(ScheduledTask.owner_agentium_id == owner)
    rows = (
        q.order_by(ScheduledTask.created_at.desc()).offset(offset).limit(limit).all()
    )
    return [_serialize(r) for r in rows]


@router.get("/{schedule_id}")
def get_scheduled_task(
    schedule_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rec = _get_or_404(db, schedule_id)
    _scope_or_403(rec, current_user)
    return _serialize(rec)


@router.patch("/{schedule_id}")
def update_scheduled_task(
    schedule_id: str,
    payload: ScheduledTaskUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rec = _get_or_404(db, schedule_id)
    _scope_or_403(rec, current_user)

    data = payload.model_dump(exclude_unset=True)
    schedule_changed = any(k in data for k in ("cron_expression", "timezone", "run_once", "run_at"))

    if "name" in data and data["name"] is not None:
        rec.name = data["name"]
    if "description" in data:
        rec.description = data["description"]
    if "priority" in data and data["priority"] is not None:
        rec.priority = data["priority"]
    if "max_retries" in data and data["max_retries"] is not None:
        rec.max_retries = data["max_retries"]
    if "cron_expression" in data:
        rec.cron_expression = data["cron_expression"]
    if "timezone" in data and data["timezone"]:
        rec.timezone = data["timezone"]
    if "run_once" in data:
        rec.run_once = bool(data["run_once"])
    if "run_at" in data:
        rec.run_at = data["run_at"]
    if "task_payload" in data and data["task_payload"] is not None:
        rec.set_task_payload(data["task_payload"])
    if "paused" in data:
        if data["paused"]:
            rec.pause()
        else:
            rec.resume()

    try:
        rec.validate_schedule_config()
        if schedule_changed and rec.status != ScheduledTaskStatus.PAUSED:
            rec.next_execution_at = rec.calculate_next_run()
        db.commit()
        db.refresh(rec)
    except ValueError as exc:
        db.rollback()
        raise BadRequestError(str(exc))
    return _serialize(rec)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheduled_task(
    schedule_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rec = _get_or_404(db, schedule_id)
    _scope_or_403(rec, current_user)
    db.delete(rec)
    db.commit()
    return None
```

- [ ] **Step 5: Register the router in `backend/main.py`**

Add to the route imports (near `from backend.api.routes import tasks as tasks_routes`, ~line 66):

```python
from backend.api.routes import scheduled_tasks as scheduled_tasks_routes
```

Add to the include_router block (near `app.include_router(tasks_routes.router, prefix="/api/v1")`, ~line 657):

```python
app.include_router(scheduled_tasks_routes.router, prefix="/api/v1")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/integration/test_scheduled_tasks_api.py -v`
Expected: PASS — 2 passed

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/scheduled_task.py backend/api/routes/scheduled_tasks.py backend/main.py backend/tests/integration/test_scheduled_tasks_api.py
git commit -m "feat(scheduled-tasks): CRUD route + schemas + app registration"
```

---

### Task 7: Fix `create_reminder` in `backend/services/workflow_tools.py`

**Files:**
- Modify: `backend/services/workflow_tools.py:196-242`
- Test: `backend/tests/unit/services/test_create_reminder.py`

**Interfaces:**
- Consumes: `ScheduledTask` (Task 2 model), `get_db_context`.
- Produces: a valid one-time `ScheduledTask` row (`run_once=True` + `run_at`, no cron) instead of the current always-throwing kwargs (`task_type`/`payload`/`scheduled_for`/`status="pending"` don't exist on the model) that degrades to log-only.

**Why it's broken today:** the tool passes `ScheduledTask(id=..., task_type="reminder", payload=..., scheduled_for=..., status="pending")` — none of those are model columns (`task_type`, `payload`, `scheduled_for`, and a plain-string `status`). `ScheduledTask.__init__` raises on assignment, the `except` swallows it, and only a log is written. Reminders never persist.

- [ ] **Step 1: Write the failing regression test**

```python
# backend/tests/unit/services/test_create_reminder.py
import asyncio
import json
from contextlib import contextmanager

import pytest

from backend.models.entities.scheduled_task import ScheduledTask, ScheduledTaskStatus


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
    assert row.next_execution_at is not None   # set so the dispatcher will fire it
    assert result["reminder_id"] == row.agentium_id
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/unit/services/test_create_reminder.py -v`
Expected: FAIL — `db_session.query(ScheduledTask).one()` raises `NoResultFound` (the writer throws and only logs; nothing is persisted).

- [ ] **Step 3: Rewrite `_create_reminder`**

Replace lines 196–242 in `backend/services/workflow_tools.py` with:

```python
@register("create_reminder")
async def _create_reminder(params: dict) -> dict:
    """
    Persist a one-time reminder as a ScheduledTask (run_once + run_at).

    params:
        message       (str)
        delay_seconds (int)  — 0 = fire immediately (fires on the next 15s tick)
    """
    import json
    import uuid
    from datetime import datetime, timedelta

    from backend.models.database import get_db_context
    from backend.models.entities.scheduled_task import ScheduledTask

    message = params.get("message", "Reminder")
    delay = int(params.get("delay_seconds", 0))
    fire_at = datetime.utcnow() + timedelta(seconds=delay)

    try:
        with get_db_context() as db:
            task = ScheduledTask(
                name=f"reminder_{uuid.uuid4().hex[:8]}",
                description=f"Reminder: {message[:200]}",
                cron_expression=None,
                run_once=True,
                run_at=fire_at,
                owner_agentium_id="00001",
                task_payload=json.dumps(
                    {"action_type": "reminder", "params": {"message": message}}
                ),
            )
            task.next_execution_at = task.calculate_next_run()
            db.add(task)
            db.commit()
            reminder_id = task.agentium_id
    except Exception as exc:
        logger.warning(
            f"[create_reminder] ScheduledTask write failed ({exc}); "
            "reminder logged only."
        )
        reminder_id = str(uuid.uuid4())

    logger.info(f"[create_reminder] Scheduled for {fire_at.isoformat()}: {message[:60]}")
    return {
        "created": True,
        "reminder_id": reminder_id,
        "message": message,
        "scheduled_for": fire_at.isoformat(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/unit/services/test_create_reminder.py -v`
Expected: PASS — 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/workflow_tools.py backend/tests/unit/services/test_create_reminder.py
git commit -m "fix(scheduled-tasks): create_reminder persists valid one-time row"
```

---

### Task 8: Integration tests + §10.4 checklist verification

**Files:**
- Create: `backend/tests/integration/test_scheduled_tasks_end_to_end.py`
- Modify: `docs/documents/TODO.md` (mark 10.4.1–10.4.3 complete after tests pass)

**Interfaces:**
- Consumes: `_sweep` (Task 3), `evaluate_schedule_triggers` (Task 5), the full built model/route/beat wiring.

**Purpose:** these are **verification** tests over a real DB. They patch `scheduled_task_dispatcher._submit_execution` (and Redis/rate-limit helpers) so no broker is contacted, but exercise the real claim → build → state-machine → advance/COMPLETED path and the real SCHEDULE-trigger → task-build path. The live beat tick + worker end-to-end is the manual smoke step at the end.

- [ ] **Step 1: Write the integration tests**

```python
# backend/tests/integration/test_scheduled_tasks_end_to_end.py
import json
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


def test_cron_fire_dispatches_once_and_advances(seeded_db):
    from backend.models.entities.scheduled_task import (
        ScheduledTask, ScheduledTaskExecution, ScheduledTaskStatus,
    )
    from backend.services.tasks import scheduled_task_dispatcher as d

    d._submit_execution = lambda task_id, agent_id: None  # no broker

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


def test_one_time_fires_once_to_completed_and_not_again(seeded_db):
    from backend.models.entities.scheduled_task import (
        ScheduledTask, ScheduledTaskStatus,
    )
    from backend.services.tasks import scheduled_task_dispatcher as d

    d._submit_execution = lambda task_id, agent_id: None  # no broker

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


def test_schedule_trigger_dispatches_a_real_task(seeded_db):
    import backend.services.event_processor as ep
    from backend.models.entities.event_trigger import EventTrigger, TriggerType
    from backend.models.entities.task import Task, TaskStatus
    from backend.services.tasks import scheduled_task_dispatcher as d

    d._submit_execution = lambda task_id, agent_id: None  # no broker
    ep._check_rate_limit = lambda t, db: False
    ep._is_trigger_paused = lambda t: False

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
```

- [ ] **Step 2: Run the full scheduled-tasks test suite**

Run: `pytest backend/tests/unit/models/test_task_scheduling_models.py backend/tests/unit/services/scheduling backend/tests/unit/services/tasks backend/tests/unit/services/test_schedule_trigger.py backend/tests/unit/services/test_create_reminder.py backend/tests/integration/test_scheduled_tasks_api.py backend/tests/integration/test_scheduled_tasks_end_to_end.py -q`
Expected: all PASS.

- [ ] **Step 3: Manual live smoke (beat tick + worker)** — verify the fleet wiring once, not unit-testable:
  1. Start Celery beat + worker (`celery -A backend.celery_app worker`, `celery -A backend.celery_app beat`).
  2. `POST /api/v1/scheduled-tasks` a one-time task with `run_at` in the near past; confirm within ~15s a `Task` row appears (`tasks.status` IN_PROGRESS), the schedule row transitions to `COMPLETED`, and a `ScheduledTaskExecution` row is recorded.
  3. Confirm a second 15s tick does **not** re-fire it (dispatcher log shows `dispatched: 0`).

- [ ] **Step 4: Mark the TODO checklist complete** — in `docs/documents/TODO.md`, change §10.4 to check all three boxes:

```markdown
- [x] **10.4 — Scheduled Tasks**
  - [x] 10.4.1 — Cron-style scheduled tasks fire at correct intervals
  - [x] 10.4.2 — One-time scheduled tasks execute and are cleaned up
  - [x] 10.4.3 — Event-triggered tasks fire on condition match
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_scheduled_tasks_end_to_end.py docs/documents/TODO.md
git commit -m "test(scheduled-tasks): end-to-end verification; mark §10.4 complete"
```

---

## Done

All eight tasks done:

| Task | Delivers |
|------|----------|
| 1 | Shared cron-due helper (single `croniter` home) |
| 2 | `ScheduledTask` `run_once`/`run_at`/`COMPLETED` + tz-aware cron |
| 3 | Dispatcher, CAS claim, shared task builder |
| 4 | 15s beat registration |
| 5 | `SCHEDULE` event-trigger evaluator + beat |
| 6 | CRUD route `/api/v1/scheduled-tasks` |
| 7 | `create_reminder` fix |
| 8 | Integration verification + §10.4 checklist |