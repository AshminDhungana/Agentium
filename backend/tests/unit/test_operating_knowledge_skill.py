from pathlib import Path

from backend.scripts.seed_skills import parse_skill_file

SKILLS_ROOT = Path(__file__).resolve().parents[2] / ".agentium" / "skills"


def _parse(name: str):
    return parse_skill_file(SKILLS_ROOT / name / "SKILL.md")


def test_operating_knowledge_routes_to_best_practices():
    schema = _parse("operating_knowledge")
    assert schema.skill_name == "operating_knowledge"
    assert schema.chroma_collection == "best_practices"
    # Folder skills are trusted → clear the RAG retrieval floor.
    assert schema.success_rate == 1.0
    assert schema.verification_status == "verified"


def test_operating_knowledge_answers_acceptance_prompts():
    schema = _parse("operating_knowledge")
    blob = (schema.description + " " + " ".join(schema.steps)).lower()
    # Acceptance queries from 6.2.
    assert "fetch a url" in blob or "fetch a url" in schema.description.lower()
    assert "working directory" in blob


def test_web_crawling_includes_major_sites_index():
    schema = _parse("web_crawling")
    blob = (schema.description + " " + " ".join(schema.steps)).lower()
    assert "major sites" in blob
    # The referenced dataset must exist and be non-trivial.
    dataset = SKILLS_ROOT / "web_crawling" / "datasets" / "major_sites.md"
    assert dataset.exists()
    text = dataset.read_text(encoding="utf-8")
    assert "wikipedia.org" in text
    assert "stackoverflow.com" in text
    assert "github.com" in text
