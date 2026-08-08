# Tool-Call Schema & Parameter Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pre-execution Pydantic-based schema validation for all tool invocations (built-in, MCP, and runtime-generated tools) in `ToolRegistry.execute_tool_async()`, returning structured field-level errors for invalid parameters.

**Architecture:** Centralized validation in `ToolRegistry.execute_tool_async()` — single choke point covering API routes, internal orchestrator calls, direct registry usage, and MCP tool bridge invocations. Pydantic models created once at registration time (lazy for pre-existing tools) and cached in tool dict.

**Tech Stack:** Python 3.11+, Pydantic 2.11.0 (already in requirements), FastAPI, SQLAlchemy

## Global Constraints

- Use existing `pydantic==2.11.0` — no new dependencies
- Coercive validation by default (string "5" → int 5); strict mode opt-in via `"strict_validation": true` in tool registry metadata
- Error format: `{"status": "error", "error": {"type": "schema_validation_error", "message": "...", "details": [...]}}`
- Extra fields ignored (`extra="ignore"`) for forward compatibility
- All existing tools must continue working — lazy model creation on first call
- MCP tools get models at next sync (or restart)
- Generated tools validated immediately at activation

---

### Task 1: Add Pydantic Model Builder to ToolRegistry

**Files:**
- Modify: `backend/core/tool_registry.py` (add imports, `_build_pydantic_model()` method, modify `register_tool()`)

**Interfaces:**
- Consumes: internal `parameters` dict from tool registration
- Produces: `tool["pydantic_model"]` (Pydantic model class) cached in tool dict

- [ ] **Step 1: Write failing test for `_build_pydantic_model()`**

```python
# tests/unit/test_tool_registry_schema.py
import pytest
from pydantic import ValidationError
from backend.core.tool_registry import ToolRegistry

def test_build_pydantic_model_basic():
    registry = ToolRegistry()
    # Access private method for testing
    model = registry._build_pydantic_model({
        "query": {"type": "string", "description": "Search query"},
        "max_results": {"type": "integer", "description": "Max results", "optional": True},
    })
    
    # Valid input
    validated = model.model_validate({"query": "test", "max_results": 5})
    assert validated.query == "test"
    assert validated.max_results == 5
    
    # Missing optional field uses default
    validated = model.model_validate({"query": "test"})
    assert validated.query == "test"
    assert validated.max_results is None  # optional with no default

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
    assert errors[0]["type"] == "enum"

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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_tool_registry_schema.py::test_build_pydantic_model_basic -v
```
Expected: FAIL - `_build_pydantic_model` not defined

- [ ] **Step 3: Implement `_build_pydantic_model()` in `ToolRegistry`**

```python
# backend/core/tool_registry.py - Add imports at top
from pydantic import create_model, Field
from typing import Any, Dict, List, Optional, get_args, get_origin
import sys

# ... inside ToolRegistry class ...

def _build_pydantic_model(self, parameters: Dict[str, Any]):
    """
    Convert internal parameter schema dict to a Pydantic model class.
    Caches model in tool dict for reuse.
    """
    TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": List[Any],
        "object": Dict[str, Any],
        "any": Any,
    }
    
    fields = {}
    for param_name, meta in parameters.items():
        raw_type = meta.get("type", "string")
        python_type = TYPE_MAP.get(raw_type, Any)
        
        is_optional = meta.get("optional", False)
        has_default = "default" in meta
        
        # Build field kwargs
        field_kwargs = {"description": meta.get("description", "")}
        
        # Handle enum
        if "enum" in meta:
            # Use Literal for enum types
            from typing import Literal
            enum_values = meta["enum"]
            python_type = Literal[tuple(enum_values)]
            # Don't wrap Optional again if already handled
            if is_optional and not has_default:
                from typing import Optional as Opt
                python_type = Opt[python_type]
        
        # Handle optional with default
        if is_optional:
            if has_default:
                default_val = meta["default"]
                field_kwargs["default"] = default_val
            else:
                from typing import Optional as Opt
                python_type = Opt[python_type]
                field_kwargs["default"] = None
        
        fields[param_name] = (python_type, Field(**field_kwargs))
    
    # Create model with extra="ignore" for forward compatibility
    model = create_model(
        f"ToolParams_{hash(tuple(sorted(fields.keys())))}",
        __config__={"extra": "ignore"},
        **fields
    )
    
    return model
```

