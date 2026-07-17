"""Unit tests for dispatcher Task Agent recovery (issue: tasks stuck after
dispatch with 'No Task Agent available').

The dispatcher only considered a Lead's direct DB subordinates, so capable
Task Agents spawned under another parent (e.g. auto-scaled under the Head) or
freshly spawned agents were invisible. ``_ensure_task_agent`` must recover by
reusing any active Task Agent, and only spawn one if none exist.
"""

from backend.services.agent_orchestrator import AgentOrchestrator
from backend.models.entities.agents import AgentType, AgentStatus


class _FakeAgent:
    def __init__(self, agentium_id, agent_type=None, status=None, is_active=True):
        self.agentium_id = agentium_id
        self.agent_type = agent_type
        self.status = status
        self.is_active = is_active


class _FakeQuery:
    def __init__(self, model, db):
        self._model = model
        self._db = db
        self._used_filter_by = False

    def filter(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        self._used_filter_by = True
        return self

    def first(self):
        from backend.models.entities.agents import Agent

        if self._model is not Agent:  # only Agent is queried here
            return None
        # Lead lookup uses filter_by(agentium_id=..., is_active=True)
        if self._used_filter_by:
            return self._db._lead
        # Reuse lookup uses filter(...) for an active Task Agent
        return self._db._existing


class _FakeDB:
    def __init__(self, lead=None, existing=None):
        self._lead = lead
        self._existing = existing
        self.committed = False

    def query(self, model):
        return _FakeQuery(model, self)

    def commit(self):
        self.committed = True


def _make_lead(agentium_id="20001"):
    return _FakeAgent(agentium_id, agent_type=AgentType.LEAD_AGENT, status=AgentStatus.ACTIVE)


def _make_task_agent(agentium_id="30001"):
    return _FakeAgent(
        agentium_id,
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
    )


async def test_reuse_existing_active_task_agent(monkeypatch):
    """A capable Task Agent already in the system must be reused, even if it is
    not a subordinate of the dispatching Lead."""
    lead = _make_lead()
    existing = _make_task_agent("30099")
    db = _FakeDB(lead=lead, existing=existing)

    spawned = []
    monkeypatch.setattr(
        "backend.services.agent_orchestrator.CapabilityRegistry.can_agent",
        lambda agent, cap, db: True,
    )
    monkeypatch.setattr(
        "backend.services.agent_orchestrator.ReincarnationService.spawn_task_agent",
        lambda parent, name, description, db: spawned.append(parent) or _make_task_agent("30999"),
    )

    orch = AgentOrchestrator(db)
    result = await orch._ensure_task_agent("20001")

    assert result == "30099"
    assert spawned == []  # no spawn when one already exists


async def test_spawn_when_no_task_agent_exists(monkeypatch):
    """When the system has zero Task Agents, spawn one under the Lead."""
    lead = _make_lead()
    db = _FakeDB(lead=lead, existing=None)

    captured = {}

    def _spawn(parent, name, description, db):
        captured["parent"] = parent
        return _make_task_agent("30888")

    monkeypatch.setattr(
        "backend.services.agent_orchestrator.CapabilityRegistry.can_agent",
        lambda agent, cap, db: True,
    )
    monkeypatch.setattr(
        "backend.services.agent_orchestrator.ReincarnationService.spawn_task_agent",
        _spawn,
    )

    orch = AgentOrchestrator(db)
    result = await orch._ensure_task_agent("20001")

    assert result == "30888"
    assert captured["parent"] is lead
    assert db.committed is True


async def test_none_when_lead_missing():
    """No recovery possible if the Lead itself cannot be found."""
    db = _FakeDB(lead=None, existing=None)
    orch = AgentOrchestrator(db)
    assert await orch._ensure_task_agent("20001") is None
