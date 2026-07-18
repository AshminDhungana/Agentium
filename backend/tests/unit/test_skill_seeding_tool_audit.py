# backend/tests/unit/test_skill_seeding_tool_audit.py
from pathlib import Path
from backend.scripts.seed_skills import parse_skill_file


def test_three_skills_parse():
    base = Path(__file__).resolve().parents[2] / ".agentium" / "skills"
    for name in ["web_fetch", "code_execution", "tool_search"]:
        p = base / name / "SKILL.md"
        assert p.exists(), f"missing {p}"
        schema = parse_skill_file(p)
        assert schema.skill_name == name
        assert 50 <= len(schema.description) <= 300
        assert schema.skill_type in {
            "code_generation", "analysis", "integration", "automation",
            "research", "design", "testing", "deployment", "debugging",
            "optimization", "documentation",
        }
        assert schema.domain in {
            "frontend", "backend", "devops", "data", "ai", "security",
            "mobile", "desktop", "general", "database", "api",
        }
