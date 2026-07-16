import os

os.environ.setdefault("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")

from pathlib import Path

from backend.scripts.seed_skills import parse_skill_file
from backend.services.skill_manager import skill_manager
from backend.services.skill_rag import skill_rag

ROOT = Path(__file__).resolve().parents[2]  # backend/tests/integration -> backend


def _schema():
    return parse_skill_file(ROOT / ".agentium" / "skills" / "bash" / "SKILL.md")


def test_bash_skill_is_retrievable():
    from backend.models.database import SessionLocal

    db = SessionLocal()
    try:
        schema = _schema()
        skill_manager.upsert_skill_from_markdown(schema, db=db)
        db.commit()
        results = skill_manager.search_skills(
            "run pytest in the backend container", agent_tier="head", db=db, n_results=3
        )
    finally:
        db.close()
    ids = [r["skill_id"] for r in results]
    assert "skill_bash" in ids


def test_bash_skill_injected_by_rag():
    from backend.models.database import SessionLocal

    db = SessionLocal()
    try:
        schema = _schema()
        skill_manager.upsert_skill_from_markdown(schema, db=db)
        db.commit()
        results = skill_manager.search_skills(
            "how do I run the test suite safely", agent_tier="head", db=db, n_results=3
        )
        ctx = skill_rag._build_rag_context(results, "how do I run the test suite safely")
    finally:
        db.close()
    assert "bash" in ctx["context_text"].lower() or "ShellTool" in ctx["context_text"]
