"""
Quick smoke tests for mcp_agent_tools.
"""
import pytest
from unittest.mock import MagicMock, patch


def test_mcp_agent_tools_imports():
    """Verify mcp_agent_tools module can be imported."""
    from backend.tools.mcp_agent_tools import (
        add_mcp_server,
        vote_on_mcp_server,
    )
    assert add_mcp_server is not None
    assert vote_on_mcp_server is not None


def test_mcp_add_server_signature():
    """Verify add_mcp_server has correct signature."""
    from backend.tools.mcp_agent_tools import add_mcp_server
    import inspect

    sig = inspect.signature(add_mcp_server)
    params = list(sig.parameters.keys())
    assert "name" in params
    assert "description" in params
    assert "server_url" in params
    assert "tier" in params
    assert "agent_id" in params
    assert "constitutional_article" in params


def test_mcp_vote_on_server_signature():
    """Verify vote_on_mcp_server has correct signature."""
    from backend.tools.mcp_agent_tools import vote_on_mcp_server
    import inspect

    sig = inspect.signature(vote_on_mcp_server)
    params = list(sig.parameters.keys())
    assert "tool_id" in params
    assert "vote" in params
    assert "agent_id" in params


def test_mcp_agent_tools_module():
    """Verify module imports correctly."""
    import backend.tools.mcp_agent_tools as mat

    assert hasattr(mat, "add_mcp_server")
    assert hasattr(mat, "vote_on_mcp_server")
    assert callable(mat.add_mcp_server)
    assert callable(mat.vote_on_mcp_server)