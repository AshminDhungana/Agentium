"""Generic parent-document store: untruncated full text for every ChromaDB
collection, keyed by (collection_key, parent_id).

ChromaDB holds only chunk vectors; this table holds the whole document so
parent-document retrieval can return complete context on query.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, JSON, Integer, DateTime, UniqueConstraint

from .base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_key = Column(String(64), nullable=False, index=True)
    parent_id = Column(String(128), nullable=False, index=True)
    full_text = Column(Text, nullable=False)
    doc_metadata = Column(JSON, nullable=False, default=dict)
    chunk_count = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("collection_key", "parent_id", name="uq_knowledge_doc_coll_parent"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "collection_key": self.collection_key,
            "parent_id": self.parent_id,
            "full_text": self.full_text,
            "doc_metadata": self.doc_metadata or {},
            "chunk_count": self.chunk_count,
        }
