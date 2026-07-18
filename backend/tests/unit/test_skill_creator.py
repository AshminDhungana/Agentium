"""Validate the skill_creator tool end-to-end: write, parse, and retrieve."""

from pathlib import Path

from backend.models.database import get_db_context
from backend.scripts.seed_skills import parse_skill_file
from backend.services.skill_manager import skill_manager
from backend.tools.skill_creator_tool import skill_creator_tool, SKILLS_ROOT

SKILL_TYPES = ["automation", "analysis", "research", "debugging", "testing",
               "deployment", "design", "code_generation", "integration",
               "optimization", "documentation"]
DOMAINS = ["backend", "frontend", "devops", "data", "ai", "security", "mobile",
           "desktop", "general", "database", "api"]


def _valid_payload(**overrides):
    p = dict(
        action="create",
        skill_name="demo_skill_xyz",
        display_name="Demo Skill XYZ",
        description="A demo skill used by the skill_creator unit test to verify end to end.",
        skill_type="automation",
        domain="devops",
        complexity="intermediate",
        tags=["demo", "test"],
        steps=["Run the thing.", "Verify the thing."],
        validation_criteria=["Thing completed without error."],
        agent_id="00001",
    )
    p.update(overrides)
    return p


def test_unauthorized_tier_rejected():
    res = skill_creator_tool.execute(**_valid_payload(agent_id="30001"))
    assert res["success"] is False
    assert "restricted" in res["error"].lower()


def test_invalid_description_rejected():
    res = skill_creator_tool.execute(**_valid_payload(description="too short"))
    assert res["success"] is False


def test_invalid_enum_rejected():
    res = skill_creator_tool.execute(**_valid_payload(skill_type="not_a_type"))
    assert res["success"] is False


def test_valid_create_writes_and_parses():
    res = skill_creator_tool.execute(**_valid_payload())
    try:
        assert res["success"] is True, res
        md = SKILLS_ROOT / "demo_skill_xyz" / "SKILL.md"
        assert md.exists(), "SKILL.md should be written"
        schema = parse_skill_file(md)
        assert schema.skill_name == "demo_skill_xyz"
        assert 50 <= len(schema.description) <= 300
        assert len(schema.steps) >= 1
        assert len(schema.validation_criteria) >= 1
        assert schema.constitution_compliant is True
        assert schema.success_rate == 1.0
    finally:
        # Clean up the on-disk skill dir written during the test.
        import shutil
        d = SKILLS_ROOT / "demo_skill_xyz"
        if d.exists():
            shutil.rmtree(d)


def test_created_skill_is_retrievable():
    res = skill_creator_tool.execute(**_valid_payload())
    try:
        assert res["success"] is True, res
        with get_db_context() as db:
            hits = skill_manager.search_skills(
                query="demo skill verify end to end",
                agent_tier="head",
                db=db,
                n_results=5,
            )
        ids = [h["skill_id"] for h in hits]
        assert "skill_demo_skill_xyz" in ids, ids
    finally:
        import shutil
        d = SKILLS_ROOT / "demo_skill_xyz"
        if d.exists():
            shutil.rmtree(d)
