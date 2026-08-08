# 21.1.2 — Tool-Call Schema & Parameter Validation Design

## Overview

Implement pre-execution schema validation for all tool invocations (built-in, MCP, and runtime-generated tools) using Pydantic models. Invalid parameters are rejected before tool logic executes, returning structured field-level errors.

## Goals

1. **Catch invalid parameters early** — reject malformed calls at registry layer, not inside tool implementations
2. **Unified validation layer** — single choke point covering API routes, internal orchestrator calls, and direct registry usage
3. **Structured error responses** — field-level error details for debugging and LLM self-correction
4. **Type coercion** — auto-convert common LLM mistakes (string "5" → int 5) to reduce false failures
5. **Zero runtime overhead for valid calls** — Pydantic models cached at registration time

## Non-Goals

- Runtime schema discovery (all schemas are static at registration)
- Validation of tool *outputs* (only inputs)
- Replacing per-tool business logic validation (e.g., "file must exist")

---

## Architecture

### Validation Point

**Centralized in `ToolRegistry.execute_tool_async()`** — the single async execution entry point used by:
- `/tools/execute` API route
- Internal `run_tool_async()` (tool_runner.py)
- Direct `tool_registry.execute_tool_async()` calls
- MCP tool bridge invocations

### Pydantic Model Creation

At **tool registration time** (`ToolRegistry.register_tool()`):
1. Convert internal `parameters` dict → Pydantic model via `pydantic.create_model()`
2. Cache model in tool dict: `tool["pydantic_model"] = ModelClass`
3. Cache required-field list for fast-path check

At **MCP tool sync time** (`MCPToolBridge.sync_one()`):
1. Convert MCP `inputSchema` (JSON Schema) → Pydantic model
2. Cache in tool dict

At **generated tool activation** (`ToolCreationService.activate_tool()`):
1. Build model from `ToolCreationRequest.parameters` (already Pydantic `ToolParameter` list)
2. Cache in tool dict

### Validation Flow

```
execute_tool_async(name, **kwargs)
    │
    ├─► Get tool from registry
    │
    ├─► If tool has pydantic_model:
    │       try:
    │           validated = model.model_validate(kwargs)
    │           kwargs = validated.model_dump()  # coerced types
    │       except ValidationError as e:
    │           return structured_error(e)
    │
    └─► Proceed to existing execution logic
```

---

## Data Structures

### Internal Parameter Schema (Existing)

```python
# Stored in tool["parameters"]
{
    "param_name": {
        "type": "string|integer|number|boolean|array|object|any",
        "description": "...",
        "optional": bool,
        "enum": [...]  # optional
    }
}
```

### Pydantic Model (Cached)

Generated via `pydantic.create_model()` with:
- Fields matching parameter names
- Types mapped: `string→str`, `integer→int`, `number→float`, `boolean→bool`, `array→List[Any]`, `object→Dict[str, Any]`, `any→Any`
- `Optional[]` for `optional: true` params
- `Literal[...]` for `enum` params
- `Field(description="...")` for docs

### Error Response Format

```json
{
  "status": "error",
  "error": {
    "type": "schema_validation_error",
    "message": "Invalid parameters for tool 'web_search'",
    "details": [
      {
        "loc": ["max_results"],
        "msg": "Input should be a valid integer",
        "type": "int_type",
        "input": "five"
      },
      {
        "loc": ["provider"],
        "msg": "Input should be 'auto', 'tavily', 'brave', 'serpapi', or 'duckduckgo'",
        "type": "enum",
        "input": "google"
      }
    ]
  }
}
```

Matches existing `{"status": "error", "error": ...}` shape with structured `details` array.

---

## Implementation Plan

### Phase 1: Registry Core Changes (`backend/core/tool_registry.py`)

1. **Add `_build_pydantic_model()` method** — converts internal `parameters` dict to Pydantic model class
2. **Modify `register_tool()`** — build and cache `pydantic_model` in tool dict
3. **Modify `execute_tool_async()`** — validate `kwargs` against cached model before execution
4. **Add imports** — `pydantic`, `pydantic.ValidationError`

### Phase 2: MCP Bridge Integration (`backend/services/mcp_tool_bridge.py`)

