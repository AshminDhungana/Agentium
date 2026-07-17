"""
Skill entity for ChromaDB and PostgreSQL dual-storage.
Defines the standardized skill schema.

Embedding / ChromaDB size contract
────────────────────────────────────
BAAI/bge-base-en-v1.5 silently truncates input beyond 512 tokens, and the
prior ``to_chroma_document()`` hard-clipped the assembled string to
``CHROMA_CHAR_LIMIT`` — losing skill content.  That clip has been removed.
The ``VectorStore`` now stores the full skill text in PostgreSQL and chunks
it into ChromaDB for retrieval, so untruncated skills are served back at
query time.  ``CHROMA_CHAR_LIMIT`` is retained only for preview sizing.

"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, String, DateTime, JSON, Float, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.models.entities.base import Base, BaseEntity

# ---------------------------------------------------------------------------
# Preview size guard
# BAAI/bge-base-en-v1.5 → 512 tokens ≈ 2 000 characters (conservative estimate)
# No longer used to clip stored documents; retained for preview sizing only.
# ---------------------------------------------------------------------------
CHROMA_CHAR_LIMIT: int = 2_000


class SkillSchema(BaseModel):
    """
    Pydantic schema for skill validation — used for ALL skills stored in
    ChromaDB.  Ensures a consistent format across agent-created and
    Council-created skills.
    """

    # Identity
    # Fix 14 — previous pattern r"skill_[0-6]xxxx_\d{3}" matched only the
    # literal string "skill_0xxxx_001" etc. (xxxx is not a regex quantifier).
    # New pattern accepts the slug format that skill_manager generates.
    skill_id: str = Field(..., pattern=r"skill_[a-z0-9_-]{3,64}")

    skill_name: str = Field(..., min_length=3, max_length=100)
    display_name: str = Field(..., min_length=5, max_length=200)

    # Categorization
    skill_type: str = Field(..., enum=[
        "code_generation", "analysis", "integration",
        "automation", "research", "design", "testing", "deployment",
        "debugging", "optimization", "documentation",
    ])
    domain: str = Field(..., enum=[
        "frontend", "backend", "devops", "data", "ai",
        "security", "mobile", "desktop", "general", "database", "api",
    ])
    tags: List[str] = Field(..., min_items=1, max_items=10)
    complexity: str = Field(..., enum=["beginner", "intermediate", "advanced"])

    # Content
    # max_length=300 matches SKILL_CREATION_TEMPLATE instruction and keeps the
    # description — the primary semantic search surface — safely within the
    # CHROMA_CHAR_LIMIT budget even when steps and other fields are present.
    description: str = Field(..., min_length=50, max_length=300)
    prerequisites: List[str] = Field(default_factory=list)
    steps: List[str] = Field(..., min_items=1)
    code_template: Optional[str] = None
    examples: List[Dict[str, str]] = Field(default_factory=list)
    common_pitfalls: List[str] = Field(default_factory=list)
    validation_criteria: List[str] = Field(..., min_items=1)

    # Provenance
    version: str = Field(default="1.0.0", pattern=r"\d+\.\d+\.\d+")
    created_at: datetime
    updated_at: datetime
    creator_tier: str = Field(..., enum=["head", "council", "lead", "task"])
    # Fix 14 — previous pattern r"[0-6]xxxx" matched only literal "0xxxx"…
    # "6xxxx".  Agentium IDs are zero-padded numerics like "00001", "10023".
    creator_id: str = Field(..., pattern=r"[a-z0-9]{4,20}")
    parent_skill_id: Optional[str] = None
    task_origin: Optional[str] = None

    # Quality Metrics
    success_rate: float = Field(..., ge=0.0, le=1.0)
    usage_count: int = Field(default=0, ge=0)
    retrieval_count: int = Field(default=0, ge=0)
    last_retrieved: Optional[datetime] = None

    # Governance
    constitution_compliant: bool
    verification_status: str = Field(
        ..., enum=["pending", "verified", "rejected"]
    )
    verified_by: Optional[str] = None
    rejection_reason: Optional[str] = None

    # ChromaDB tracking
    chroma_collection: str = Field(default="agent_skills")
    embedding_model: str = Field(
        default="BAAI/bge-base-en-v1.5"
    )

    @field_validator("tags")
    def validate_tags(cls, v: List[str]) -> List[str]:
        return [tag.lower().strip() for tag in v]

    @field_validator("skill_name")
    def validate_skill_name(cls, v: str) -> str:
        return v.lower().replace(" ", "_").replace("-", "_")

    # ------------------------------------------------------------------
    # ChromaDB document assembly
    # ------------------------------------------------------------------

    def to_chroma_document(self) -> str:
        """
        Convert skill to a flat text string for embedding.

        The full (untruncated) document is returned.  Chunking and parent
        document storage in the ``VectorStore`` keep long skills complete:
        chunk vectors drive retrieval while the untruncated text is served
        back at query time, so no information is lost to the embedding
        window limit.  ``CHROMA_CHAR_LIMIT`` is retained only for previews.
        """
        identity = (
            f"Skill: {self.display_name} | "
            f"Name: {self.skill_name} | "
            f"Type: {self.skill_type} | "
            f"Domain: {self.domain} | "
            f"Complexity: {self.complexity} | "
            f"Tags: {', '.join(self.tags)}"
        )
        description_section = f"Description: {self.description}"
        steps_section = "Steps:\n" + "\n".join(
            f"{i + 1}. {step}" for i, step in enumerate(self.steps)
        )
        criteria_section = "Validation Criteria:\n" + "\n".join(
            f"- {c}" for c in self.validation_criteria
        )
        prereq_section = (
            "Prerequisites:\n" + "\n".join(f"- {p}" for p in self.prerequisites)
            if self.prerequisites else ""
        )
        pitfalls_section = (
            "Common Pitfalls:\n" + "\n".join(f"- {p}" for p in self.common_pitfalls)
            if self.common_pitfalls else ""
        )
        code_section = (
            f"Code Template:\n{self.code_template}"
            if self.code_template else ""
        )
        if self.examples:
            example_lines = "\n\n".join(
                f"Example {i + 1}:\nInput: {ex.get('input', 'N/A')}\n"
                f"Output: {ex.get('output', 'N/A')}"
                for i, ex in enumerate(self.examples)
            )
            examples_section = f"Examples:\n{example_lines}"
        else:
            examples_section = ""

        footer = (
            f"Success Rate: {self.success_rate:.2%} | "
            f"Creator: {self.creator_tier} agent {self.creator_id} | "
            f"Version: {self.version}"
        )

        parts = [
            identity,
            description_section,
            steps_section,
            criteria_section,
            prereq_section,
            pitfalls_section,
            code_section,
            examples_section,
            footer,
        ]
        document = "\n\n".join(p for p in parts if p)

        return document

    def to_chroma_metadata(self) -> Dict[str, Any]:
        """Convert to ChromaDB metadata (must be JSON serializable)."""
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "display_name": self.display_name,
            "skill_type": self.skill_type,
            "domain": self.domain,
            "tags": self.tags,
            "complexity": self.complexity,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "creator_tier": self.creator_tier,
            "creator_id": self.creator_id,
            "parent_skill_id": self.parent_skill_id,
            "success_rate": self.success_rate,
            "usage_count": self.usage_count,
            "constitution_compliant": self.constitution_compliant,
            "verification_status": self.verification_status,
            "verified_by": self.verified_by,
            "chroma_collection": self.chroma_collection,
        }


class SkillDB(BaseEntity):
    """
    SQLAlchemy model for skill metadata in PostgreSQL.
    References ChromaDB for the full embedded content.
    """
    __tablename__ = "skills"
    # Explicit UniqueConstraint ensures SQLAlchemy renders UNIQUE (skill_id)
    # inside the CREATE TABLE body rather than as a separate post-DDL index.
    # PostgreSQL validates the self-referential FK at CREATE TABLE time, so
    # the unique constraint must be present inline -- not in a later statement.
    __table_args__ = (UniqueConstraint("skill_id", name="uq_skills_skill_id"),)

    skill_id = Column(String(50), unique=True, nullable=False, index=True)
    skill_name = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    # Fix 11 — description cached here so to_dict() / popular-skills endpoint
    # can return it without an extra ChromaDB round-trip.
    description = Column(String(300), nullable=True)
    skill_type = Column(String(50), nullable=False)
    domain = Column(String(50), nullable=False)
    tags = Column(JSON, default=list)
    complexity = Column(String(20), nullable=False)

    # ChromaDB reference
    chroma_id = Column(String(100), nullable=False)
    chroma_collection = Column(String(50), default="agent_skills")
    embedding_model = Column(
        String(100), default="BAAI/bge-base-en-v1.5"
    )

    # Provenance
    creator_tier = Column(String(20), nullable=False)
    creator_id = Column(String(20), nullable=False)
    parent_skill_id = Column(
        String(50), ForeignKey("skills.skill_id"), nullable=True
    )
    task_origin = Column(
        String(50), ForeignKey("tasks.agentium_id"), nullable=True
    )

    # Quality metrics
    success_rate = Column(Float, default=0.0)
    usage_count = Column(Integer, default=0)
    retrieval_count = Column(Integer, default=0)
    last_retrieved = Column(DateTime, nullable=True)

    # Governance
    constitution_compliant = Column(Boolean, default=False)
    verification_status = Column(String(20), default="pending")
    verified_by = Column(String(20), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String(500), nullable=True)

    # Self-referential relationship for derived skills.
    # Fix 15 — remote_side=[skill_id] used the bare Column descriptor which is
    # ambiguous at class-definition time and can confuse SQLAlchemy's join
    # resolver.  String-based primaryjoin/remote_side plus an explicit
    # foreign_keys list is the safe, unambiguous form recommended by SA docs
    # for self-referential non-PK foreign keys.
    parent_skill = relationship(
        "SkillDB",
        foreign_keys="[SkillDB.parent_skill_id]",
        primaryjoin="SkillDB.parent_skill_id == SkillDB.skill_id",
        remote_side="SkillDB.skill_id",
        backref="derived_skills",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "display_name": self.display_name,
            # Fix 11 — description now included; previously always undefined
            # in the frontend because to_dict() omitted it.
            "description": self.description or "",
            "skill_type": self.skill_type,
            "domain": self.domain,
            "tags": self.tags or [],
            "complexity": self.complexity,
            "chroma_id": self.chroma_id,
            "creator_tier": self.creator_tier,
            "creator_id": self.creator_id,
            "success_rate": self.success_rate,
            "usage_count": self.usage_count,
            "verification_status": self.verification_status,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
        }


class SkillSubmission(BaseEntity):
    """
    Pending skill submissions awaiting Council review.
    """
    __tablename__ = "skill_submissions"

    submission_id = Column(String(50), unique=True, nullable=False)
    skill_id = Column(
        String(50), ForeignKey("skills.skill_id"), nullable=False
    )
    submitted_by = Column(String(20), nullable=False)
    # Fix — datetime.utcnow deprecated in Python 3.12+
    submitted_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Review status
    status = Column(String(20), default="pending")
    council_vote_id = Column(String(50), nullable=True)
    reviewed_by = Column(String(20), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(String(1000), nullable=True)

    # Skill data snapshot for reviewers
    skill_data = Column(JSON, nullable=False)