# backend/tests/unit/test_tool_search_tool.py
import asyncio
from backend.tools import tool_search_tool


def test_search_ranks_by_query():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute("search", query="search the web", tier="0xxxx", limit=5)
    )
    assert result["status"] == "success"
    names = [r["name"] for r in result["results"]]
    assert "web_search" in names
    assert result["results"][0]["name"] == "web_search"


def test_get_returns_descriptor():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute("get", name="web_search", tier="0xxxx")
    )
    assert result["status"] == "success"
    assert "description" in result


def test_empty_query_errors():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute("search", query="   ", tier="0xxxx")
    )
    assert result["status"] == "error"


def test_help_action():
    result = asyncio.get_event_loop().run_until_complete(tool_search_tool.execute("help"))
    assert result["status"] == "success"


def test_search_scoped_to_caller_tier():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute("search", query="execute code", agent_id="30001")
    )
    assert result["status"] == "success"
    names = [r["name"] for r in result["results"]]
    assert "code_execution" not in names


def test_tier_override_clamped():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute(
            "search", query="execute code", agent_id="30001", tier="0xxxx"
        )
    )
    assert result["status"] == "success"
    names = [r["name"] for r in result["results"]]
    assert "code_execution" not in names