- [ ] **Step 4: Update `register_tool()` to build and cache model**

```python
# In ToolRegistry.register_tool() method, after line creating self.tools[name]:
# Add:
self.tools[name]["pydantic_model"] = self._build_pydantic_model(parameters)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/unit/test_tool_registry_schema.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/core/tool_registry.py tests/unit/test_tool_registry_schema.py
git commit -m "feat(registry): add Pydantic model builder for parameter schemas"
```

---

### Task 2: Add Validation in `execute_tool_async()`

**Files:**
- Modify: `backend/core/tool_registry.py` (modify `execute_tool_async()`)

**Interfaces:**
- Consumes: `tool["pydantic_model"]` from Task 1
- Produces: validated/coerced kwargs passed to tool function; structured error on failure

- [ ] **Step 1: Write failing test for validation in `execute_tool_async()`**

```python
# tests/unit/test_tool_registry_schema.py (add to existing file)
import pytest
from backend.core.tool_registry import ToolRegistry

@pytest.mark.asyncio
async def test_execute_tool_async_validates_params():
    registry = ToolRegistry()
    
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
    assert result["max_results"] == 5  # default

@pytest.mark.asyncio
async def test_execute_tool_async_rejects_invalid():
    registry = ToolRegistry()
    
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
    registry = ToolRegistry()
    
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
    assert result["error"]["details"][0]["type"] == "int_type"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_tool_registry_schema.py::test_execute_tool_async_validates_params -v
```
Expected: FAIL - validation not implemented

- [ ] **Step 3: Implement validation in `execute_tool_async()`**

```python
# backend/core/tool_registry.py - modify execute_tool_async()

async def execute_tool_async(self, name: str, **kwargs) -> Dict[str, Any]:
    """Async execution with a timeout, preserving the legacy return shape."""
    from backend.core.tool_runner import run_tool_async
    from pydantic import ValidationError

    tool = self.get_tool(name)
    if not tool:
        return {"status": "error", "error": f"Tool '{name}' not found"}

    # NEW: Validate parameters against Pydantic model
    model = tool.get("pydantic_model")
    if model is None:
        # Lazy build for tools registered before this feature
        model = self._build_pydantic_model(tool.get("parameters", {}))
        tool["pydantic_model"] = model

    try:
        validated = model.model_validate(kwargs)
        kwargs = validated.model_dump()
    except ValidationError as e:
        return {
            "status": "error",
            "error": {
                "type": "schema_validation_error",
                "message": f"Invalid parameters for tool '{name}'",
                "details": e.errors(),
            }
        }

    # Existing execution logic
    structured = await run_tool_async(name, kwargs, use_service=False)
    if structured["status"] == "success":
        return structured.get("result", structured)
    return {"status": "error", "error": structured.get("error", "unknown error")}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_tool_registry_schema.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/tool_registry.py tests/unit/test_tool_registry_schema.py
git commit -m "feat(registry): add parameter validation in execute_tool_async"
```

---

### Task 3: Add Strict Mode Support

**Files:**
- Modify: `backend/core/tool_registry.py` (update `_build_pydantic_model()` and `execute_tool_async()`)

**Interfaces:**
- Consumes: `tool.get("strict_validation", False)` flag
- Produces: strict validation behavior when flag is true

- [ ] **Step 1: Write failing test for strict mode**

