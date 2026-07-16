from datetime import datetime, timezone

from backend.models.entities.skill import SkillSchema, CHROMA_CHAR_LIMIT


def _base_skill(**overrides) -> SkillSchema:
    data = dict(
        skill_id="skill_test_001",
        skill_name="test_skill",
        display_name="Test Skill",
        skill_type="automation",
        domain="devops",
        tags=["bash"],
        complexity="intermediate",
        description="A test skill used to verify the default embedding model is bge-base.",
        steps=["Do the thing"],
        validation_criteria=["Thing was done"],
        creator_tier="head",
        creator_id="00001",
        constitution_compliant=True,
        verification_status="verified",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        success_rate=1.0,
    )
    data.update(overrides)
    return SkillSchema(**data)


def test_skill_default_embedding_model_is_bge():
    assert _base_skill().embedding_model == "BAAI/bge-base-en-v1.5"


def test_chroma_char_limit_is_2000():
    assert CHROMA_CHAR_LIMIT == 2000


def test_to_chroma_document_truncates_at_2000():
    long_steps = [f"step {i} " * 50 for i in range(100)]
    doc = _base_skill(steps=long_steps).to_chroma_document()
    assert len(doc) <= 2000
