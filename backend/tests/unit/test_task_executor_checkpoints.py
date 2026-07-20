import asyncio


def test_executor_fires_received_and_completed_checkpoints(monkeypatch):
    import backend.services.tasks.task_executor as te

    calls = []
    async def fake_checkpoint(stage, task, agent, db, *, query=None):
        calls.append((stage, query))
        return type("O", (), {"stage": stage, "parent_id": "p"})()
    monkeypatch.setattr(te, "checkpoint_write", fake_checkpoint)

    class FakeTask:
        agentium_id = "t1"
        description = "do thing"
        def complete(self, **kw):
            FakeTask.completed = True
    class FakeAgent:
        agentium_id = "30001"
        def get_model_config(self, db):
            return None
        def execute_with_skill_rag(self, task, db):
            return {"content": "out", "model": "m", "tokens_used": 1,
                    "skills_used": [], "knowledge_needed": False,
                    "knowledge_query": None}
        def submit_skill(self, **kw):
            return None

    class FakeDB:
        def query(self, *a, **k):
            model = a[0] if a else None
            class Q:
                def filter_by(self, **k):
                    return self
                def first(self):
                    if model is not None and model.__name__ == "Agent":
                        return FakeAgent()
                    return FakeTask()
            return Q()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(te, "get_task_db", lambda: FakeDB())

    te.execute_task_async("t1", "30001")

    stages = [s for s, _ in calls]
    assert "received" in stages
    assert "completed" in stages
    assert "mid" not in stages  # no self-signal -> no mid checkpoint
