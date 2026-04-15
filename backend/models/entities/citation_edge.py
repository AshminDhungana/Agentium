"""
Phase 16.3: Cross-Document Citation Edge model.

Records every citation relationship discovered during RAG retrieval.
Each row represents: "source_doc_id was cited by cited_by_doc_id
during task_id at created_at with relevance_score".

The table lives in PostgreSQL; the actual documents live in ChromaDB.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String

from backend.models.entities.base import Base


class CitationEdge(Base):
    """A directed citation edge between two ChromaDB documents."""

    __tablename__ = "citation_edges"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ChromaDB document ID that is being cited (the source of knowledge)
    source_doc_id = Column(String(255), nullable=False, index=True)

    # ChromaDB document ID (or query context ID) that cites the source
    cited_by_doc_id = Column(String(255), nullable=False, index=True)

    # The task during which this citation was recorded (nullable —
    # citations can occur outside task context, e.g. constitution checks)
    task_id = Column(
        String(36),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Which ChromaDB collection the source document belongs to
    collection_key = Column(String(64), nullable=False, default="")

    # Cosine similarity / relevance at time of retrieval
    relevance_score = Column(Float, nullable=False, default=0.0)

    # When this citation was recorded
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Composite index for efficient cleanup queries
    __table_args__ = (
        Index("ix_citation_edges_created_at", "created_at"),
        Index(
            "ix_citation_edges_source_collection",
            "source_doc_id",
            "collection_key",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "source_doc_id": self.source_doc_id,
            "cited_by_doc_id": self.cited_by_doc_id,
            "task_id": self.task_id,
            "collection_key": self.collection_key,
            "relevance_score": round(self.relevance_score, 4),
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
        }
