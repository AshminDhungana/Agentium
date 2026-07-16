from unittest.mock import MagicMock, patch

import backend.services.skill_manager as sm
from backend.services.skill_manager import SkillManager


def test_create_skill_embeds_documents_with_bge(monkeypatch):
    fake_ef = MagicMock()
    fake_ef.embed_documents.return_value = [[0.1] * 768]
    import backend.core.vector_store as vs
    monkeypatch.setattr(vs, "BgeEmbeddingFunction", lambda: fake_ef)
    monkeypatch.setattr(sm, "BgeEmbeddingFunction", lambda: fake_ef)

    mgr = SkillManager()
    captured = {}
    fake_col = MagicMock()
    def _add(**kwargs):
        captured.update(kwargs)
        return None
    fake_col.add.side_effect = _add
    monkeypatch.setattr(mgr.vector_store, "get_collection", lambda name: fake_col)
    monkeypatch.setattr(mgr, "_build_and_check_document",
                        lambda skill: "chroma doc for embedding")
    # Stub the constitutional-compliance dependency (property returns a fake).
    fake_gov = MagicMock()
    fake_gov.check_constitutional_compliance.return_value = (True, [])
    monkeypatch.setattr(type(mgr), "knowledge_gov",
                        property(lambda self: fake_gov))
    fake_agent = MagicMock()
    fake_agent.agent_type.value = "head"
    fake_agent.agentium_id = "00001"
    fake_db = MagicMock()

    mgr.create_skill(
        skill_data={
            "skill_name": "test", "display_name": "Test Skill", "skill_type": "automation",
            "domain": "devops", "tags": ["bash"], "description": "x" * 60,
            "steps": ["s"], "validation_criteria": ["v"],
        },
        creator_agent=fake_agent, db=fake_db, auto_verify=True,
    )
    assert fake_ef.embed_documents.called
    # Documents (not queries) must NOT carry the bge query prefix.
    emb_text_arg = fake_ef.embed_documents.call_args[0][0]
    assert isinstance(emb_text_arg, list) and not emb_text_arg[0].startswith("Represent this sentence")
    # The stored embedding is a 768-dim vector produced by embed_documents.
    assert len(captured["embeddings"][0]) == 768


def test_search_skill_query_uses_bge_embed_query(monkeypatch):
    fake_ef = MagicMock()
    fake_ef.embed_query.return_value = [[0.2] * 768]
    import backend.core.vector_store as vs
    monkeypatch.setattr(vs, "BgeEmbeddingFunction", lambda: fake_ef)
    monkeypatch.setattr(sm, "BgeEmbeddingFunction", lambda: fake_ef)
    mgr = SkillManager()
    fake_col = MagicMock()
    fake_col.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    with patch.object(mgr.vector_store, "get_collection", return_value=fake_col):
        mgr.search_skills("run pytest in the backend", agent_tier="head", db=MagicMock())
    # Queries must go through embed_query (which internally applies the bge
    # query prefix), NOT embed_documents.
    fake_ef.embed_query.assert_called_once()
    fake_ef.embed_documents.assert_not_called()
    assert fake_ef.embed_query.call_args[0][0] == "run pytest in the backend"


def test_embedding_tool_default_is_bge(monkeypatch):
    from unittest.mock import MagicMock
    from backend.tools.embedding_tool import EmbeddingTool

    captured = {}

    class FakeST:
        def __init__(self, name):
            captured["model_name"] = name

        def encode(self, texts, convert_to_numpy=True):
            class _E:
                def tolist(self):
                    return [[0.0] * 768 for _ in texts]
            return _E()

    import sentence_transformers
    monkeypatch.setattr(
        sentence_transformers, "SentenceTransformer",
        lambda name: FakeST(name),
    )
    monkeypatch.setattr(EmbeddingTool, "_local_model", None, raising=False)
    tool = EmbeddingTool()
    import asyncio
    asyncio.run(tool._embed(["hello"], provider="local", model=None))
    # model=None must resolve to the project bge model, never the retired MiniLM.
    assert captured["model_name"] == "BAAI/bge-base-en-v1.5"
    assert "MiniLM" not in captured["model_name"]
