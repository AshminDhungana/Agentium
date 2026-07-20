import asyncio


def test_add_routes_through_write_knowledge(monkeypatch):
    from backend.tools.vector_db_tool import VectorDBTool

    captured = {}

    async def fake_write(parent_id, text, metadata, db, collection_key="web_knowledge"):
        captured["collection_key"] = collection_key
        captured["parent_id"] = parent_id
        captured["metadata"] = metadata
        return {"parent_id": parent_id}

    import backend.services.knowledge_assist as ka

    monkeypatch.setattr(ka, "write_knowledge", fake_write)

    tool = VectorDBTool()
    res = tool._add("web_knowledge", ["some fact"], [{"type": "agent_learning"}], None)
    assert res["success"] is True
    assert captured["collection_key"] == "web_knowledge"
    # schema field present
    assert "revision_id" in captured["metadata"]
    assert captured["metadata"]["source"] == "agent"
