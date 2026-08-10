# 21.1.4 — Output Format & Schema Compliance Enforcement Design

## Overview

This document describes the design for enforcing structured output formatting on LLM responses. The feature ensures that agent final responses conform to caller-specified Pydantic models, with automatic re-prompting when validation fails.

**Related to**: Task 21.1.2 (Tool-Call Schema & Parameter Validation — already implemented)

---

## Current State Analysis

| Component | Status | Notes |
|-----------|--------|-------|
| Tool parameter validation | ✅ Complete | `tool_registry.py` validates tool arguments via Pydantic models |
| LLM response validation | ❌ Missing | No validation of final structured output |
| Native `response_format` support | ❌ Missing | OpenAI-compatible providers could use `json_schema` mode |

---

## Design Philosophy

1. **Opt-in only** — Validation activates only when caller provides `response_model`
2. **Provider-agnostic** — Works with Anthropic, OpenAI, Gemini, Local, all via re-prompting
3. **Native first** — Uses provider's `response_format` when available (reduces retries)
4. **Graceful degradation** — On max retries, returns raw content + error details for caller handling
5. **Backward compatible** — Zero changes to existing callers

---

## 1. Architecture

### 1.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ ModelService.generate_with_agent_tools()                        │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Agentic tool-calling loop (existing)                        │ │
│ │   - LLM calls tools → executes → feeds results              │ │
│ │   - Runs max_tool_iterations turns                          │ │
│ └─────────────────────────────────────────────────────────────┘ │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ NEW: Response Validation Layer                                  │
│ ┌─────────────────────────┐  ┌───────────────────────────────┐ │
│ │ ResponseValidator       │  │ retry_with_validation()       │ │
│ │ - validate(model, text) │  │ - Re-prompts LLM on failure   │ │
│ │ - extracts JSON from    │  │ - Max 2 retries               │ │
│ │   markdown fences       │  │ - Uses provider.generate()    │ │
│ │ - returns (model|None,  │  │ - Auto-uses response_format   │ │
│ │   error_dict|None)      │  │   when supported              │ │
│ └─────────────────────────┘  └───────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                    Returns result dict with:
                    - parsed_response (if valid)
                    - validation_error (if failed after retries)
                    - validation_retries (count)
```

### 1.2 Data Flow

```
Caller provides response_model=TaskResponse
                    ↓
generate_with_agent_tools(..., response_model=TaskResponse)
                    ↓
Agentic loop completes → final content: '{"title": "X", "priority": "high"}'
                    ↓
ResponseValidator.validate(TaskResponse, content)
                    ↓
         ┌────────────────┴────────────────┐
         │                                 │
    Valid                                Invalid
         │                                 │
         ↓                                 ↓
Return parsed           retry_with_validation(model, content, conversation, provider)
model instance                ↓
              ┌───────────────┴───────────────┐
              │                               │
         Retry 1 succeeds               Retry 1 fails
              │                               │
              ↓                               ↓
Return parsed              Retry 2 (same logic)
model instance                  │
                        ┌───────┴────────┐
                        │                │
                   Retry 2 ok       Retry 2 fails
                        │                │
                        ↓                ↓
               Return parsed      Return raw content +
               model instance     validation_error dict
