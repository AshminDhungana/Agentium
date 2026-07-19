import pytest
from unittest.mock import MagicMock, patch
from backend.services import chat_service as cs
from backend.services.decision_engine import DecisionAction


@pytest.mark.asyncio
async def test_create_task_background_broadcasts_event():
    """_create_task_background opens its own DB session, creates the task, and
    broadcasts a ``task_created`` WS event with the right task_id.

    The real ``SessionLocal`` requires a live DB, so we substitute a lightweight
    fake session and patch ``create_task_from_decision`` to avoid any DB writes.
    """
    sent = {}

    class FakeManager:
        async def broadcast(self, msg):
            sent.update(msg)

    class FakeSession:
        def query(self, *args, **kwargs):
            return self

        def filter_by(self, *args, **kwargs):
            return self

        def first(self):
            return MagicMock()

        def close(self):
            return None

    class D:
        action = DecisionAction.CREATE_TASK
        task_brief = "Build a scraper"
        decision_id = "dec-1"

    async def fake_create(head, decision, prompt, db):
        return {"created": True, "task_id": "30001"}

    with patch.object(cs, "ws_manager", FakeManager()), \
         patch.object(cs, "SessionLocal", lambda: FakeSession()):
        with patch.object(cs.ChatService, "create_task_from_decision", staticmethod(fake_create)):
            await cs.ChatService._create_task_background("00001", D(), "build a scraper", "u1")
            assert sent.get("type") == "task_created"
            assert sent.get("task_id") == "30001"
            assert sent.get("action") == "create_task"
            assert sent.get("content") == "Build a scraper"
