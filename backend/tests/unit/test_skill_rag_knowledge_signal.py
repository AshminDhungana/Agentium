import asyncio


def test_execute_with_skills_signals_knowledge_needed(monkeypatch):
    from backend.services.skill_rag import SkillRAG

    captured = {}
    class FakeOutcome:
        query = "do the thing"
        wrote_back = False
        fallback_used = False
        context_text = ""
        chroma_results = {}
        web_results = {}

    async def fake_retrieve(query, agent, db, **kw):
        return FakeOutcome()
    monkeypatch.setattr(
        "backend.services.knowledge_assist.retrieve_or_search", fake_retrieve
    )

    rag = SkillRAG()
    monkeypatch.setattr(rag.skill_manager, "search_skills", lambda **kw: [])

    def fake_build(skills, td):
        return {"augmented_prompt": "PROMPT", "skills_used": [], "context_text": ""}
    monkeypatch.setattr(rag, "_build_rag_context", fake_build)

    class FakeLLM:
        async def generate(self, **kw):
            captured["user_message"] = kw.get("user_message")
            # emit the self-signal marker with a specific gap query
            return {
                "content": "<<NEED_KNOWLEDGE>> what is the frobnicate protocol?",
                "model": "m", "tokens_used": 1, "latency_ms": 1,
            }
    import backend.services.skill_rag as sr
    monkeypatch.setattr(sr, "LLMClient", lambda **kw: FakeLLM())

    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()

    res = asyncio.run(rag.execute_with_skills("do the thing", FakeAgent(), db=None))
    assert res["knowledge_needed"] is True
    assert res["knowledge_query"] == "what is the frobnicate protocol?"


def test_execute_with_skills_no_signal_when_absent(monkeypatch):
    from backend.services.skill_rag import SkillRAG

    class FakeOutcome:
        query = "do the thing"
        wrote_back = False
        fallback_used = False
        context_text = ""
        chroma_results = {}
        web_results = {}
    async def fake_retrieve(query, agent, db, **kw):
        return FakeOutcome()
    monkeypatch.setattr(
        "backend.services.knowledge_assist.retrieve_or_search", fake_retrieve
    )

    rag = SkillRAG()
    monkeypatch.setattr(rag.skill_manager, "search_skills", lambda **kw: [])

    def fake_build(skills, td):
        return {"augmented_prompt": "PROMPT", "skills_used": [], "context_text": ""}
    monkeypatch.setattr(rag, "_build_rag_context", fake_build)

    class FakeLLM:
        async def generate(self, **kw):
            return {"content": "all good, no gaps", "model": "m",
                    "tokens_used": 1, "latency_ms": 1}
    import backend.services.skill_rag as sr
    monkeypatch.setattr(sr, "LLMClient", lambda **kw: FakeLLM())

    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()

    res = asyncio.run(rag.execute_with_skills("do the thing", FakeAgent(), db=None))
    assert res["knowledge_needed"] is False
    assert res["knowledge_query"] is None