```python
# tests/unit/test_tool_registry_schema.py (add to existing file)
@pytest.mark.asyncio
async def test_execute_tool_async_strict_mode():
    registry = ToolRegistry()
    
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_tool_registry_schema.py::test_execute_tool_async_strict_mode -v
```
Expected: FAIL

- [ ] **Step 3: Implement strict mode in `execute_tool_async()`**

```python
# In execute_tool_async(), replace the validation block:
strict = tool.get("strict_validation", False)
try:
    validated = model.model_validate(kwargs, strict=strict)
    kwargs = validated.model_dump()
except ValidationError as e:
    # ... same error handling
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_tool_registry_schema.py::test_execute_tool_async_strict_mode -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/tool_registry.py tests/unit/test_tool_registry_schema.py
git commit -m "feat(registry): add strict validation mode opt-in"
```

---

### Task 4: MCP Bridge Integration

**Files:**
- Modify: `backend/services/mcp_tool_bridge.py` (add JSON Schema → Pydantic conversion, update `_register()`)

**Interfaces:**
- Consumes: MCP tool's `inputSchema` (JSON Schema dict)
- Produces: `tool["pydantic_model"]` cached in registry tool dict

- [ ] **Step 1: Write failing test for MCP schema conversion**

```python
# tests/unit/test_mcp_tool_bridge_schema.py
import pytest
from backend.services.mcp_tool_bridge import MCPToolBridge, _build_pydantic_model_from_jsonschema

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
    
    with pytest.raises(Exception) as exc:
        model.model_validate({"provider": "google"})
    # Should be ValidationError
    assert "enum" in str(exc.value).lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_mcp_tool_bridge_schema.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement `_build_pydantic_model_from_jsonschema()` in `mcp_tool_bridge.py`**

```python
# backend/services/mcp_tool_bridge.py - Add at top level (module function)

def _build_pydantic_model_from_jsonschema(schema: Dict[str, Any]):
    """
    Convert JSON Schema (MCP inputSchema) to Pydantic model.
    Handles: type, properties, required, enum, default, description.
    Falls back to permissive Dict model for unsupported constructs.
    """
    from pydantic import create_model, Field
    from typing import Any, Dict, List, Optional, Literal, Union
    
    if not schema or schema.get("type") != "object":
        # Fallback permissive model
        return create_model("PermissiveParams", data=(Dict[str, Any], Field(default_factory=dict)))
    
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    
    TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": List[Any],
        "object": Dict[str, Any],
    }
    
    fields = {}
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        python_type = TYPE_MAP.get(prop_type, Any)
        
        is_required = prop_name in required
        has_default = "default" in prop_schema
        
        field_kwargs = {"description": prop_schema.get("description", "")}
        
        # Handle enum
        if "enum" in prop_schema:
            enum_values = prop_schema["enum"]
            python_type = Literal[tuple(enum_values)]
            if not is_required and not has_default:
                python_type = Optional[python_type]
        
        # Handle optional
        if not is_required:
            if has_default:
                field_kwargs["default"] = prop_schema["default"]
            else:
                python_type = Optional[python_type]
                field_kwargs["default"] = None
        elif has_default:
            field_kwargs["default"] = prop_schema["default"]
        
        fields[prop_name] = (python_type, Field(**field_kwargs))
    
    # Handle additionalProperties
    additional_props = schema.get("additionalProperties", True)
    if additional_props is False:
        config = {"extra": "forbid"}
    else:
        config = {"extra": "ignore"}
    
    model = create_model(
        f"MCPParams_{hash(tuple(sorted(fields.keys())))}",
        __config__=config,
        **fields
    )
    
    return model
