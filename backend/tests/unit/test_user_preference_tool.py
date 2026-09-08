"""
Quick smoke tests for user_preference_tool.
"""
import pytest
from unittest.mock import MagicMock, patch


def test_user_preference_get():
    from backend.tools.user_preference_tool import user_preference_tool

    # Tool requires database - test that method exists
    assert hasattr(user_preference_tool, 'get_preference')
    assert callable(user_preference_tool.get_preference)


def test_user_preference_set():
    from backend.tools.user_preference_tool import user_preference_tool

    assert hasattr(user_preference_tool, 'set_preference')
    assert callable(user_preference_tool.set_preference)


def test_user_preference_list():
    from backend.tools.user_preference_tool import user_preference_tool

    assert hasattr(user_preference_tool, 'list_preferences')
    assert callable(user_preference_tool.list_preferences)


def test_user_preference_get_categories():
    from backend.tools.user_preference_tool import user_preference_tool

    assert hasattr(user_preference_tool, 'get_categories')
    assert callable(user_preference_tool.get_categories)


def test_user_preference_bulk_update():
    from backend.tools.user_preference_tool import user_preference_tool

    assert hasattr(user_preference_tool, 'bulk_update')
    assert callable(user_preference_tool.bulk_update)


def test_user_preference_get_defaults():
    from backend.tools.user_preference_tool import user_preference_tool

    result = user_preference_tool.get_default_preferences()
    assert result["status"] == "success"
    assert "defaults" in result


def test_user_preference_imports():
    from backend.tools.user_preference_tool import user_preference_tool, UserPreferenceTool

    assert user_preference_tool is not None
    assert UserPreferenceTool is not None