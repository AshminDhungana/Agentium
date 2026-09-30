"""
Backend API tests for skills routes.
Verifies skill CRUD, search, and RAG execution endpoints.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from backend.api.routes.skills import (
    search_skills,
    get_popular_skills,
    create_skill,
    deprecate_skill,
    get_skill_full,
    DeprecateRequest,
)
from backend.core.exceptions import ForbiddenError, NotFoundError, BadRequestError


class TestSkillsRoutes:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.fixture
    def privileged_user_ctx(self):
        """Auth context for a Sovereign (User) with head-level privileges."""
        return {
            "type": "user",
            "id": "usr-uuid-1",
            "role": "primary_sovereign",
            "agent_tier": "head",
            "is_privileged": True,
            "identifier": "sovereign",
        }

    @pytest.fixture
    def unprivileged_user_ctx(self):
        return {
            "type": "user",
            "id": "usr-uuid-2",
            "role": "user",
            "agent_tier": "task_agent",
            "is_privileged": False,
            "identifier": "testuser",
        }

    # ── GET /search ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_db, privileged_user_ctx):
        """GET /search returns matching skills with proper response shape."""
        mock_results = [
            {
                "skill_id": "skill_0xxxx_001",
                "relevance_score": 0.87,
                "content_preview": "Step 1: ...",
                "metadata": {
                    "display_name": "React Form Validation",
                    "skill_type": "code_generation",
                    "domain": "frontend",
                    "creator_id": "00001",
                },
            }
        ]

        with patch("backend.api.routes.skills.skill_manager") as mock_mgr:
            mock_mgr.search_skills.return_value = mock_results

            res = await search_skills(
                query="react forms",
                db=mock_db,
                auth_context=privileged_user_ctx,
            )

            assert res["query"] == "react forms"
            assert res["results_count"] == 1
            assert res["results"][0]["skill_id"] == "skill_0xxxx_001"
            mock_mgr.search_skills.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_creator_id_filter_resolves_user_uuid(
        self, mock_db, privileged_user_ctx
    ):
        """P1 fix: creator_id filter resolves user UUID to agent agentium_id."""
        mock_results = [
            {
                "skill_id": "skill_0xxxx_001",
                "relevance_score": 0.9,
                "metadata": {"creator_id": "00001", "display_name": "Test"},
                "content_preview": "...",
            }
        ]

        mock_agent = MagicMock()
        mock_agent.agentium_id = "00001"

        with patch("backend.api.routes.skills.skill_manager") as mock_mgr:
            mock_mgr.search_skills.return_value = mock_results
            # Mock db.query(Agent).filter(...).first() to return the agent
            mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

            res = await search_skills(
                query="",
                creator_id="usr-uuid-1",  # User UUID (not agentium_id)
                db=mock_db,
                auth_context=privileged_user_ctx,
            )

            # Should still find the result because the UUID was resolved to "00001"
            assert res["results_count"] == 1
            assert res["results"][0]["metadata"]["creator_id"] == "00001"

    # ── POST / (create) ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_skill_success(self, mock_db, privileged_user_ctx):
        """POST / creates a skill via skill_manager.create_skill."""
        mock_skill = MagicMock()
        mock_skill.skill_id = "skill_new_001"
        mock_skill.verification_status = "verified"

        mock_agent = MagicMock()
        mock_agent.agentium_id = "00001"

        with patch("backend.api.routes.skills.skill_manager") as mock_mgr:
            mock_mgr.create_skill.return_value = mock_skill
            mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

            res = await create_skill(
                skill_data={
                    "display_name": "New Skill",
                    "skill_type": "code_generation",
                    "domain": "frontend",
                    "description": "A new skill",
                    "steps": ["Step 1"],
                },
                auto_verify=True,
                db=mock_db,
                auth_context=privileged_user_ctx,
            )

            assert res["skill_id"] == "skill_new_001"
            assert res["status"] == "verified"
            mock_mgr.create_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_skill_auto_verify_forbidden_for_unprivileged(
        self, mock_db, unprivileged_user_ctx
    ):
        """Unprivileged users cannot auto-verify skills."""
        with pytest.raises(ForbiddenError):
            await create_skill(
                skill_data={"display_name": "Test"},
                auto_verify=True,
                db=mock_db,
                auth_context=unprivileged_user_ctx,
            )

    # ── POST /{skill_id}/deprecate ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_deprecate_skill_success(self, mock_db, privileged_user_ctx):
        """POST /{id}/deprecate soft-deletes the skill."""
        mock_skill_db = MagicMock()
        mock_skill_db.creator_id = "00001"
        mock_skill_db.verification_status = "verified"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_skill_db

        res = await deprecate_skill(
            skill_id="skill_0xxxx_001",
            body=DeprecateRequest(reason="No longer needed"),
            db=mock_db,
            auth_context=privileged_user_ctx,
        )

        assert res["message"] == "Skill deprecated successfully"
        assert mock_skill_db.verification_status == "deprecated"
        assert mock_skill_db.rejection_reason == "No longer needed"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deprecate_skill_not_found(self, mock_db, privileged_user_ctx):
        """Deprecating a non-existent skill raises NotFoundError."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(NotFoundError):
            await deprecate_skill(
                skill_id="nonexistent",
                body=DeprecateRequest(reason="test"),
                db=mock_db,
                auth_context=privileged_user_ctx,
            )

    # ── GET /stats/popular ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_popular_skills(self, mock_db, privileged_user_ctx):
        """GET /stats/popular returns verified skills ordered by usage."""
        mock_skill = MagicMock()
        mock_skill.to_dict.return_value = {
            "skill_id": "skill_001",
            "display_name": "Popular Skill",
            "usage_count": 100,
            "verification_status": "verified",
        }

        mock_db.query.return_value.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_skill
        ]

        res = await get_popular_skills(
            db=mock_db,
            auth_context=privileged_user_ctx,
        )

        assert len(res["skills"]) == 1
        assert res["skills"][0]["display_name"] == "Popular Skill"
        assert res["skills"][0]["usage_count"] == 100
