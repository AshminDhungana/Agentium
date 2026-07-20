import asyncio

def test_execute_with_skills_includes_retrieved_knowledge(monkeypatch):
    from backend.services.skill_rag import SkillRAG

    captured = {}
    class FakeOutcome:
        query = "do the thing"
        wrote_back = True
        fallback_used = False
        context_text = "Web search results for: do the thing\n1. T (http://a)\n   snip A"
        chroma_results = {}
        web_results = {}
    async def fake_retrieve(query, agent, db, **kw):
        captured["query"] = query
        return FakeOutcome()
    monkeypatch.setattr(
        "backend.services.knowledge_assist.retrieve_or_search", fake_retrieve
    )

    # minimal fakes for skill search + llm
    rag = SkillRAG()
    monkeypatch.setattr(rag.skill_manager, "search_skills",
                        lambda **kw: [])
    monkeypatch.setattr(rag, "_build_rag_context",
                        lambda skills, td: {"augmented_prompt": "PROMPT", "skills_used": [], "context_text": ""})

    class FakeLLM:
        async def generate(self, **kw):
            captured["user_message"] = kw.get("user_message")
            return {"content": "ok", "model": "m", "tokens_used": 1, "latency_ms": 1}
    import backend.services.skill_rag as sr
    monkeypatch.setattr(sr, "LLMClient", lambda **kw: FakeLLM())

    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()

    res = asyncio.run(rag.execute_with_skills("do the thing", FakeAgent(), db=None))
    assert "RETRIEVED KNOWLEDGE" in captured["user_message"]
    assert res["knowledge_outcome"]["wrote_back"] is True
