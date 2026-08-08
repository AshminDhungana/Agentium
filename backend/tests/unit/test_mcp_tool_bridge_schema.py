# tests/unit/test_mcp_tool_bridge_schema.py
import pytest
from pydantic import ValidationError
from backend.services.mcp_tool_bridge import _build_pydantic_model_from_jsonschema


def test_build_pydantic_model_from_jsonschema_basic():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results"},
        },
        "required": ["query"],
    })

    validated = model.model_validate({"query": "test", "max_results": 10})
    assert validated.query == "test"
    assert validated.max_results == 10


def test_build_pydantic_model_from_jsonschema_optional():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "required_field": {"type": "string"},
            "optional_field": {"type": "string"},
        },
        "required": ["required_field"],
    })

    validated = model.model_validate({"required_field": "present"})
    assert validated.required_field == "present"
    assert validated.optional_field is None


def test_build_pydantic_model_from_jsonschema_enum():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "provider": {"type": "string", "enum": ["auto", "tavily", "brave"]},
        },
        "required": ["provider"],
    })

    validated = model.model_validate({"provider": "tavily"})
    assert validated.provider == "tavily"

    with pytest.raises(ValidationError) as exc:
        model.model_validate({"provider": "google"})
    errors = exc.value.errors()
    # Pydantic v2 uses "literal_error" for Literal type validation
    assert any(e["type"] == "literal_error" for e in errors)


def test_build_pydantic_model_from_jsonschema_missing_required():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "required_field": {"type": "string"},
            "optional_field": {"type": "string"},
        },
        "required": ["required_field"],
    })

    with pytest.raises(ValidationError) as exc:
        model.model_validate({"optional_field": "present"})
    errors = exc.value.errors()
    assert errors[0]["type"] == "missing"
    assert errors[0]["loc"] == ("required_field",)


def test_build_pydantic_model_from_jsonschema_coercion():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "enabled": {"type": "boolean"},
        },
        "required": ["count", "enabled"],
    })

    validated = model.model_validate({"count": "42", "enabled": "true"})
    assert validated.count == 42
    assert validated.enabled is True


def test_build_pydantic_model_from_jsonschema_default():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "required_field": {"type": "string"},
            "optional_with_default": {"type": "integer", "default": 100},
        },
        "required": ["required_field"],
    })

    validated = model.model_validate({"required_field": "test"})
    assert validated.required_field == "test"
    assert validated.optional_with_default == 100


def test_build_pydantic_model_from_jsonschema_additional_props_forbid():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "field": {"type": "string"},
        },
        "required": ["field"],
        "additionalProperties": False,
    })

    # Should work with expected field
    validated = model.model_validate({"field": "test"})
    assert validated.field == "test"

    # Should fail with extra field
    with pytest.raises(ValidationError) as exc:
        model.model_validate({"field": "test", "extra": "not allowed"})
    errors = exc.value.errors()
    assert errors[0]["type"] == "extra_forbidden"


def test_build_pydantic_model_from_jsonschema_additional_props_ignore():
    model = _build_pydantic_model_from_jsonschema({
        "type": "object",
        "properties": {
            "field": {"type": "string"},
        },
        "required": ["field"],
        "additionalProperties": True,
    })

    # Extra fields should be ignored (forward compat)
    validated = model.model_validate({"field": "test", "extra": "ignored"})
    assert validated.field == "test"


def test_build_pydantic_model_from_jsonschema_invalid_type():
    # Non-object schema should return permissive model
    model = _build_pydantic_model_from_jsonschema({
        "type": "string",
    })

    validated = model.model_validate({"data": {"any": "thing"}})
    assert validated.data == {"any": "thing"}


def test_build_pydantic_model_from_jsonschema_empty():
    # Empty/None schema should return permissive model
    model = _build_pydantic_model_from_jsonschema({})
    validated = model.model_validate({"data": {"any": "thing"}})
    assert validated.data == {"any": "thing"}

    model = _build_pydantic_model_from_jsonschema(None)
    validated = model.model_validate({"data": {"any": "thing"}})
    assert validated.data == {"any": "thing"}