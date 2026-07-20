import asyncio
import pytest

pytestmark = pytest.mark.integration


def test_novel_task_triggers_retrieval_and_writeback(monkeypatch):
    from backend.models.entities.agents import Agent
    from backend.services import knowledge_assist as ka
    import backend.services.skill_rag as sr

    writes = []

    # ChromaDB returns nothing relevant -> force web search + write-back
    class EmptyStore:
        def query_knowledge(self, *a, **k):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        def get_collection(self, key):
            return self

        def get_parent_document(self, ck, pid, db):
            return None

        def upsert_document(self, ck, pid, text, meta, db):
            writes.append((ck, pid))
            return {"parent_id": pid}

    monkeypatch.setattr(ka, "get_vector_store", lambda: EmptyStore())

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "Novel Topic Explained", "url": "http://n", "snippet": "details"}
            ]}

    monkeypatch.setattr(ka, "web_search_tool", FakeWeb())

    # Avoid DB-backed skill search and real LLM calls.
    monkeypatch.setattr(
        sr.skill_manager,
        "search_skills",
        lambda **kw: [],
    )

    class FakeLLM:
        def __init__(self, **kw):
            pass

        async def generate(self, **kw):
            return {"content": "ok", "model": "m", "tokens_used": 1, "latency_ms": 1}

    monkeypatch.setattr("backend.services.skill_rag.LLMClient", FakeLLM)

    # Build a minimal Task + Agent without heavy infra
    class FakeTask:
        description = "explain the noveltopicium protocol in depth"
        agentium_id = "t_novel"

        def complete(self, **kw):
            pass

    from backend.services.skill_rag import skill_rag

    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()
        get_model_config = lambda self, db: None
        submit_skill = lambda self, **kw: None

        def execute_with_skill_rag(self, task, db):
            import asyncio
            return asyncio.run(skill_rag.execute_with_skills(
                task_description=task.description,
                agent=self,
                db=db,
                model_config_id=self.get_model_config(db).id if self.get_model_config(db) else None,
            ))

    agent = FakeAgent()
    res = agent.execute_with_skill_rag(FakeTask(), db=None)

    assert any(ck == "web_knowledge" for ck, _ in writes), "expected a web_knowledge write-back"
    assert res["knowledge_outcome"]["wrote_back"] is True