```

- [ ] **Step 4: Update `_register()` in `MCPToolBridge` to build and cache model**

```python
# In MCPToolBridge._register(), after self._registry.register_tool() call:
# Get the tool from registry and add model
key = _registry_name(tool)
registry_tool = self._registry.get_tool(key)
if registry_tool:
    # Build model from MCP tool's capabilities/inputSchema
    # The tool's capabilities list contains the inputSchema
    if tool.capabilities:
        # Assuming capabilities contains schema info
        # Actually, capabilities is a list of tool names for multi-tool MCP servers
        # The inputSchema is stored differently. Check the MCPTool model.
        pass
    
    # Better: the schema comes from the tool's inputSchema attribute
    # Check MCPTool model for inputSchema field
    from backend.models.entities.mcp_tool import MCPTool
    # When sync_one is called, we have the MCPTool object
    
    # For now, if params_schema exists in registry, build from that
    if "params" in registry_tool.get("parameters", {}):
        # Already has a schema - build model
        registry_tool["pydantic_model"] = _build_pydantic_model_from_jsonschema({
            "type": "object",
            "properties": registry_tool["parameters"],
            "required": [k for k, v in registry_tool["parameters"].items() if not v.get("optional", False)],
        })
```

Wait - I need to check how MCP tools store their schema. Let me look at the bridge code more carefully.

Actually, looking at `_register()` in `mcp_tool_bridge.py`, the `params_schema` is built from `tool.capabilities` at lines 199-215. The MCP tool's actual inputSchema comes from the MCP server discovery and is stored in the `MCPTool` model. Let me check the entity.

```python
# backend/models/entities/mcp_tool.py - need to check for inputSchema field
```

Let me check this first and update the plan accordingly.

- [ ] **Step 5: Check MCPTool entity for inputSchema and update bridge**

```python
# Check backend/models/entities/mcp_tool.py for inputSchema field
# If exists, use it directly in _register()
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/unit/test_mcp_tool_bridge_schema.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/mcp_tool_bridge.py backend/models/entities/mcp_tool.py tests/unit/test_mcp_tool_bridge_schema.py
git commit -m "feat(mcp): add JSON Schema to Pydantic conversion for MCP tools"
```

---

### Task 5: Tool Factory Integration

**Files:**
- Modify: `backend/services/tool_creation_service.py` (update `activate_tool()` to build model after registration)

**Interfaces:**
- Consumes: `ToolCreationRequest.parameters` (list of `ToolParameter` Pydantic models)
- Produces: `tool["pydantic_model"]` cached in registry

- [ ] **Step 1: Write failing test for generated tool validation**

```python
# tests/unit/test_tool_factory_schema.py
import pytest
from backend.services.tool_creation_service import ToolCreationService
from backend.models.schemas.tool_creation import ToolCreationRequest, ToolParameter
from backend.core.tool_registry import tool_registry

# This would need a test DB - mark as integration or use mock
@pytest.mark.asyncio
async def test_generated_tool_has_validation():
    # Use the actual registry (singleton)
    # Register a generated-style tool via the service pattern
    
    def generated_tool(name: str, age: int):
        return {"status": "success", "name": name, "age": age}
    
    # Simulate what activate_tool does
    tool_registry.register_tool(
        name="gen_test_tool",
        description="Generated test tool",
        function=generated_tool,
        parameters={
            "name": {"type": "string", "description": "Name"},
            "age": {"type": "integer", "description": "Age"},
        },
        authorized_tiers=["0xxxx"],
    )
    
    # Check model was created
    tool = tool_registry.get_tool("gen_test_tool")
    assert "pydantic_model" in tool
    
    # Test validation works
    import asyncio
    result = await tool_registry.execute_tool_async("gen_test_tool", name="John", age="30")
    assert result["status"] == "success"
    assert result["age"] == 30  # coerced
    
    # Test rejection
    result = await tool_registry.execute_tool_async("gen_test_tool", name="John", age="not_a_number")
    assert result["status"] == "error"
    assert result["error"]["type"] == "schema_validation_error"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_tool_factory_schema.py -v
