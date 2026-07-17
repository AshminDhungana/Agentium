"""
Validate the vector_db skill markdown parses through the generic loader and
meets SkillSchema constraints.

Run inside the backend container:
    docker compose exec -T backend bash -lc \
        "cd /app/backend && pytest tests/unit/test_vector_db_skill.py -o addopts='' -q"
"""
from pathlib import Path

from backend.scripts.seed_skills import parse_skill_file

SKILL_MD = Path(__file__).resolve().parents[2] / ".agentium" / "skills" / "vector_db" / "SKILL.md"


def test_vector_db_skill_file_exists():
    assert SKILL_MD.exists(), "Create backend/.agentium/skills/vector_db/SKILL.md"


def test_vector_db_skill_parses():
    schema = parse_skill_file(SKILL_MD)
    assert schema.skill_name == "vector_db"
    assert schema.embedding_model == "BAAI/bge-base-en-v1.5"
    assert schema.verification_status == "verified"
    assert schema.success_rate == 1.0
    assert schema.constitution_compliant is True
    assert len(schema.steps) >= 1
    assert len(schema.validation_criteria) >= 1
    # The skill must tell agents where the tool reference lives.
    joined = " ".join(schema.steps) + " " + schema.description
    assert ".agentium/skills/vector_db/SKILL.md" in joined


def test_vector_db_skill_lists_writable_collections():
    schema = parse_skill_file(SKILL_MD)
    joined = " ".join(schema.steps)
    # Protected collections must be documented as read-only / immutable.
    assert "constitution" in joined
    assert "not writable" in joined or "immutable" in joined
    # At least one writable collection named.
    assert "task_patterns" in joined or "best_practices" in joined
