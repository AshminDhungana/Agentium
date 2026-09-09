# Tool Creation from Natural Language — Design Specification

**Date:** 2026-09-09  
**Status:** Approved  
**Related TODO Items:** 8.3.1, plus fixes for self-improvement scheduling and model tests

---

## 1. Problem Statement

The Agentium system already implements a complete Tool Creation & Marketplace pipeline (8.3.2–8.3.8):
- Tool staging with Council voting
- Marketplace publishing/importing
- Versioning with rollback
- Deprecation lifecycle
- Usage analytics

**Gap (8.3.1):** Natural language → code generation exists internally in `agent_orchestrator.py:_handle_tool_creation_request()` but is **not exposed** as a direct API/service. Only agents via orchestration can use it. Human users and scripts have no access.

**Additional Issues:**
- `SelfImprovementService.generate_auto_tools()` exists but no Celery task calls it (auto-generation never runs)
- Some model tests in `test_mcp_tool_models.py` fail due to DB setup issues

---

## 2. Solution Overview

Expose natural language tool creation via:
1. **New service:** `ToolCodeGenerationService` — extracts LLM logic for reuse
2. **New method:** `ToolCreationService.create_from_natural_language()` — orchestrates generation → proposal
3. **New REST endpoint:** `POST /tool-management/from-natural-language` — human/script access
4. **Celery task:** Weekly `generate_auto_tools` — enables self-improvement

---

## 3. Architecture

### 3.1 New Components

| Component | File | Responsibility |
|-----------|------|----------------|
| `ToolCodeGenerationService` | `backend/services/tool_code_generation.py` | LLM prompt → validated Python code body |
| `create_from_natural_language()` | `backend/services/tool_creation_service.py` | Generate → validate → propose |
| `POST /tool-management/from-natural-language` | `backend/api/routes/tool_creation.py` | REST endpoint |
| `generate_auto_tools` task | `backend/services/tasks/task_executor.py` + `celery_app.py` | Weekly auto-generation |

### 3.2 Data Flow

```
User/Agent Request
       │
       ▼
POST /tool-management/from-natural-language
       │
       ▼
ToolCreationService.create_from_natural_language(description, agent_id, tool_name?, authorized_tiers?)
       │
       ├─► ToolCodeGenerationService.generate(description, agent_id)
       │       │
       │       ├─► LLMClient.generate(system_prompt, user_message)
       │       │
       │       └─► ToolFactory.validate_tool_code() → raises if unsafe
       │
       ▼
ToolCreationRequest(tool_name, code_template, description, authorized_tiers, rationale=description, created_by_agentium_id)
       │
       ▼
ToolCreationService.propose_tool()  ← existing logic (auto-activate for Head, vote for Council/Lead)
```

---

## 4. API Specification

### 4.1 Request

```json
POST /tool-management/from-natural-language
Content-Type: application/json

{
  "description": "Create a tool that fetches a webpage and extracts all email addresses",
  "tool_name": "extract_emails_from_url",        // optional; derived from description if omitted
  "authorized_tiers": ["0xxxx", "1xxxx", "2xxxx"] // optional; defaults to creator's tier + Head
}
```

### 4.2 Response (Success — Head Agent)

```json
{
  "proposed": true,
  "tool_name": "extract_emails_from_url",
  "status": "activated",
  "activated": true,
  "version": "v1.0.0",
  "authorized_tiers": ["0xxxx", "1xxxx", "2xxxx"]
}
```

### 4.3 Response (Success — Council/Lead Agent)

```json
{
  "proposed": true,
  "tool_name": "extract_emails_from_url",
  "status": "pending_vote",
  "voting_id": "uuid",
  "requires_council_approval": true,
  "council_members": ["10001", "10002", ...]
}
```

### 4.4 Error Responses

| Code | Scenario |
|------|----------|
| 400 | Generated code failed security validation |
| 403 | Task agent (3xxxx) attempted to create tool |
| 409 | Tool name already exists (use versioning to update) |
| 500 | LLM generation failed |

---

## 5. ToolCodeGenerationService Design

### 5.1 Interface

