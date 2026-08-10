# 21.1.4 Output Format & Schema Compliance Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured output validation for LLM responses with automatic re-prompting when validation fails, plus native `response_format` support for OpenAI-compatible providers.

**Architecture:** New `ResponseValidator` class validates final LLM output against a caller-provided Pydantic model. On failure, `retry_with_validation()` re-prompts the LLM (max 2 retries). Providers with native `response_format` support (OpenAI, Groq, Mistral, etc.) use it automatically to reduce retries.

**Tech Stack:** Python 3.11+, Pydantic v2, Anthropic SDK, OpenAI SDK, AsyncIO

## Global Constraints

- Backward compatible — `response_model` parameter is optional, zero overhead when not provided
- Max 2 validation retries (configurable via `max_validation_retries`)
- All providers supported via re-prompting fallback
- Native `response_format` used automatically for OpenAI-compatible providers
- Test coverage ≥90% for new code
- No new external dependencies

---

### Task 1: Create ResponseValidator Core Class

**Files:**
- Create: `backend/core/response_validator.py`
- Test: `backend/tests/unit/test_response_validator.py`

**Interfaces:**
- Consumes: Pydantic model class, response text string
- Produces: `(parsed_model_instance, None)` on success, `(None, error_dict)` on failure

- [ ] **Step 1: Write the failing test**

```python
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
    assert any(d["type"] == "int_parsing" for d in error["details"])


def test_extra_fields_rejected_strict():
    """Extra fields should be rejected with strict=True (default)."""
    class StrictModel(BaseModel):
        name: str
    
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
    assert "attempts" in error  # will be added by retry logic, not validator directly


- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_response_validator.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.core.response_validator'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Response validation for LLM structured outputs."""
import json
import re
from typing import Any, Dict, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError


class ResponseValidator:
    """
    Validates LLM response text against a Pydantic model.
    
    Handles:
    - Direct JSON strings
    - JSON inside markdown code fences (```json ... ```)
    - Strict Pydantic validation with detailed error reporting
    """
    
    @staticmethod
    def _extract_json(content: str) -> str:
        """Extract JSON from markdown code fences or return as-is."""
        # Try to find ```json ... ``` pattern
        fence_pattern = r'```(?:json)?\s*\n(.*?)\n```'
        matches = re.findall(fence_pattern, content, re.DOTALL)
        if matches:
            # Use the last match (most likely the intended response)
            return matches[-1].strip()
        
        # Try to find ``` ... ``` without language hint
        fence_pattern_generic = r'```\s*\n(.*?)\n```'
        matches = re.findall(fence_pattern_generic, content, re.DOTALL)
        if matches:
            return matches[-1].strip()
        
        return content.strip()
    
    @staticmethod
    def validate(
        model: Type[BaseModel],
        content: str,
        *,
        strict: bool = True,
    ) -> Tuple[Optional[BaseModel], Optional[Dict[str, Any]]]:
        """
        Validate content against model.
        
        Args:
            model: Pydantic model class to validate against
            content: Raw response text from LLM
            strict: If True, use strict validation (reject extra fields)
        
        Returns:
            (parsed_model_instance, None) if valid
            (None, error_dict) if invalid
            
        error_dict structure:
            {
                "type": "schema_validation_error",
                "message": "Response does not match expected schema",
                "details": [...],  # Pydantic ValidationError.errors()
                "raw_content": str  # original content for debugging
            }
        """
        # Extract JSON from markdown fences if present
        json_str = ResponseValidator._extract_json(content)
        
        try:
            # Parse and validate using Pydantic
            parsed = model.model_validate_json(json_str, strict=strict)
            return parsed, None
        except ValidationError as e:
            error_dict = {
                "type": "schema_validation_error",
                "message": "Response does not match expected schema",
                "details": e.errors(),
                "raw_content": content,  # Keep original for debugging
            }
            return None, error_dict
        except json.JSONDecodeError as e:
            error_dict = {
                "type": "schema_validation_error",
                "message": f"Invalid JSON: {str(e)}",
                "details": [{"loc": (), "msg": str(e), "type": "json_decode_error"}],
                "raw_content": content,
            }
            return None, error_dict
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_response_validator.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/response_validator.py backend/tests/unit/test_response_validator.py
git commit -m "feat: add ResponseValidator for structured output validation"
```

---

### Task 2: Add retry_with_validation Helper

**Files:**
- Modify: `backend/services/model_provider.py` (add new function)
- Test: `backend/tests/unit/test_retry_validation.py`

**Interfaces:**
- Consumes: response_model, invalid content, conversation history, provider instance, system_prompt
- Produces: (parsed_model, None) on success, (None, error_dict) on max retries exceeded

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for retry_with_validation helper."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field
from typing import List, Literal
from backend.services.model_provider import retry_with_validation


class TaskResponse(BaseModel):
    title: str
    priority: Literal["high", "normal", "low"]
    tags: List[str] = []


class MockProvider:
    """Mock provider for testing."""
    
    def __init__(self, responses: List[str]):
        self.responses = responses
        self.call_count = 0
    
    async def generate(self, system_prompt: str, user_message: str, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            response = self.responses[-1]
        self.call_count += 1
        
        return {
            "content": response,
            "tokens_used": 100,
            "prompt_tokens": 50,
            "completion_tokens": 50,
            "latency_ms": 100,
            "model": "test-model",
        }


@pytest.mark.asyncio
async def test_invalid_then_valid_on_retry():
    """First invalid, second valid should succeed with 1 retry."""
    provider = MockProvider([
        '{"priority": "high"}',  # missing title - invalid
        '{"title": "Fixed Task", "priority": "normal"}',  # valid
    ])
    
    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."
    
    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='{"priority": "high"}',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )
    
    assert error is None
    assert model is not None
    assert model.title == "Fixed Task"
    assert model.priority == "normal"
    assert provider.call_count == 2  # Called twice


@pytest.mark.asyncio
async def test_max_retries_exceeded_returns_error():
    """All retries invalid should return error with attempt count."""
    provider = MockProvider([
        '{"priority": "high"}',  # invalid
        '{"title": "x"}',  # invalid - missing priority
        'still invalid',  # invalid
    ])
    
    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."
    
    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='{"priority": "high"}',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )
    
    assert model is None
    assert error is not None
    assert error["type"] == "schema_validation_error"
    assert error["attempts"] == 2  # max_retries
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_valid_on_first_try_no_retry():
    """Valid content on first try should not call provider again."""
    provider = MockProvider([
        '{"title": "Valid Task", "priority": "high"}',
    ])
    
    messages = [{"role": "user", "content": "Create a task"}]
    system_prompt = "You are a task creator."
    
    model, error = await retry_with_validation(
        response_model=TaskResponse,
        content='{"title": "Valid Task", "priority": "high"}',
        messages=messages,
        provider=provider,
        system_prompt=system_prompt,
        max_retries=2,
        agentium_id="test-agent",
    )
    
    assert error is None
    assert model is not None
    assert provider.call_count == 0  # No retry needed