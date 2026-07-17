"""
Registration tests for the vector_db tool.

Run inside the backend container:
    docker compose exec -T backend bash -lc \
        "cd /app/backend && pytest tests/integration/test_vector_db_registration.py -o addopts='' -q"
"""
from backend.core.tool_registry import tool_registry


VALID_TIERS = ["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"]


def test_vector_db_registered():
    assert "vector_db" in tool_registry.tools


def test_vector_db_available_to_all_tiers():
    for tier in VALID_TIERS:
        available = tool_registry.list_tools(tier)
        assert "vector_db" in available, f"vector_db missing for tier {tier}"
        assert "query" in available["vector_db"]["description"].lower()


def test_vector_db_exported_to_openai_and_anthropic():
    for tier in VALID_TIERS:
        openai_tools = tool_registry.to_openai_tools(tier)
        names = [t["function"]["name"] for t in openai_tools]
        assert "vector_db" in names

        anthropic_tools = tool_registry.to_anthropic_tools(tier)
        a_names = [t["name"] for t in anthropic_tools]
        assert "vector_db" in a_names

        spec = next(t for t in openai_tools if t["function"]["name"] == "vector_db")
        props = spec["function"]["parameters"]["properties"]
        assert "action" in props
        assert "query" in props
        # "action" is required so agents always specify an operation
        assert "action" in spec["function"]["parameters"]["required"]