```

---

## 2. New Components

### 2.1 `ResponseValidator` — `backend/core/response_validator.py`

```python
class ResponseValidator:
    """
    Validates LLM response text against a Pydantic model.
    
    Handles:
    - Direct JSON strings
    - JSON inside markdown code fences (```json ... ```)
    - Strict Pydantic validation with detailed error reporting
    """
    
    @staticmethod
    def validate(
        model: Type[BaseModel],
        content: str,
        *,
        strict: bool = True,
    ) -> Tuple[Optional[BaseModel], Optional[Dict[str, Any]]]:
        """
        Validate content against model.
        
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
```

**Key behaviors**:
- Extracts JSON from markdown fences automatically
- Uses `model.model_validate_json()` for strict validation
- Returns structured errors matching Pydantic's `ValidationError.errors()` format
- `strict=True` rejects extra fields (forward compatibility controlled by model config)

### 2.2 `retry_with_validation()` — `backend/services/model_provider.py`

```python
async def retry_with_validation(
    response_model: Type[BaseModel],
    content: str,
    messages: List[Dict[str, str]],
    provider: BaseModelProvider,
    system_prompt: str,
    *,
    max_retries: int = 2,
    agentium_id: str = "system",
    **kwargs,
) -> Tuple[Optional[BaseModel], Optional[Dict[str, Any]]]:
    """
    Re-prompt LLM to produce valid structured output.
    
    Strategy:
    1. Try native response_format if provider supports it (OpenAI-compatible)
    2. Otherwise, add validation error as user message and call provider.generate()
    3. Repeat up to max_retries times
    
    Returns:
        (parsed_model, None) on success
        (None, error_dict) on max retries exceeded
    """
```

**Re-prompt message format**:
```
Your previous response failed schema validation.

Errors:
- Field 'title' is required (location: title)
- Field 'priority' must be one of: high, normal, low (location: priority)

Please output ONLY valid JSON matching the schema. No markdown, no explanations.
```

---

## 3. Integration Points

### 3.1 `ModelService.generate_with_agent_tools()` — Updated Signature

```python
@staticmethod
async def generate_with_agent_tools(
    agent,
    user_message: str,
    db,
    config_id: Optional[str] = None,
    system_prompt_override: Optional[str] = None,
    agent_tier: Optional[str] = None,
    task_id: Optional[str] = None,
    max_tool_iterations: int = 10,
    history: Optional[List[Dict[str, str]]] = None,
    on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]] = None,
    # NEW PARAMETERS:
    response_model: Optional[Type[BaseModel]] = None,
    max_validation_retries: int = 2,
    **kwargs,
) -> Dict[str, Any]:
```

**Result dict additions** (when `response_model` provided):
```python
{
    "content": "original text response",
    "tokens_used": 1234,
    "prompt_tokens": 567,
    "completion_tokens": 667,
    "latency_ms": 4500,
    "model": "claude-sonnet-4-6",
    "messages": [...],
    # NEW FIELDS:
    "parsed_response": {"title": "X", "priority": "high"},  # if validation passed
    "validation_error": {...},  # if all retries failed
    "validation_retries": 1,    # number of retries attempted
}
```

### 3.2 Provider Integration — Native `response_format`

**OpenAI-compatible providers** (`OpenAICompatibleProvider`, `LocalProvider`, `GeminiProvider`):
- When `response_model` provided, auto-generate JSON schema via `model.model_json_schema()`
- Pass `response_format={"type": "json_schema", "json_schema": {"name": "...", "schema": ..., "strict": true}}`
- Reduces/eliminates need for re-prompting

**Anthropic provider**:
- No native `response_format` equivalent
- Falls back to re-prompting strategy
- Could use forced tool call as alternative (future enhancement)

---

## 4. Error Handling

| Scenario | Result Fields | Behavior |
|----------|---------------|----------|
| Valid on first try | `parsed_response`, `validation_retries=0` | Normal return |
| Valid after N retries | `parsed_response`, `validation_retries=N` | Returns parsed model |
| All retries failed | `content` (raw), `validation_error`, `validation_retries=max` | Caller decides handling |
| No `response_model` provided | (unchanged) | Zero overhead, no validation |
| Provider supports native format | `parsed_response`, `validation_retries=0` | Best performance |

**Validation Error Structure**:
```python
{
    "type": "schema_validation_error",
    "message": "Response does not match expected schema",
    "details": [
        {"loc": ("field_name",), "msg": "Field required", "type": "missing"},
        {"loc": ("nested", "field"), "msg": "Input should be a valid integer", "type": "int_parsing"}
    ],
    "attempts": 2,
    "raw_content": "{'title': 'Task'}"  # original for debugging
}
```

---

## 5. Testing Strategy

### 5.1 Unit Tests — `backend/tests/unit/test_response_validator.py`

| Test | Description |
|------|-------------|
| `test_valid_json_parsed` | Direct JSON string → parsed model |
| `test_markdown_fence_extraction` | ```json {...}``` → extracted & validated |
| `test_invalid_missing_field` | Missing required field → error details |
| `test_invalid_type_coercion` | String "5" for int field → error (strict=True) |
| `test_extra_fields_rejected` | Extra field with strict model → error |
| `test_extra_fields_allowed` | Extra field with `extra="allow"` model → ok |

### 5.2 Integration Tests — `backend/tests/integration/test_response_validation.py`

| Test | Description |
|------|-------------|
| `test_valid_response_returns_parsed` | Agent outputs valid JSON → `parsed_response` present |
| `test_invalid_then_valid_on_retry` | First invalid, re-prompts, second valid → `validation_retries=1` |
| `test_max_retries_exceeded_returns_error` | 3 invalid attempts → `validation_error` in result |
| `test_native_response_format_openai` | OpenAI provider uses `response_format` param |
| `test_no_response_model_unchanged` | Without param → identical behavior to before |
| `test_anthropic_fallback_reprompt` | Anthropic provider uses re-prompting |

### 5.3 Fixtures Required

```python
# conftest.py
@pytest.fixture
def sample_response_model():
    class TaskResponse(BaseModel):
        title: str
        priority: Literal["high", "normal", "low"]
        tags: List[str] = []
    return TaskResponse
```

---

## 6. Success Criteria

| Metric | Target |
|--------|--------|
| Validation latency overhead | <50ms per attempt |
| Native format adoption | 100% for OpenAI-compatible providers |
| Retry success rate | >90% on second attempt |
| Backward compatibility | 100% — existing tests pass unchanged |
| Test coverage (new code) | ≥90% |

---

## 7. File Structure

```
backend/
├── core/
│   └── response_validator.py          # NEW: ResponseValidator class
├── services/
│   └── model_provider.py              # UPDATED: retry_with_validation(), provider changes
└── schemas/
    ├── task.py                        # EXISTING: Example response models
    └── ...                            # Other response models

backend/tests/
├── unit/
│   └── test_response_validator.py     # NEW: Unit tests
└── integration/
    └── test_response_validation.py    # NEW: Integration tests

docs/superpowers/specs/
    └── 2026-08-10-output-format-schema-compliance-design.md  # THIS FILE
```

---

## 8. Dependencies

- **Existing**: `pydantic` (already in requirements)
- **No new external dependencies** — uses stdlib + Pydantic

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Infinite re-prompt loops | Hard limit `max_validation_retries=2` (configurable) |
| Provider native format divergence | Abstract behind `provider.supports_response_format` property |
| Markdown extraction ambiguity | Only extract from ```json fences, not ``` or ```python |
| Large response validation cost | Validate only final response, not intermediate tool turns |
| Breaking existing callers | `response_model` is Optional; zero overhead when None |

---

## 10. Future Extensions

| Feature | Description |
|---------|-------------|
| Streaming validation | Validate partial JSON during streaming (complex) |
| Schema inference | Auto-generate response_model from tool outputs |
| Multi-provider fallback | Try native format, fall back to re-prompt seamlessly |
| Validation metrics | Track validation failure rates per agent/model |

---

## 11. Approval

> **Design approved by:** ____________________ **Date:** __________
>
> **Implementation plan to follow:** `writing-plans` skill