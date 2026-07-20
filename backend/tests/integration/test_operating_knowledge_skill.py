"""Integration tests for 6.2 — foundational operating knowledge retrievable via RAG.
"""
import pytest
from pathlib import Path
from sqlalchemy.orm import Session

from backend.core.vector_store import get_vector_store
from backend.services.skill_manager import skill_manager
from backend.scripts.seed_skills import parse_skill_file

pytestmark = pytest.mark.integration

SKILLS_ROOT = Path(__file__).resolve().parents[2] / ".agentium" / "skills"


def _seed_operating_knowledge(db: Session):
    schema = parse_skill_file(SKILLS_ROOT / "operating_knowledge" / "SKILL.md")
    skill_manager.upsert_skill_from_markdown(schema, db=db)
    db.commit()
    return schema


def test_operating_knowledge_searchable_via_rag(db_session: Session):
    """6.2 acceptance: knowledge retrievable via search_skills/RAG for the
    representative prompts 'how do I fetch a URL' and 'what's my working directory'."""
    _seed_operating_knowledge(db_session)
    get_vector_store().initialize()

    for query in ("how do I fetch a URL", "what's my working directory"):
        results = skill_manager.search_skills(query, "task", db_session)
        ids = [r["skill_id"] for r in results]
        assert "skill_operating_knowledge" in ids, (
            f"'{query}' should retrieve operating_knowledge, got {ids}"
        )
