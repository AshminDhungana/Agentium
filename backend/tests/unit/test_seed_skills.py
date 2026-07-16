import textwrap
from pathlib import Path

from backend.scripts.seed_skills import parse_skill_file

ROOT = Path(__file__).resolve().parents[2]  # backend/tests/unit -> backend


GOOD = textwrap.dedent(
    """
    ---
    name: demo_skill
    description: A demo skill that does a thing for testing the generic loader.
    skill_type: automation
    domain: devops
    complexity: intermediate
    tags: [bash, demo]
    creator_tier: head
    ---
    ## Overview
    Does the thing safely.
    ## Steps
    Run the command.
    Verify output.
    ## Validation
    Thing completed without error.
    """
)


def test_seed_skills_registers_markdown(tmp_path):
    skill_dir = tmp_path / "demo_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(GOOD, encoding="utf-8")

    schema = parse_skill_file(skill_dir / "SKILL.md")
    assert schema.skill_name == "demo_skill"
    assert schema.embedding_model == "BAAI/bge-base-en-v1.5"
    assert schema.verification_status == "verified"
    assert schema.success_rate == 1.0
    assert len(schema.steps) >= 1
    assert schema.constitution_compliant is True
    assert schema.skill_id == "skill_demo_skill"


def test_bash_skill_parses():
    p = ROOT / ".agentium" / "skills" / "bash" / "SKILL.md"
    schema = parse_skill_file(p)
    assert schema.skill_name == "bash"
    assert "docker" in [t.lower() for t in schema.tags]
    assert any("ShellTool" in s or "bash -lc" in s for s in schema.steps)
    joined = " ".join(schema.steps)
    assert "__SKILL_DIR__" not in joined, "loader must substitute __SKILL_DIR__ token"
    assert "/.agentium/skills/bash" in joined, "bundled script path must be resolved"
    assert schema.verification_status == "verified"
