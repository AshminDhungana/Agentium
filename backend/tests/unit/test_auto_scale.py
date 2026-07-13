"""Unit tests for auto_scale_check ceiling + cooldown (Task 11)."""

from contextlib import contextmanager

import backend.services.tasks.task_executor as te
from backend.models.entities.task import Task
from backend.models.entities.agents import Agent, HeadOfCouncil


class _FakeQuery:
    def __init__(self, model, counts, head):
        self._model = model
        self._counts = counts
        self._head = head

    def filter(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        return self

    def count(self):
        if self._model is Task:
            return self._counts["pending"]
        if self._model is Agent:
            return self._counts["live"]
        return 0

    def first(self):
        if self._model is HeadOfCouncil:
            return self._head
        return None


class _FakeDB:
    def __init__(self, counts, head):
        self._counts = counts
        self._head = head

    def query(self, model):
        return _FakeQuery(model, self._counts, self._head)


class _FakeRedis:
    def __init__(self, cooling=False):
        self.store = {}
        if cooling:
            self.store["agentium:autoscale:cooldown"] = "1"

    def get(self, key):
        return self.store.get(key)

    def set(self, key, val, ex=None):
        self.store[key] = val


def _install(monkeypatch, counts, head, redis):
    @contextmanager
    def fake_db_ctx():
        yield _FakeDB(counts, head)

    monkeypatch.setattr(te, "get_task_db", fake_db_ctx)
    monkeypatch.setattr(te, "_scale_redis", lambda: redis)
    spawned = []
    monkeypatch.setattr(
        te.ReincarnationService,
        "spawn_task_agent",
        staticmethod(lambda *a, **k: spawned.append(1)),
    )
    # AuditLog.log touches the fake DB — make it a no-op.
    monkeypatch.setattr(te.AuditLog, "log", staticmethod(lambda *a, **k: None))
    return spawned


def test_auto_scale_respects_ceiling(monkeypatch):
    # Already at the ceiling: pending is high but live >= MAX -> no spawn.
    monkeypatch.setenv("MAX_LIVE_AGENTS", "5")
    monkeypatch.setenv("AUTO_SCALE_THRESHOLD", "10")
    spawned = _install(
        monkeypatch,
        counts={"pending": 100, "live": 5},
        head=object(),
        redis=_FakeRedis(),
    )
    result = te.auto_scale_check()
    assert result["scaled"] is False
    assert len(spawned) == 0


def test_auto_scale_spawns_within_headroom(monkeypatch):
    monkeypatch.setenv("MAX_LIVE_AGENTS", "50")
    monkeypatch.setenv("AUTO_SCALE_THRESHOLD", "10")
    spawned = _install(
        monkeypatch,
        counts={"pending": 100, "live": 2},
        head=object(),
        redis=_FakeRedis(),
    )
    result = te.auto_scale_check()
    assert result["scaled"] is True
    # min(3, 50-2) == 3
    assert len(spawned) == 3


def test_auto_scale_cooldown_blocks(monkeypatch):
    monkeypatch.setenv("MAX_LIVE_AGENTS", "50")
    monkeypatch.setenv("AUTO_SCALE_THRESHOLD", "10")
    spawned = _install(
        monkeypatch,
        counts={"pending": 100, "live": 2},
        head=object(),
        redis=_FakeRedis(cooling=True),
    )
    result = te.auto_scale_check()
    assert result["scaled"] is False
    assert result["reason"] == "cooldown"
    assert len(spawned) == 0


def test_auto_scale_headroom_caps_spawn(monkeypatch):
    # 1 slot of headroom -> spawn exactly 1 even though 3 recommended.
    monkeypatch.setenv("MAX_LIVE_AGENTS", "3")
    monkeypatch.setenv("AUTO_SCALE_THRESHOLD", "10")
    spawned = _install(
        monkeypatch,
        counts={"pending": 100, "live": 2},
        head=object(),
        redis=_FakeRedis(),
    )
    result = te.auto_scale_check()
    assert result["scaled"] is True
    assert len(spawned) == 1