1. **Add `_build_pydantic_model_from_jsonschema()`** — converts MCP `inputSchema` (JSON Schema) to Pydantic model
2. **Modify `_register()`** — build and cache model after registry registration
3. **Handle edge cases** — empty schema, `additionalProperties`, `oneOf`/`anyOf` (fallback to permissive model)

### Phase 3: Tool Factory Integration (`backend/services/tool_factory.py` / `tool_creation_service.py`)

1. **In `ToolFactory.generate_tool_file()`** — no change needed (parameters already in `ToolCreationRequest`)
2. **In `ToolCreationService.activate_tool()`** — after `tool_registry.register_tool()`, build model from `request.parameters` and cache it

### Phase 4: API Route (Optional Enhancement)

- `/tools/execute` already calls `execute_tool_async()` — validation happens automatically
- No route changes required

### Phase 5: Tests

- Unit tests for `_build_pydantic_model()` with various parameter configs
- Integration tests for validation success/failure via `/tools/execute`
- MCP tool validation tests (schema conversion)
- Generated tool validation tests

---

## Type Mapping Table

| Internal Type | JSON Schema Type | Pydantic Type | Coercion Behavior |
|---------------|------------------|---------------|-------------------|
| `string` | `string` | `str` | `"hello"` → `"hello"`, `123` → `"123"` |
| `integer` | `integer` | `int` | `"5"` → `5`, `5.0` → `5` |
| `number` | `number` | `float` | `"3.14"` → `3.14`, `5` → `5.0` |
| `boolean` | `boolean` | `bool` | `"true"` → `true`, `1` → `true`, `"false"` → `false` |
| `array` | `array` | `List[Any]` | `[1,2]` → `[1,2]`, `"[1,2]"` → error |
| `object` | `object` | `Dict[str, Any]` | `{"a":1}` → `{"a":1}`, `"{\"a\":1}"` → error |
| `any` | (none) | `Any` | Pass-through |

**Strict mode opt-in**: Tools can set `"strict_validation": true` in registry metadata to use `model_validate(..., strict=True)` — rejects coercions.

---

## Edge Cases & Handling

| Scenario | Handling |
|----------|----------|
| Extra fields in kwargs | Ignored (default Pydantic `extra="ignore"`) — allows forward-compat |
| Missing required field | ValidationError with `loc=["field"]`, `type="missing"` |
| Wrong type (non-coercible) | ValidationError with `type="int_type"`, `type="bool_type"`, etc. |
| Enum value not in list | ValidationError with `type="enum"`, shows allowed values |
| MCP tool with no `inputSchema` | Fallback permissive model: `params: Dict[str, Any]` |
| Generated tool with no parameters | Empty model — validates `{}` only |
| Tool registered before this feature | `_build_pydantic_model()` called lazily on first `execute_tool_async()` call if missing |

---

## Performance

- **Model creation**: Once per tool at registration (lazy for pre-existing tools)
- **Validation**: ~1-2μs per call (Pydantic v2 is fast)
- **Memory**: ~1-2KB per tool for model class
- **No impact** on valid calls beyond single `model_validate()` call

---

## Rollout Strategy

1. **Deploy registry changes** — all existing tools get models lazily on first call
2. **Deploy MCP bridge changes** — MCP tools get models at next sync (or restart)
3. **Deploy tool factory changes** — new generated tools validated immediately
4. **Monitor** — watch for validation errors in logs; adjust coercion if needed
5. **Optional**: Enable strict mode for sensitive tools (`execute_command`, `code_execution`)

---

## Testing Checklist

- [ ] Built-in tool with valid params → succeeds
- [ ] Built-in tool with missing required param → structured error
- [ ] Built-in tool with wrong type (coercible) → succeeds with coerced value
- [ ] Built-in tool with wrong type (non-coercible) → structured error
- [ ] Built-in tool with invalid enum value → structured error with allowed values
- [ ] MCP tool with valid params → succeeds
- [ ] MCP tool with invalid params → structured error
- [ ] Generated tool with valid params → succeeds
- [ ] Generated tool with invalid params → structured error
- [ ] Extra unknown params ignored → succeeds
- [ ] Strict mode tool rejects coercion → error
- [ ] Pre-existing tool (registered before feature) → works after lazy model creation

---

## Future Enhancements (Out of Scope)

- Output schema validation
- JSON Schema export for external consumers (already via `to_openai_tools()`)
- Custom validators per-parameter (e.g., `min/max` for numbers)
- Schema versioning for generated tools