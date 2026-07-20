import asyncio
import pytest

pytestmark = pytest.mark.integration


def test_self_signaling_task_shows_three_checkpoints(monkeypatch):
    from backend.services import knowledge_assist as ka
    from backend.models.entities.agents import Agent

    captured = []
    class SpyStore:
        def query_knowledge(self, *a, **k):
            # Non-empty context so the fallback path still records the checkpoint
            # when web search fails (spec: missing web MUST NOT block the update).
            return {"ids": [["c1"]], "documents": [["prior context"]],
                    "metadatas": [[{}]], "distances": [[0.1]]}
        def get_collection(self, key):
            return self
        def get_parent_document(self, ck, pid, db):
            return None
        def upsert_document(self, ck, pid, text, meta, db):
            captured.append((ck, meta.get("stage"), pid))
            return {"parent_id": pid}
    ka.get_vector_store = lambda: SpyStore()

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "Gap Explained", "url": "http://g", "snippet": "d"}
            ]}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "t_int"
        description = "solve the integration problem"
        def complete(self, **kw):
            pass
    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()
        def get_model_config(self, db):
            return None
        def execute_with_skill_rag(self, task, db):
            # signal a mid-task gap
            return {
                "content": "<<NEED_KNOWLEDGE>> what is the protocol?",
                "model": "m", "tokens_used": 1, "skills_used": [],
                "knowledge_needed": True, "knowledge_query": "what is the protocol?",
            }
        def submit_skill(self, **kw):
            return None

    agent = FakeAgent()
    task = FakeTask()

    # 1. received checkpoint (task intake)
    asyncio.run(ka.checkpoint_write("received", task, agent, db=None))
    # 2. execute the task; it self-signals a mid-task knowledge gap
    result = agent.execute_with_skill_rag(task, db=None)
    assert result["knowledge_needed"] is True
    # 3. mid checkpoint driven by the agent's signaled query
    asyncio.run(ka.checkpoint_write(
        "mid", task, agent, db=None, query=result["knowledge_query"]))
    # 4. completed checkpoint
    asyncio.run(ka.checkpoint_write("completed", task, agent, db=None))

    stages = [s for _, s, _ in captured]
    assert "received" in stages
    assert "completed" in stages
    assert "mid" in stages


def test_web_failure_still_records_all_checkpoints(monkeypatch):
    from backend.services import knowledge_assist as ka

    captured = []
    class SpyStore:
        def query_knowledge(self, *a, **k):
            # Non-empty context so the fallback path still records the checkpoint
            # when web search fails (spec: missing web MUST NOT block the update).
            return {"ids": [["c1"]], "documents": [["prior context"]],
                    "metadatas": [[{}]], "distances": [[0.1]]}
        def get_collection(self, key):
            return self
        def get_parent_document(self, ck, pid, db):
            return None
        def upsert_document(self, ck, pid, text, meta, db):
            captured.append((ck, meta.get("stage")))
            return {"parent_id": pid}
    ka.get_vector_store = lambda: SpyStore()

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "error", "error": "all providers failed"}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "t_int2"
        description = "another task"
    class FakeAgent:
        agentium_id = "30001"

    # call each stage directly; must not raise, must record stage
    for stage in ("received", "completed", "mid"):
        out = asyncio.run(ka.checkpoint_write(stage, FakeTask(), FakeAgent(), db=None))
        assert out.fallback_used is True

    stages = [s for _, s in captured]
    assert "received" in stages
    assert "completed" in stages
    assert "mid" in stages
