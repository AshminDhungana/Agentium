"""
Quick smoke tests for skill_creator_tool.
"""
import pytest
from unittest.mock import MagicMock, patch


def test_skill_creator_help():
    from backend.tools.skill_creator_tool import skill_creator_tool

    result = skill_creator_tool.execute(action="help")
    assert result["success"] is True
    assert "help" in result


def test_skill_creator_invalid_action():
    from backend.tools.skill_creator_tool import skill_creator_tool

    result = skill_creator_tool.execute(action="invalid")
    assert result["success"] is False
    assert "unknown action" in result["error"].lower()


def test_skill_creator_missing_action():
    from backend.tools.skill_creator_tool import skill_creator_tool

    result = skill_creator_tool.execute()
    assert result["success"] is True  # Defaults to help


def test_skill_creator_tier_restriction():
    from backend.tools.skill_creator_tool import skill_creator_tool

    # Task agent (30001) should be rejected
    result = skill_creator_tool.execute(
        action="create",
        skill_name="test_skill",
        display_name="Test Skill",
        description="A test skill for verification that is long enough",
        skill_type="automation",
        domain="general",
        complexity="beginner",
        tags=["test"],
        steps=["Step 1"],
        validation_criteria=["Valid"],
        agent_id="30001"
    )
    assert result["success"] is False
    assert "head" in result["error"].lower() or "council" in result["error"].lower()


def test_skill_creator_imports():
    """Verify skill_creator_tool module can be imported."""
    from backend.tools.skill_creator_tool import (
        skill_creator_tool,
        SkillCreatorTool,
        SKILLS_ROOT,
    )
    assert skill_creator_tool is not None
    assert SkillCreatorTool is not None
    assert SKILLS_ROOT is not None