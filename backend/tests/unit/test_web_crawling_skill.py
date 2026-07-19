"""
Validate the web_crawling skill markdown parses through the generic loader and
meets SkillSchema constraints, and that it points back to the web_crawler tool.
"""
from pathlib import Path

from backend.scripts.seed_skills import parse_skill_file

SKILL_MD = Path(__file__).resolve().parents[2] / ".agentium" / "skills" / "web_crawling" / "SKILL.md"


def test_web_crawling_skill_file_exists():
    assert SKILL_MD.exists(), "Create backend/.agentium/skills/web_crawling/SKILL.md"


def test_web_crawling_skill_parses():
    schema = parse_skill_file(SKILL_MD)
    assert schema.skill_name == "web_crawling"
    assert schema.embedding_model == "BAAI/bge-base-en-v1.5"
    assert schema.verification_status == "verified"
    assert schema.success_rate == 1.0
    assert schema.constitution_compliant is True
    assert len(schema.steps) >= 1
    assert len(schema.validation_criteria) >= 1
    joined = " ".join(schema.steps) + " " + schema.description
    # The skill must name the tool and point at its own SKILL.md path.
    assert "web_crawler" in joined
    assert ".agentium/skills/web_crawling/SKILL.md" in joined


def test_web_crawling_skill_covers_politeness():
    schema = parse_skill_file(SKILL_MD)
    joined = " ".join(schema.steps)
    # Politeness guidance that the crawler enforces in-tool must be documented.
    assert "robots.txt" in joined
    assert "rate" in joined.lower()
    assert "depth" in joined
