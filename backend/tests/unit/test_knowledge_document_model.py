from backend.models.entities.knowledge_document import KnowledgeDocument


def test_table_and_columns():
    assert KnowledgeDocument.__tablename__ == "knowledge_documents"
    cols = set(KnowledgeDocument.__table__.columns.keys())
    assert {"id", "collection_key", "parent_id", "full_text",
            "doc_metadata", "chunk_count", "created_at", "updated_at"} <= cols


def test_unique_constraint_present():
    uniques = [
        c for c in KnowledgeDocument.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    cols = {tuple(sorted(col.name for col in u.columns)) for u in uniques}
    assert ("collection_key", "parent_id") in cols
