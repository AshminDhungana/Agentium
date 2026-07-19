"""Unit tests for the task_management tool (spec §3.7).

These tests run WITHOUT a live database by faking ``get_db_context`` with an
in-memory session that shares state across calls, so a task created in one
action is visible to the next. They exercise the real round-trip logic
(create → get → update → list → close), the task state machine, and the
per-tier authorization policy.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch
import operator as _operator

import pytest

from backend.models.entities.task import TaskPriority, TaskStatus, TaskType


# ── Fake ORM layer ───────────────────────────────────────────────────────────

class _Clause:
    def __init__(self, left, op, right):
        self.left = left
        self.operator = op
        self.right = right


class _Col:
    """Minimal SQLAlchemy-Column stand-in: supports == and .contains()."""

    def __init__(self, name):
        self.name = name

    def __get__(self, obj, owner):
        if obj is None:
            return self
        return obj.__dict__.get(self.name)

    def __eq__(self, other):
        return _Clause(self, _operator.eq, other)

    def contains(self, value):
        return _Clause(self, lambda a, b: a is not None and b in a, value)

    def desc(self):
        return self


def _norm(v):
    return v.value if hasattr(v, "value") else v


def _predicate(clause):
    attr = clause.left.name
    op = clause.operator
    val = _norm(clause.right)
    return lambda o: op(_norm(getattr(o, attr, None)), val)


class FakeTask:
    id = _Col("id")
    agentium_id = _Col("agentium_id")
    status = _Col("status")
    parent_task_id = _Col("parent_task_id")
    assigned_task_agent_ids = _Col("assigned_task_agent_ids")
    created_at = _Col("created_at")

    def __init__(self, **kw):
        self.id = kw.get("id") or f"task-{uuid.uuid4().hex[:8]}"
        self.agentium_id = kw.get("agentium_id") or f"T-{uuid.uuid4().hex[:6]}"
        self.title = kw.get("title")
        self.description = kw.get("description")
        self.priority = kw.get("priority") or TaskPriority.NORMAL
        self.task_type = kw.get("task_type") or TaskType.EXECUTION
        self.status = kw.get("status") or TaskStatus.PENDING
        self.created_by = kw.get("created_by")
        self.lead_agent_id = kw.get("lead_agent_id")
        self.assigned_task_agent_ids = kw.get("assigned_task_agent_ids") or []
        self.parent_task_id = kw.get("parent_task_id")
        self.due_date = kw.get("due_date")
        self.constitutional_basis = kw.get("constitutional_basis")
        self.completion_percentage = kw.get("completion_percentage") or 0
        self.result_summary = kw.get("result_summary")
        self.completed_at = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class FakeTaskEvent:
    def __init__(self, **kw):
        self.task_id = kw.get("task_id")
        self.event_type = kw.get("event_type")
        self.actor_id = kw.get("actor_id")
        self.actor_type = kw.get("actor_type")
        self.data = kw.get("data")


class FakeTaskEventType:
    TASK_CREATED = "task_created"


class FakeSession:
    _tasks: list = []
    _events: list = []

    def add(self, obj):
        if isinstance(obj, FakeTask):
            self._tasks.append(obj)
        else:
            self._events.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def close(self):
        pass

    def query(self, cls):
        store = self._tasks if cls is FakeTask else self._events
        return FakeQuery(store)


class FakeQuery:
    def __init__(self, store):
        self._store = store
        self._filters = []
        self._limit = None

    def filter(self, *clauses):
        for c in clauses:
            self._filters.append(_predicate(c))
        return self

    def order_by(self, *a):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self):
        return [o for o in self._store if all(f(o) for f in self._filters)]

    def first(self):
        m = self._matches()
        return m[0] if m else None

    def all(self):
        m = self._matches()
        if self._limit is not None:
            m = m[: self._limit]
        return m


@contextmanager
def _fake_get_db_context():
    sess = FakeSession()
    try:
        yield sess
        sess.commit()
    finally:
        sess.close()


@pytest.fixture(autouse=True)
def _patch_db():
    FakeSession._tasks = []
    FakeSession._events = []
    with patch("backend.models.database.get_db_context", _fake_get_db_context), \
         patch("backend.models.entities.task.Task", FakeTask), \
         patch("backend.models.entities.task_events.TaskEvent", FakeTaskEvent), \
         patch("backend.models.entities.task_events.TaskEventType", FakeTaskEventType):
        yield


# ── Round-trip ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_round_trip():
    from backend.tools.task_management_tool import task_management_tool as t

    # create (Lead)
    created = await t.execute(
        "create",
        agent_id="20001",
        description="Write the migration",
        title="Migration",
        assigned_to=["30001"],
        priority="high",
    )
    assert created["status"] == "success", created
    tid = created["task"]["id"]
    assert created["task"]["status"] == "pending"
    assert created["task"]["created_by"] == "20001"
    assert created["task"]["assigned_task_agent_ids"] == ["30001"]

    # get
    got = await t.execute("get", task_id=tid)
    assert got["status"] == "success"
    assert got["task"]["id"] == tid

    # update status by the assigned Task agent (legal path: pending -> approved -> in_progress)
    upd1 = await t.execute("update", agent_id="30001", task_id=tid, status="approved")
    assert upd1["status"] == "success", upd1
    upd = await t.execute("update", agent_id="30001", task_id=tid, status="in_progress")
    assert upd["status"] == "success", upd
    assert upd["task"]["status"] == "in_progress"

    # list filtered by status
    listed = await t.execute("list", status="in_progress")
    assert listed["status"] == "success"
    assert any(x["id"] == tid for x in listed["tasks"])

    # close (Lead)
    closed = await t.execute("close", agent_id="20001", task_id=tid, outcome="completed")
    assert closed["status"] == "success", closed
    assert closed["task"]["status"] == "completed"

    # final get
    final = await t.execute("get", task_id=tid)
    assert final["task"]["status"] == "completed"


# ── Tier enforcement ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_agent_cannot_create():
    from backend.tools.task_management_tool import task_management_tool as t
    res = await t.execute("create", agent_id="30001", description="x")
    assert res["status"] == "error"
    assert "Lead" in res["error"]


@pytest.mark.asyncio
async def test_task_agent_cannot_close():
    from backend.tools.task_management_tool import task_management_tool as t
    created = await t.execute("create", agent_id="20001", description="x", assigned_to=["30001"])
    tid = created["task"]["id"]
    res = await t.execute("close", agent_id="30001", task_id=tid)
    assert res["status"] == "error"
    assert "Lead" in res["error"]


@pytest.mark.asyncio
async def test_task_agent_cannot_edit_unassigned_task():
    from backend.tools.task_management_tool import task_management_tool as t
    created = await t.execute("create", agent_id="20001", description="x", assigned_to=["39999"])
    tid = created["task"]["id"]
    res = await t.execute("update", agent_id="30001", task_id=tid, status="in_progress")
    assert res["status"] == "error"
    assert "assigned" in res["error"].lower()


@pytest.mark.asyncio
async def test_task_agent_cannot_update_non_status_field():
    from backend.tools.task_management_tool import task_management_tool as t
    created = await t.execute("create", agent_id="20001", description="x", assigned_to=["30001"])
    tid = created["task"]["id"]
    res = await t.execute("update", agent_id="30001", task_id=tid, title="hacked")
    assert res["status"] == "error"
    assert "status" in res["error"].lower()


@pytest.mark.asyncio
async def test_invalid_state_transition_rejected():
    from backend.tools.task_management_tool import task_management_tool as t
    created = await t.execute("create", agent_id="20001", description="x", assigned_to=["30001"])
    tid = created["task"]["id"]
    # PENDING -> COMPLETED is illegal in the state machine
    res = await t.execute("update", agent_id="30001", task_id=tid, status="completed")
    assert res["status"] == "error"
    assert "Illegal" in res["error"] or "transition" in res["error"].lower()


@pytest.mark.asyncio
async def test_help_action():
    from backend.tools.task_management_tool import task_management_tool as t
    res = await t.execute("help")
    assert res["status"] == "success"
    assert "create" in res["actions"]
