"""Unit tests for ResponseValidator."""
import pytest
from pydantic import BaseModel, Field
from typing import List, Literal
from backend.core.response_validator import ResponseValidator


class SampleResponse(BaseModel):
    title: str = Field(description="Task title")
    priority: Literal["high", "normal", "low"] = Field(description="Priority level")
    tags: List[str] = Field(default_factory=list, description="Optional tags")


def test_valid_json_parsed():
    """Valid JSON string should parse to model instance."""
    content = '{"title": "Test Task", "priority": "high", "tags": ["urgent"]}'
    model, error = ResponseValidator.validate(SampleResponse, content)

    assert error is None
    assert model is not None
    assert model.title == "Test Task"
    assert model.priority == "high"
    assert model.tags == ["urgent"]


def test_markdown_fence_extraction():
    """JSON inside ```json fences should be extracted and validated."""
    content = '```json\n{"title": "Test Task", "priority": "normal"}\n```'
    model, error = ResponseValidator.validate(SampleResponse, content)

    assert error is None
    assert model is not None
    assert model.title == "Test Task"
    assert model.priority == "normal"


def test_invalid_missing_field():
    """Missing required field should return error details."""
    content = '{"priority": "high"}'
    model, error = ResponseValidator.validate(SampleResponse, content)

    assert model is None
    assert error is not None
    assert error["type"] == "schema_validation_error"
    assert any(d["loc"] == ("title",) for d in error["details"])
    assert any(d["type"] == "missing" for d in error["details"])


def test_invalid_enum_value():
    """Invalid enum value should return error details."""
    content = '{"title": "Test", "priority": "urgent"}'
    model, error = ResponseValidator.validate(SampleResponse, content)

    assert model is None
    assert error is not None
    assert error["type"] == "schema_validation_error"
    assert any(d["loc"] == ("priority",) for d in error["details"])
    assert any(d["type"] == "literal_error" for d in error["details"])


def test_invalid_type_string_for_int():
    """String where int expected should fail with strict True."""
    from pydantic import BaseModel, Field

    class IntModel(BaseModel):
        count: int = Field(description="A count")

    content = '{"count": "five"}'
    model, error = ResponseValidator.validate(IntModel, content, strict=True)

    assert model is None
    assert error is not None
    assert any(d["type"] == "int_type" for d in error["details"])


def test_extra_fields_rejected_strict():
    """Extra fields should be rejected with strict=True (default) when model config has extra='forbid'."""
    from pydantic import ConfigDict

    class StrictModel(BaseModel):
        name: str
        model_config = ConfigDict(extra="forbid")

    content = '{"name": "test", "extra": "field"}'
    model, error = ResponseValidator.validate(StrictModel, content, strict=True)

    assert model is None
    assert error is not None
    assert any(d["type"] == "extra_forbidden" for d in error["details"])


def test_extra_fields_allowed_when_configured():
    """Extra fields allowed when model config has extra='allow'."""
    from pydantic import ConfigDict

    class AllowExtraModel(BaseModel):
        name: str
        model_config = ConfigDict(extra="allow")

    content = '{"name": "test", "extra": "field"}'
    model, error = ResponseValidator.validate(AllowExtraModel, content, strict=True)

    assert model is not None
    assert error is None
    assert model.name == "test"
    assert model.extra == "field"


def test_error_structure_includes_raw_content():
    """Error dict should include raw_content for debugging."""
    content = '{"priority": "high"}'
    model, error = ResponseValidator.validate(SampleResponse, content)

    assert error["raw_content"] == content
    assert error["type"] == "schema_validation_error"
    assert "details" in error
    assert "message" in error