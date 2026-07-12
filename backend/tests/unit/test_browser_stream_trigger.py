# backend/tests/unit/test_browser_stream_trigger.py
from unittest.mock import AsyncMock, patch

from backend.models.entities.task import TaskType
from backend.api.routes import tasks as tasks_route


class _FakeTask:
    """Minimal stand-in for a Task ORM row.

    The real ``execute_task`` calls ``task.set_status(...)`` and returns
    ``_serialize(task)``, which reads many attributes. We implement the few
    that matter and fall back to ``None`` for the rest so the real code path
    runs end-to-end under test.
    """

    def __init__(self, task_type, description="", execution_context="",
                 agentium_id="task-123", status=None):
        self.id = agentium_id
        self.agentium_id = agentium_id
        self.task_type = task_type
        self.description = description
        self.execution_context = execution_context
        self.assigned_task_agent_ids = []
        self.status = status
        self.events = []

    def set_status(self, *a, **k):
        # no-op: real Task.set_status validates state transitions
        pass

    def __getattr__(self, name):
        # safe default for _serialize()'s many attribute reads
        return None


def test_resolve_url_from_description():
    t = _FakeTask(TaskType.BROWSER, description="please open https://example.com now")
    assert tasks_route._resolve_browser_url(t) == "https://example.com"


def test_resolve_url_from_execution_context_json():
    t = _FakeTask(TaskType.BROWSER, execution_context='{"url": "https://ctx.test/x"}')
    assert tasks_route._resolve_browser_url(t) == "https://ctx.test/x"


def test_resolve_url_none_when_absent():
    t = _FakeTask(TaskType.BROWSER, description="no link here")
    assert tasks_route._resolve_browser_url(t) is None


def test_execute_task_starts_stream_for_browser_task():
    t = _FakeTask(TaskType.BROWSER, description="go to https://example.com")

    class _FakeDB:
        def query(self, *a, **k):
            class _Q:
                def filter(self, *a, **k):
                    return self

                def first(self):
                    return t
            return _Q()

        def commit(self):
            pass

        def refresh(self, *a, **k):
            pass

    with patch.object(tasks_route, "get_browser_service") as gbs:
        svc = gbs.return_value
        svc.start_stream = AsyncMock()
        import asyncio
        asyncio.run(
            tasks_route.execute_task(
                task_id=t.id, agent_id="a1", current_user={"id": "u"}, db=_FakeDB()
            )
        )
    svc.start_stream.assert_awaited_once()
    args, kwargs = svc.start_stream.call_args
    assert kwargs["task_id"] == t.agentium_id
    assert kwargs["url"] == "https://example.com"