```python
class ToolCodeGenerationService:
    def __init__(self, db: Session):
        self.db = db
        self.factory = ToolFactory()
    
    def generate(
        self,
        description: str,
        agent_id: str,
        tool_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Returns: {"code_template": str, "tool_name": str, "parameters": List[ToolParameter]}
        Raises: ValueError if generation fails or validation fails
        """
```

### 5.2 System Prompt (from existing orchestration)

```
You are the code-generation engine of an autonomous AI agent system.
Write the BODY of a Python method `execute(self, **kwargs)` for a new tool.

Rules:
- Compute the tool's output and assign it to a variable named `result` (a dict or JSON-serialisable value).
- You MAY call other already-registered tools via:
  `from backend.core.tool_registry import tool_registry` then `tool_registry.get_tool_function('<name>')(**inputs)`.
- Only use these imports: os, sys, json, re, datetime, math, typing, requests, pathlib, uuid, random, string, hashlib, time, collections, itertools, backend.
- Do NOT use eval, exec, __import__, open, input, os.system, subprocess shell calls, or file deletion.
Return ONLY Python code (the execute body). No markdown fences, no commentary.
```

### 5.3 Parameter Inference

The LLM is asked to infer parameters from the description. For now, parameters default to empty list (all via `**kwargs`). Future enhancement: structured parameter extraction.

---

## 6. Self-Improvement Scheduling Fix

### 6.1 New Celery Task

**File:** `backend/services/tasks/task_executor.py`

```python
@celery_app.task(name="agentium.tasks.task_executor.generate_auto_tools")
def generate_auto_tools():
    db = BeatSessionLocal()
    try:
        from backend.services.self_improvement_service import self_improvement_service
        return self_improvement_service.generate_auto_tools(db)
    finally:
        db.close()
```

### 6.2 Beat Schedule Entry

**File:** `backend/celery_app.py`

```python
'generate-auto-tools-weekly': {
    'task': 'agentium.tasks.task_executor.generate_auto_tools',
    'schedule': 604800.0,  # weekly (7 days)
},
```

---

## 7. Security Considerations

1. **Code Validation:** All generated code passes through `ToolFactory.validate_tool_code()` (AST-based, blocks eval/exec/open/subprocess/file deletion)
2. **Tier Enforcement:** Task agents (3xxxx) blocked at API and service layer
3. **Audit Logging:** Tool activation logged to `AuditLog` with `CONSTITUTIONAL` category
4. **Council Oversight:** Non-Head agents require Council vote before activation

---

## 8. Testing Strategy

| Test | Location | Coverage |
|------|----------|----------|
| Unit: `ToolCodeGenerationService.generate()` | `backend/tests/unit/test_tool_code_generation.py` | Mock LLM, validate output |
| Unit: `create_from_natural_language()` | `backend/tests/unit/test_tool_creation_service.py` | Mock generation, verify proposal |
| Integration: Full API flow | `backend/tests/integration/test_tool_creation_natural_language.py` | POST → generate → propose |
| Existing: Composite tools | `backend/tests/unit/test_tool_self_creation.py` | Unchanged |

---

## 9. Migration / Compatibility

- **No breaking changes** — only additive
- Existing `/propose` endpoint unchanged
- Existing `tool_creator` tool (agent-callable) unchanged
- New endpoint coexists with all current workflows

---

## 10. Implementation Order

1. Create `ToolCodeGenerationService` (extract from `agent_orchestrator`)
2. Add `create_from_natural_language()` to `ToolCreationService`
3. Add `POST /from-natural-language` route to `tool_creation.py`
4. Add `generate_auto_tools` Celery task + beat schedule
5. Fix failing model tests (`test_mcp_tool_models.py`)
6. Write unit + integration tests
7. Verify end-to-end

---

## 11. Acceptance Criteria

- [ ] Human user can POST natural language description → tool activated (Head) or voted (Council)
- [ ] Agent can call endpoint programmatically with same result
- [ ] Generated code passes security validation (AST checks)
- [ ] Weekly `generate_auto_tools` task runs and creates composite tools from patterns
- [ ] All existing tests pass + new tests added
- [ ] Model tests in `test_mcp_tool_models.py` fixed

---

## 12. Future Enhancements (Out of Scope)

- Structured parameter schema inference from natural language
- Multi-step tool creation wizard in Frontend
- Tool template library for common patterns
- Cross-instance tool sharing via federation