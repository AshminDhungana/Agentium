# tests/unit/test_tool_registry_schema.py
import pytest
from pydantic import ValidationError
from backend.core.tool_registry import ToolRegistry, tool_registry


def test_build_pydantic_model_basic():
    registry = ToolRegistry()
    # Access private method for testing
    model = registry._build_pydantic_model({
        "query": {"type": "string", "description": "Search query"},
        "max_results": {"type": "integer", "description": "Max results", "optional": True, "default": 5},
    })

    # Valid input
    validated = model.model_validate({"query": "test", "max_results": 5})
    assert validated.query == "test"
    assert validated.max_results == 5

    # Missing optional field uses default
    validated = model.model_validate({"query": "test"})
    assert validated.query == "test"
    assert validated.max_results == 5  # uses default from schema


def test_build_pydantic_model_coercion():
    registry = ToolRegistry()
    model = registry._build_pydantic_model({
        "count": {"type": "integer", "description": "Count"},
        "enabled": {"type": "boolean", "description": "Enabled flag"},
    })

    # String to int coercion
    validated = model.model_validate({"count": "42", "enabled": "true"})
    assert validated.count == 42
    assert validated.enabled is True


def test_build_pydantic_model_enum():
    registry = ToolRegistry()
    model = registry._build_pydantic_model({
        "provider": {"type": "string", "description": "Provider", "enum": ["auto", "tavily", "brave"]},
    })

    validated = model.model_validate({"provider": "tavily"})
    assert validated.provider == "tavily"

    with pytest.raises(ValidationError) as exc:
        model.model_validate({"provider": "google"})
    errors = exc.value.errors()
    assert errors[0]["type"] == "literal_error"


def test_build_pydantic_model_missing_required():
    registry = ToolRegistry()
    model = registry._build_pydantic_model({
        "required_field": {"type": "string", "description": "Required"},
        "optional_field": {"type": "string", "description": "Optional", "optional": True},
    })

    with pytest.raises(ValidationError) as exc:
        model.model_validate({"optional_field": "present"})
    errors = exc.value.errors()
    assert errors[0]["type"] == "missing"
    assert errors[0]["loc"] == ("required_field",)


@pytest.mark.asyncio
async def test_execute_tool_async_validates_params():
    # Use global registry (singleton)
    registry = tool_registry

    # Register a simple test tool
    def dummy_tool(query: str, max_results: int = 5):
        return {"status": "success", "query": query, "max_results": max_results}

    registry.register_tool(
        name="dummy_test",
        description="Test tool",
        function=dummy_tool,
        parameters={
            "query": {"type": "string", "description": "Query"},
            "max_results": {"type": "integer", "description": "Max results", "optional": True},
        },
        authorized_tiers=["0xxxx"],
    )

    # Valid call with coercion
    result = await registry.execute_tool_async("dummy_test", query="test", max_results="10")
    assert result["status"] == "success"
    assert result["max_results"] == 10  # coerced from string

    # Missing optional param
    result = await registry.execute_tool_async("dummy_test", query="test")
    assert result["status"] == "success"
    # When optional param has no default in schema, Pydantic sets it to None
    # The function's default parameter is not used because validation happens first
    assert result["max_results"] is None


@pytest.mark.asyncio
async def test_execute_tool_async_rejects_invalid():
    registry = tool_registry

    def dummy_tool(query: str):
        return {"status": "success", "query": query}

    registry.register_tool(
        name="dummy_test2",
        description="Test tool",
        function=dummy_tool,
        parameters={
            "query": {"type": "string", "description": "Query"},
        },
        authorized_tiers=["0xxxx"],
    )

    # Missing required param
    result = await registry.execute_tool_async("dummy_test2", not_query="test")
    assert result["status"] == "error"
    assert result["error"]["type"] == "schema_validation_error"
    assert result["error"]["details"][0]["type"] == "missing"
    assert result["error"]["details"][0]["loc"] == ("query",)


@pytest.mark.asyncio
async def test_execute_tool_async_rejects_wrong_type():
    registry = tool_registry

    def dummy_tool(count: int):
        return {"status": "success", "count": count}

    registry.register_tool(
        name="dummy_test3",
        description="Test tool",
        function=dummy_tool,
        parameters={
            "count": {"type": "integer", "description": "Count"},
        },
        authorized_tiers=["0xxxx"],
    )

    # Non-coercible type
    result = await registry.execute_tool_async("dummy_test3", count="not_a_number")
    assert result["status"] == "error"
    assert result["error"]["type"] == "schema_validation_error"
    assert result["error"]["details"][0]["type"] == "int_parsing"


@pytest.mark.asyncio
async def test_execute_tool_async_strict_mode():
    registry = tool_registry

    def dummy_tool(count: int):
        return {"status": "success", "count": count}

    # Register with strict mode
    registry.register_tool(
        name="strict_tool",
        description="Strict tool",
        function=dummy_tool,
        parameters={
            "count": {"type": "integer", "description": "Count"},
        },
        authorized_tiers=["0xxxx"],
    )
    # Manually set strict flag (simulating registry metadata)
    registry.tools["strict_tool"]["strict_validation"] = True

    # Valid integer - should work
    result = await registry.execute_tool_async("strict_tool", count=5)
    assert result["status"] == "success"

    # String that would coerce in normal mode - should FAIL in strict
    result = await registry.execute_tool_async("strict_tool", count="5")
    assert result["status"] == "error"
    assert result["error"]["type"] == "schema_validation_error"


@pytest.mark.asyncio
async def test_sensitive_tools_strict_mode():
    registry = tool_registry
    # Ensure sensitive tools have strict_validation = True
    assert registry.tools["execute_command"].get("strict_validation") is True
    assert registry.tools["code_execution"].get("strict_validation") is True
    assert registry.tools["remote_exec"].get("strict_validation") is True
    assert registry.tools["desktop_delete_file"].get("strict_validation") is True
    assert registry.tools["host_smart_execute"].get("strict_validation") is True