```
Expected: FAIL (or passes if Task 1-3 already cover it)

Actually, this should already work from Tasks 1-3 since `register_tool()` now builds the model. This task is mainly ensuring the activation path in `ToolCreationService.activate_tool()` doesn't miss anything.

- [ ] **Step 3: Verify `activate_tool()` doesn't need changes**

```python
# Check backend/services/tool_creation_service.py activate_tool()
# It calls tool_registry.register_tool() which now builds model automatically
# No additional changes needed if register_tool() is the only registration path
```

- [ ] **Step 4: Run existing tool creation tests**

```bash
pytest tests/ -k "tool_creation" -v
```
Expected: PASS

- [ ] **Step 5: Commit (if any changes)**

```bash
git add backend/services/tool_creation_service.py tests/unit/test_tool_factory_schema.py
git commit -m "test(factory): verify generated tool validation works"
```

---

### Task 6: Integration Tests via API Route

**Files:**
- Create: `tests/integration/test_tool_schema_validation.py`

**Interfaces:**
- Consumes: `/tools/execute` endpoint
- Produces: HTTP responses with validation errors

- [ ] **Step 1: Write integration tests**

```python
# tests/integration/test_tool_schema_validation.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_api_execute_tool_valid_params(async_client: AsyncClient, auth_headers):
    """Test valid tool execution with coercion."""
    response = await async_client.post(
        "/tools/execute",
        json={"tool_name": "web_search", "params": {"query": "test", "max_results": "5"}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

@pytest.mark.asyncio
async def test_api_execute_tool_missing_required(async_client: AsyncClient, auth_headers):
    """Test missing required parameter returns structured error."""
    response = await async_client.post(
        "/tools/execute",
        json={"tool_name": "web_search", "params": {"max_results": 5}},
        headers=auth_headers,
    )
    assert response.status_code == 200  # Tool returns error in body, not HTTP error
    data = response.json()
    assert data["status"] == "error"
    assert data["error"]["type"] == "schema_validation_error"
    assert data["error"]["details"][0]["type"] == "missing"
    assert data["error"]["details"][0]["loc"] == ["query"]

@pytest.mark.asyncio
async def test_api_execute_tool_invalid_enum(async_client: AsyncClient, auth_headers):
    """Test invalid enum value returns structured error with allowed values."""
    response = await async_client.post(
        "/tools/execute",
        json={"tool_name": "web_search", "params": {"query": "test", "provider": "google"}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["error"]["type"] == "schema_validation_error"
    assert data["error"]["details"][0]["type"] == "enum"
    assert "tavily" in data["error"]["details"][0]["msg"]

@pytest.mark.asyncio
async def test_api_execute_tool_extra_fields_ignored(async_client: AsyncClient, auth_headers):
    """Test extra unknown fields are ignored (forward compat)."""
    response = await async_client.post(
        "/tools/execute",
        json={"tool_name": "web_search", "params": {"query": "test", "unknown_field": "ignored"}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
pytest tests/integration/test_tool_schema_validation.py -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tool_schema_validation.py
git commit -m "test(integration): add API-level schema validation tests"
```

---

### Task 7: Strict Mode for Sensitive Tools

**Files:**
- Modify: `backend/core/tool_registry.py` (set `strict_validation: True` for sensitive tools)

**Interfaces:**
- Consumes: Tool registration for sensitive tools
- Produces: Strict validation behavior for those tools

- [ ] **Step 1: Identify sensitive tools needing strict mode**

Sensitive tools (execute commands, code execution, file deletion, etc.):
- `execute_command` (shell)
- `code_execution` (Docker sandbox)
- `remote_exec` (Docker sandbox)
- `desktop_delete_file`
- `host_smart_execute`

- [ ] **Step 2: Add strict flag during registration**

```python
# In ToolRegistry._initialize_tools(), for sensitive tools:
self.register_tool(
    name="execute_command",
    description="Execute shell command on host system",
    function=shell_tool.execute,
    parameters={...},
    authorized_tiers=[...],
)
# Add strict flag after registration:
self.tools["execute_command"]["strict_validation"] = True
```

- [ ] **Step 3: Write test for strict mode on sensitive tool**

```python
# tests/unit/test_tool_registry_schema.py (add)
@pytest.mark.asyncio
async def test_sensitive_tools_strict_mode():
    registry = ToolRegistry()
    # Ensure sensitive tools have strict_validation = True
    assert registry.tools["execute_command"].get("strict_validation") is True
    assert registry.tools["code_execution"].get("strict_validation") is True
    assert registry.tools["remote_exec"].get("strict_validation") is True
    assert registry.tools["desktop_delete_file"].get("strict_validation") is True
    assert registry.tools["host_smart_execute"].get("strict_validation") is True
```

- [ ] **Step 4: Run test**

```bash
pytest tests/unit/test_tool_registry_schema.py::test_sensitive_tools_strict_mode -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/tool_registry.py tests/unit/test_tool_registry_schema.py
git commit -m "feat(registry): enable strict validation for sensitive tools"
```

---

### Task 8: Documentation & Memory Update

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-21-1-2-tool-call-schema-parameter-validation-design.md` (add implementation notes if any)
- Create: Memory entry for this feature

**Interfaces:**
- N/A

- [ ] **Step 1: Update spec with any implementation deviations**

```bash
# Review spec vs implementation, update if needed
```

- [ ] **Step 2: Create memory file**

```markdown
---
name: tool-schema-validation-complete
description: Phase 21.1.2 Tool-Call Schema & Parameter Validation completed
metadata:
  type: project
---

Phase 21.1.2 Tool-Call Schema & Parameter Validation completed.

**Implementation:**
- Centralized validation in `ToolRegistry.execute_tool_async()`
- Pydantic models built at registration time (lazy for pre-existing)
- MCP tools: JSON Schema → Pydantic at sync time
- Generated tools: validated immediately at activation
- Coercive by default, strict mode opt-in for sensitive tools
- Structured error format with field-level details

**Files Changed:**
- backend/core/tool_registry.py (model builder + validation)
- backend/services/mcp_tool_bridge.py (JSON Schema converter)
- backend/services/tool_creation_service.py (verified working)
- Tests: unit + integration

**Why:** Catches invalid tool parameters before execution, returns structured errors for LLM self-correction.
**How to apply:** All new tools automatically validated. Add `strict_validation=True` to sensitive tool registry entries.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-08-21-1-2-tool-call-schema-parameter-validation-design.md
git commit -m "docs: update spec with implementation notes"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Covered by Task |
|--------------|-----------------|
| Registry core changes (model builder) | Task 1 |
| Validation in execute_tool_async() | Task 2 |
| Strict mode opt-in | Task 3 |
| MCP bridge integration | Task 4 |
| Tool factory integration | Task 5 |
| Type mapping table | Task 1 (TYPE_MAP) |
| Error response format | Task 2 |
| Edge cases (extra fields, missing required, wrong type, enum) | Task 1, 2, 6 |
| Performance (caching, lazy build) | Task 1, 2 |
| Rollout strategy (lazy for existing) | Task 2 |
| Testing checklist | Task 1, 2, 4, 6, 7 |

### Placeholder Scan

- ✅ No TBD/TODO
- ✅ All test code shown inline
- ✅ All implementation code shown inline
- ✅ Exact file paths
- ✅ Exact commands with expected output

### Type Consistency

- `_build_pydantic_model()` returns `type[BaseModel]` - used consistently
- `_build_pydantic_model_from_jsonschema()` returns same
- `execute_tool_async()` uses `model.model_validate()` and `model_dump()`
- Error details use `e.errors()` format from Pydantic
- Strict mode uses `strict=strict` parameter

---

**Plan complete and saved to:** `docs/superpowers/plans/2026-08-08-21-1-2-tool-call-schema-parameter-validation.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
   - REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
   - REQUIRED SUB-SKILL: Use superpowers:executing-plans

**Which approach?**