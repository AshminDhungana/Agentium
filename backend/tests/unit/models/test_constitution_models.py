"""
Unit tests for Constitution and Ethos models.
Tests articles, amendments, ethos records, and constitutional versioning.
"""
import pytest
import json
from datetime import datetime, timezone

try:
    from backend.models.entities.constitution import (
        Constitution, Ethos, DocumentType
    )
except ImportError:
    from models.entities.constitution import (
        Constitution, Ethos, DocumentType
    )


class TestConstitution:
    """Tests for Constitution model."""

    def test_constitution_creation_with_all_fields(self, db_session):
        """Constitution creates with all required fields."""
        constitution = Constitution(
            agentium_id="C00001",
            version="v1.0.0",
            version_number=1,
            preamble="Supreme law of Agentium",
            articles=json.dumps({
                "article_1": {"title": "Sovereignty", "content": "The Constitution is supreme"},
                "article_2": {"title": "Agents", "content": "Agents serve the Constitution"},
            }),
            prohibited_actions=json.dumps(["unauthorized_tool_use", "constitution_modification"]),
            sovereign_preferences=json.dumps({"theme": "dark", "notifications": True}),
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()
        db_session.refresh(constitution)

        assert constitution.version == "v1.0.0"
        assert constitution.version_number == 1
        assert constitution.preamble == "Supreme law of Agentium"
        assert len(constitution.get_articles_dict()) == 2
        assert constitution.get_prohibited_actions_list() == ["unauthorized_tool_use", "constitution_modification"]
        assert constitution.get_sovereign_preferences() == {"theme": "dark", "notifications": True}
        assert constitution.created_by_agentium_id == "00001"
        assert constitution.is_active is True
        assert constitution.document_type == DocumentType.CONSTITUTION

    def test_constitution_defaults(self, db_session):
        """Constitution defaults are correct."""
        constitution = Constitution(
            agentium_id="C00002",
            version="v2.0.0",
            version_number=2,
            articles=json.dumps({}),
            prohibited_actions=json.dumps([]),
            sovereign_preferences=json.dumps({}),
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()

        assert constitution.is_active is True
        assert constitution.effective_date is not None
        assert constitution.preamble is None
        assert constitution.changelog is None
        assert constitution.amendment_of is None
        assert constitution.replaces_version_id is None

    def test_constitution_version_uniqueness(self, db_session):
        """Constitution version must be unique."""
        c1 = Constitution(agentium_id="C00001", version="v1.0.0", version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")
        c2 = Constitution(agentium_id="C00001-dup", version="v1.0.0", version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")
        db_session.add(c1)
        db_session.commit()

        db_session.add(c2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_constitution_version_number_uniqueness(self, db_session):
        """Constitution version_number must be unique."""
        c1 = Constitution(agentium_id="C00001", version="v1.0.0", version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")
        c2 = Constitution(agentium_id="C00002", version="v2.0.0", version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")
        db_session.add(c1)
        db_session.commit()

        db_session.add(c2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_constitution_articles_roundtrip(self, db_session):
        """Articles JSON roundtrips correctly via get_articles_dict()."""
        articles = {
            "article_1": {"title": "Sovereignty", "content": "Supreme law", "clauses": ["1.1", "1.2"]},
            "article_2": {"title": "Rights", "content": "Agent rights", "clauses": []},
        }
        constitution = Constitution(
            agentium_id="C00003",
            version="v3.0.0",
            version_number=3,
            articles=json.dumps(articles),
            prohibited_actions=json.dumps([]),
            sovereign_preferences=json.dumps({}),
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()
        db_session.refresh(constitution)

        # get_articles_dict normalizes the format
        parsed = constitution.get_articles_dict()
        assert "article_1" in parsed
        assert "article_2" in parsed
        assert parsed["article_1"]["title"] == "Sovereignty"
        assert parsed["article_1"]["content"] == "Supreme law"

    def test_constitution_prohibited_actions_roundtrip(self, db_session):
        """Prohibited actions JSON roundtrips correctly."""
        actions = ["action1", "action2", "action3"]
        constitution = Constitution(
            agentium_id="C00004",
            version="v4.0.0",
            version_number=4,
            articles=json.dumps({}),
            prohibited_actions=json.dumps(actions),
            sovereign_preferences=json.dumps({}),
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()
        db_session.refresh(constitution)

        assert constitution.get_prohibited_actions_list() == actions

    def test_constitution_sovereign_preferences_roundtrip(self, db_session):
        """Sovereign preferences JSON roundtrips correctly."""
        prefs = {"theme": "light", "language": "en", "auto_save": True}
        constitution = Constitution(
            agentium_id="C00005",
            version="v5.0.0",
            version_number=5,
            articles=json.dumps({}),
            prohibited_actions=json.dumps([]),
            sovereign_preferences=json.dumps(prefs),
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()
        db_session.refresh(constitution)

        assert constitution.get_sovereign_preferences() == prefs

    def test_constitution_changelog_roundtrip(self, db_session):
        """Changelog JSON roundtrips correctly."""
        changelog = [{"version": "1.0.0", "changes": ["Initial release"]}, {"version": "2.0.0", "changes": ["Added article 3"]}]
        constitution = Constitution(
            agentium_id="C00006",
            version="v6.0.0",
            version_number=6,
            articles=json.dumps({}),
            prohibited_actions=json.dumps([]),
            sovereign_preferences=json.dumps({}),
            changelog=json.dumps(changelog),
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()
        db_session.refresh(constitution)

        assert constitution.get_changelog() == changelog

    def test_constitution_amendment_chain(self, db_session):
        """Amendment chain works correctly (replaces_version relationship)."""
        c1 = Constitution(agentium_id="C00001", version="v1.0.0", version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")
        db_session.add(c1)
        db_session.commit()
        db_session.refresh(c1)

        c2 = Constitution(
            agentium_id="C00002",
            version="v2.0.0",
            version_number=2,
            articles="{}",
            prohibited_actions="[]",
            sovereign_preferences="{}",
            replaces_version_id=c1.id,
            created_by_agentium_id="00001",
        )
        db_session.add(c2)
        db_session.commit()
        db_session.refresh(c2)

        assert c2.replaces_version.id == c1.id
        assert len(c1.replaced_by.all()) == 1
        assert c1.replaced_by.first().id == c2.id

        # Test amendment_chain
        chain = c2.get_amendment_chain()
        assert len(chain) == 2
        assert chain[0].version == "v1.0.0"
        assert chain[1].version == "v2.0.0"

    def test_constitution_archive(self, db_session):
        """Archive method works correctly."""
        constitution = Constitution(agentium_id="C00001", version="v1.0.0", version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")
        db_session.add(constitution)
        db_session.commit()

        assert constitution.is_active is True
        assert constitution.archived_date is None

        constitution.archive()
        db_session.commit()

        assert constitution.is_active is False
        assert constitution.archived_date is not None

    def test_constitution_to_dict(self, db_session):
        """Constitution.to_dict() includes all fields."""
        constitution = Constitution(
            agentium_id="C00001",
            version="v1.0.0",
            version_number=1,
            preamble="Test preamble",
            articles=json.dumps({"article_1": {"title": "Test", "content": "Content"}}),
            prohibited_actions=json.dumps(["action1"]),
            sovereign_preferences=json.dumps({"key": "value"}),
            changelog=json.dumps([{"version": "1.0.0", "changes": ["Initial"]}]),
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()

        data = constitution.to_dict()
        assert data["version"] == "v1.0.0"
        assert data["version_number"] == 1
        assert data["preamble"] == "Test preamble"
        assert len(data["articles"]) == 1
        assert data["prohibited_actions"] == ["action1"]
        assert data["sovereign_preferences"] == {"key": "value"}
        assert len(data["changelog"]) == 1
        assert data["is_active"] is True
        assert data["document_type"] == "constitution"

    def test_constitution_version_validation(self, db_session):
        """Version validation rejects invalid format."""
        with pytest.raises(ValueError):
            Constitution(agentium_id="C00001", version="1.0.0", version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")

    def test_constitution_version_number_validation(self, db_session):
        """Version number validation rejects negative numbers."""
        with pytest.raises(ValueError):
            Constitution(agentium_id="C00001", version="v1.0.0", version_number=-1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}")


class TestEthos:
    """Tests for Ethos (working memory) model."""

    def test_ethos_creation(self, db_session):
        """Ethos creates with all fields."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid,
            agent_type="task_agent",
            mission_statement="Test mission",
            core_values=json.dumps(["integrity", "efficiency"]),
            behavioral_rules=json.dumps(["Follow constitution", "Report violations"]),
            restrictions=json.dumps(["No unauthorized access"]),
            capabilities=json.dumps(["coding", "analysis"]),
            current_objective="Complete task T00001",
            active_plan=json.dumps({"steps": ["step1", "step2"], "status": "in_progress"}),
            constitutional_references=json.dumps([{"section": "Article 1", "summary": "Sovereignty"}]),
            task_progress_markers=json.dumps({"step1": "completed", "step2": "in_progress"}),
            reasoning_artifacts=json.dumps([{"thought": "Initial reasoning"}]),
            outcome_summary="Initial summary",
            lessons_learned=json.dumps([{"lesson": "Lesson 1"}]),
            version=1,
            is_verified=True,
            created_by_agentium_id="20001",
            working_method="Test working method",
            environment_context="Test environment",
            agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()
        db_session.refresh(ethos)

        assert ethos.agentium_id == "E30001"
        assert ethos.agent_id == agent_uuid
        assert ethos.agent_type == "task_agent"
        assert ethos.mission_statement == "Test mission"
        assert ethos.get_core_values() == ["integrity", "efficiency"]
        assert ethos.get_behavioral_rules() == ["Follow constitution", "Report violations"]
        assert ethos.get_restrictions() == ["No unauthorized access"]
        assert ethos.get_capabilities() == ["coding", "analysis"]
        assert ethos.current_objective == "Complete task T00001"
        assert ethos.get_active_plan() == {"steps": ["step1", "step2"], "status": "in_progress"}
        assert ethos.get_constitutional_references() == [{"section": "Article 1", "summary": "Sovereignty"}]
        assert ethos.get_task_progress() == {"step1": "completed", "step2": "in_progress"}
        assert ethos.get_reasoning_artifacts() == [{"thought": "Initial reasoning"}]
        assert ethos.outcome_summary == "Initial summary"
        assert ethos.get_lessons_learned() == [{"lesson": "Lesson 1"}]
        assert ethos.version == 1
        assert ethos.is_verified is True
        assert ethos.created_by_agentium_id == "20001"

    def test_ethos_defaults(self, db_session):
        """Ethos defaults are correct."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid,
            agent_type="lead_agent",
            mission_statement="Lead mission",
            core_values=json.dumps([]),
            behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]),
            capabilities=json.dumps([]),
            created_by_agentium_id="10001",
            agentium_id="E20001",
        )
        db_session.add(ethos)
        db_session.commit()

        assert ethos.get_core_values() == []
        assert ethos.get_behavioral_rules() == []
        assert ethos.get_restrictions() == []
        assert ethos.get_capabilities() == []
        assert ethos.current_objective is None
        assert ethos.get_active_plan() is None
        assert ethos.get_constitutional_references() == []
        assert ethos.get_task_progress() == {}
        assert ethos.get_reasoning_artifacts() == []
        assert ethos.outcome_summary is None
        assert ethos.get_lessons_learned() == []
        assert ethos.version == 1
        assert ethos.is_verified is False
        assert ethos.verified_by_agentium_id is None
        assert ethos.verified_at is None
        assert ethos.last_updated_by_agent is False
        assert ethos.environment_context is None
        assert ethos.working_method is None
        assert ethos.meta_data is None

    def test_ethos_agentium_id_uniqueness(self, db_session):
        """Ethos agentium_id must be unique."""
        import uuid
        agent_uuid1 = str(uuid.uuid4())
        agent_uuid2 = str(uuid.uuid4())

        ethos1 = Ethos(
            agent_id=agent_uuid1, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        ethos2 = Ethos(
            agent_id=agent_uuid2, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20002", agentium_id="E30001",
        )
        db_session.add(ethos1)
        db_session.commit()

        db_session.add(ethos2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_ethos_verify(self, db_session):
        """verify() method marks ethos as verified."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        assert ethos.is_verified is False
        assert ethos.verified_by_agentium_id is None
        assert ethos.verified_at is None

        ethos.verify("10001")
        db_session.commit()

        assert ethos.is_verified is True
        assert ethos.verified_by_agentium_id == "10001"
        assert ethos.verified_at is not None

    def test_ethos_increment_version(self, db_session):
        """increment_version() bumps version counter."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20001", agentium_id="E30001",
            version=1,
        )
        db_session.add(ethos)
        db_session.commit()

        assert ethos.version == 1
        ethos.increment_version()
        db_session.commit()

        assert ethos.version == 2
        assert ethos.last_updated_by_agent is True

    def test_ethos_set_active_plan(self, db_session):
        """set_active_plan() stores plan and increments version."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        plan = {"steps": ["step1", "step2", "step3"], "title": "Test Plan", "status": "pending"}
        ethos.set_active_plan(plan)
        db_session.commit()

        assert ethos.get_active_plan() == plan
        assert ethos.version == 2

    def test_ethos_set_constitutional_references(self, db_session):
        """set_constitutional_references() updates references."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        refs = [{"section": "Article 1", "summary": "Sovereignty"}, {"section": "Article 2", "summary": "Agents"}]
        ethos.set_constitutional_references(refs)
        db_session.commit()

        assert ethos.get_constitutional_references() == refs

    def test_ethos_set_task_progress(self, db_session):
        """set_task_progress() updates progress markers."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        progress = {"step1": "completed", "step2": "in_progress", "step3": "pending"}
        ethos.set_task_progress(progress)
        db_session.commit()

        assert ethos.get_task_progress() == progress

    def test_ethos_add_lesson_learned(self, db_session):
        """add_lesson_learned() appends and limits to 20."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        # Add 25 lessons - should keep only last 20
        for i in range(25):
            ethos.add_lesson_learned({"lesson": f"Lesson {i}", "key_point": f"Point {i}"})

        lessons = ethos.get_lessons_learned()
        assert len(lessons) == 20
        # Last lesson should be "Lesson 24"
        assert lessons[-1]["lesson"] == "Lesson 24"

    def test_ethos_compress_clears_working_state(self, db_session):
        """compress() clears working state but preserves core identity."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test mission",
            core_values=json.dumps(["integrity"]), behavioral_rules=json.dumps(["Follow rules"]),
            restrictions=json.dumps(["No bad"]), capabilities=json.dumps(["coding"]),
            current_objective="Complete task",
            active_plan=json.dumps({"steps": ["s1"], "status": "done"}),
            task_progress_markers=json.dumps({"step1": "done"}),
            reasoning_artifacts=json.dumps([{"thought": "thinking"}]),
            outcome_summary="Done",
            lessons_learned=json.dumps([{"lesson": "learned"}]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        ethos.compress()
        db_session.commit()

        assert ethos.current_objective is None
        assert ethos.active_plan is None
        assert ethos.task_progress_markers is None
        assert ethos.reasoning_artifacts is None
        # Core identity preserved
        assert ethos.mission_statement == "Test mission"
        assert ethos.get_core_values() == ["integrity"]
        assert ethos.get_behavioral_rules() == ["Follow rules"]
        assert ethos.get_restrictions() == ["No bad"]
        assert ethos.get_capabilities() == ["coding"]
        assert ethos.outcome_summary == "Done"
        assert ethos.get_lessons_learned() == [{"lesson": "learned"}]
        assert ethos.version == 2

    def test_ethos_clear_working_state(self, db_session):
        """clear_working_state() resets for fresh task cycle."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test mission",
            core_values=json.dumps(["integrity"]), behavioral_rules=json.dumps(["Follow rules"]),
            restrictions=json.dumps(["No bad"]), capabilities=json.dumps(["coding"]),
            current_objective="Complete task",
            active_plan=json.dumps({"steps": ["s1"]}),
            task_progress_markers=json.dumps({"step1": "done"}),
            reasoning_artifacts=json.dumps([{"thought": "thinking"}]),
            constitutional_references=json.dumps([{"section": "Art 1"}]),
            lessons_learned=json.dumps([{"lesson": "learned"}]),
            outcome_summary="Done",
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        ethos.clear_working_state()
        db_session.commit()

        assert ethos.current_objective is None
        assert ethos.active_plan is None
        assert ethos.task_progress_markers is None
        assert ethos.reasoning_artifacts is None
        # Preserved
        assert ethos.get_constitutional_references() == [{"section": "Art 1"}]
        assert ethos.get_lessons_learned() == [{"lesson": "learned"}]
        assert ethos.outcome_summary == "Done"

    def test_ethos_build_compression_payload(self, db_session):
        """build_compression_payload() serializes working memory for LLM."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test mission",
            core_values=json.dumps(["integrity"]), behavioral_rules=json.dumps(["Follow rules"]),
            restrictions=json.dumps(["No bad"]), capabilities=json.dumps(["coding"]),
            current_objective="Complete task",
            active_plan=json.dumps({"steps": ["s1"], "status": "in_progress"}),
            task_progress_markers=json.dumps({"step1": "completed"}),
            reasoning_artifacts=json.dumps([{"thought": "thinking"}]),
            constitutional_references=json.dumps([{"section": "Art 1"}]),
            outcome_summary="Done",
            lessons_learned=json.dumps([{"lesson": "learned"}]),
            environment_context="test_env",
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        payload = ethos.build_compression_payload()

        assert payload["agent_type"] == "task_agent"
        assert payload["mission_statement"] == "Test mission"
        assert payload["current_objective"] == "Complete task"
        assert payload["active_plan"] == {"steps": ["s1"], "status": "in_progress"}
        assert payload["task_progress"] == {"step1": "completed"}
        assert payload["reasoning_artifacts"] == [{"thought": "thinking"}]
        assert payload["lessons_learned"] == [{"lesson": "learned"}]
        assert payload["constitutional_refs"] == [{"section": "Art 1"}]
        assert payload["outcome_summary"] == "Done"
        assert payload["environment_context"] == "test_env"

    def test_ethos_apply_llm_compression(self, db_session):
        """apply_llm_compression() writes compressed data back."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test mission",
            core_values=json.dumps(["integrity"]), behavioral_rules=json.dumps(["Follow rules"]),
            restrictions=json.dumps(["No bad"]), capabilities=json.dumps(["coding"]),
            current_objective="Complete task",
            active_plan=json.dumps({"steps": ["s1"], "status": "in_progress"}),
            task_progress_markers=json.dumps({"step1": "completed", "step2": "in_progress"}),
            reasoning_artifacts=json.dumps([{"thought": "old"}]),
            lessons_learned=json.dumps([{"lesson": "old"}]),
            constitutional_references=json.dumps([{"section": "Art 1"}, {"section": "Art 1"}]),
            outcome_summary="Old summary",
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        compressed = {
            "reasoning_artifacts": [{"thought": "compressed"}, {"thought": "new"}],
            "lessons_learned": [{"lesson": "consolidated"}, {"lesson": "recent"}],
            "constitutional_refs": [{"section": "Art 1"}],
            "outcome_summary": "New compressed summary",
        }
        # When completed_steps is provided (mid-task pruning), outcome_summary is NOT updated
        ethos.apply_llm_compression(compressed, completed_steps=["step1"])
        db_session.commit()

        assert ethos.get_reasoning_artifacts() == [{"thought": "compressed"}, {"thought": "new"}]
        assert ethos.get_lessons_learned() == [{"lesson": "consolidated"}, {"lesson": "recent"}]
        assert ethos.get_constitutional_references() == [{"section": "Art 1"}]
        # outcome_summary is preserved during mid-task pruning (completed_steps provided)
        assert ethos.outcome_summary == "Old summary"
        assert ethos.get_task_progress() == {"step2": "in_progress"}  # step1 removed
        assert ethos.version == 2

    def test_ethos_prune_obsolete_content(self, db_session):
        """prune_obsolete_content() fallback compression works."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        # Create many artifacts to trigger compression
        artifacts = [{"thought": f"thought {i}"} for i in range(20)]
        lessons = [{"lesson": f"lesson {i}"} for i in range(20)]

        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test mission",
            core_values=json.dumps(["integrity"]), behavioral_rules=json.dumps(["Follow rules"]),
            restrictions=json.dumps(["No bad"]), capabilities=json.dumps(["coding"]),
            reasoning_artifacts=json.dumps(artifacts),
            lessons_learned=json.dumps(lessons),
            constitutional_references=json.dumps([{"section": "Art 1"}, {"section": "Art 1"}]),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos)
        db_session.commit()

        original_version = ethos.version
        ethos.prune_obsolete_content()
        db_session.commit()

        # Should have compressed artifacts (75/25 split)
        remaining_artifacts = ethos.get_reasoning_artifacts()
        assert len(remaining_artifacts) <= 6  # 25% of 20 = 5, plus 1 compressed = 6 max

        # Should have compressed lessons
        remaining_lessons = ethos.get_lessons_learned()
        assert len(remaining_lessons) <= 6

        # Should have deduplicated constitutional refs
        remaining_refs = ethos.get_constitutional_references()
        assert len(remaining_refs) == 1

        # Version should increment
        assert ethos.version == original_version + 1

    def test_ethos_get_outcome_snapshot(self, db_session):
        """get_outcome_snapshot() parses outcome_summary."""
        import uuid
        agent_uuid = str(uuid.uuid4())

        # Test with dict format
        ethos1 = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            outcome_summary=json.dumps({"task": "T001", "status": "completed", "score": 95}),
            created_by_agentium_id="20001", agentium_id="E30001",
        )
        db_session.add(ethos1)
        db_session.commit()

        snapshot = ethos1.get_outcome_snapshot()
        assert snapshot == {"task": "T001", "status": "completed", "score": 95}

        # Test with raw string format (fallback)
        ethos2 = Ethos(
            agent_id=str(uuid.uuid4()), agent_type="task_agent", mission_statement="Test",
            core_values=json.dumps([]), behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]), capabilities=json.dumps([]),
            outcome_summary="Raw text summary",
            created_by_agentium_id="20001", agentium_id="E30002",
        )
        db_session.add(ethos2)
        db_session.commit()

        snapshot2 = ethos2.get_outcome_snapshot()
        assert snapshot2 == {"raw": "Raw text summary"}

    def test_ethos_to_dict(self, db_session):
        """Ethos.to_dict() includes all relevant fields."""
        import uuid
        agent_uuid = str(uuid.uuid4())
        ethos = Ethos(
            agent_id=agent_uuid, agent_type="task_agent", mission_statement="Test mission",
            core_values=json.dumps(["integrity"]), behavioral_rules=json.dumps(["Follow rules"]),
            restrictions=json.dumps(["No bad"]), capabilities=json.dumps(["coding"]),
            current_objective="Complete task",
            active_plan=json.dumps({"steps": ["s1"]}),
            constitutional_references=json.dumps([{"section": "Art 1"}]),
            task_progress_markers=json.dumps({"step1": "done"}),
            outcome_summary="Done",
            lessons_learned=json.dumps([{"lesson": "learned"}]),
            version=1,
            created_by_agentium_id="20001",
            agentium_id="E30001",
            environment_context="test_env",
            working_method="test_method",
        )
        db_session.add(ethos)
        db_session.commit()

        data = ethos.to_dict()
        assert data["agent_type"] == "task_agent"
        assert data["agentium_id"] == "E30001"
        assert data["mission_statement"] == "Test mission"
        assert data["core_values"] == ["integrity"]
        assert data["behavioral_rules"] == ["Follow rules"]
        assert data["restrictions"] == ["No bad"]
        assert data["capabilities"] == ["coding"]
        assert data["current_objective"] == "Complete task"
        assert data["active_plan"] == {"steps": ["s1"]}
        assert data["constitutional_references"] == [{"section": "Art 1"}]
        assert data["task_progress"] == {"step1": "done"}
        assert data["outcome_summary"] == {"raw": "Done"}
        assert data["lessons_learned"] == [{"lesson": "learned"}]
        assert data["version"] == 1
        assert data["created_by"] == "20001"
        assert data["verified"] is False
        assert data["agent_id"] == agent_uuid
        assert data["environment_context"] == "test_env"
        assert data["working_method"] == "test_method"


class TestDocumentType:
    """Tests for DocumentType enum."""

    @pytest.mark.parametrize("doc_type", [DocumentType.CONSTITUTION, DocumentType.ETHOS])
    def test_document_type_values(self, doc_type):
        """All DocumentType values are valid."""
        assert doc_type in (DocumentType.CONSTITUTION, DocumentType.ETHOS)
        assert isinstance(doc_type.value, str)