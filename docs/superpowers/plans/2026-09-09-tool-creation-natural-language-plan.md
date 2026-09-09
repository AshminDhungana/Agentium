# Tool Creation from Natural Language — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing LLM-based natural language → tool code generation as a public REST API endpoint, enable programmatic access, and schedule weekly self-improvement tool generation.

**Architecture:** Extract the LLM code generation logic from `agent_orchestrator.py` into a new `ToolCodeGenerationService`, add `create_from_natural_language()` to `ToolCreationService`, expose via `POST /tool-management/from-natural-language`, and add a weekly Celery task for `generate_auto_tools`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL, Pydantic

## Global Constraints

- All generated code must pass `ToolFactory.validate_tool_code()` (AST-based security validation)
- Task agents (3xxxx) blocked at both API and service layer
- Head (0xxxx) auto-activates; Council (1xxxx) / Lead (2xxxx) require Council vote
- No breaking changes to existing `/propose` endpoint or `tool_creator` tool
- Follow existing patterns in `backend/services/tool_creation_service.py` and `backend/api/routes/tool_creation.py`
- Tests must use pytest with mocks for LLM calls

---

### Task 1: Create ToolCodeGenerationService

**Files:**
- Create: `backend/services/tool_code_generation.py`
- Test: `backend/tests/unit/test_tool_code_generation.py`

**Interfaces:**
- Consumes: `backend.services.tool_factory.ToolFactory`, `backend.core.llm_client.LLMClient`, `backend.models.schemas.tool_creation.ToolParameter`
- Produces: `ToolCodeGenerationService.generate(description: str, agent_id: str, tool_name: Optional[str]) -> Dict[str, Any]` returning `{"code_template": str, "tool_name": str, "parameters": List[ToolParameter]}`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_tool_code_generation.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.tool_code_generation import ToolCodeGenerationService
from backend.models.schemas.tool_creation import ToolParameter

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.agentium_id = "00001"
    return agent

@pytest.fixture
def mock_llm_client():
    with patch("backend.services.tool_code_generation.LLMClient") as mock:
        client_instance = AsyncMock()
        client_instance.generate = AsyncMock(return_value={
            "content": "result = {'emails': ['test@example.com']}"
        })
        mock.return_value = client_instance
        yield client_instance

def test_generate_returns_code_template_and_tool_name(mock_db, mock_agent, mock_llm_client):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class, \
         patch("backend.services.tool_code_generation.ToolFactory") as mock_factory_class:
        
        mock_llm_class.return_value = mock_llm_client
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCodeGenerationService(mock_db)
        result = service.generate(
            description="Extract emails from a webpage",
            agent_id="00001",
            tool_name="extract_emails"
        )
        
        assert "code_template" in result
        assert result["tool_name"] == "extract_emails"
        assert isinstance(result["parameters"], list)
        mock_llm_client.generate.assert_called_once()
        mock_factory.validate_tool_code.assert_called_once()

def test_generate_derives_tool_name_from_description(mock_db, mock_agent, mock_llm_client):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class, \
         patch("backend.services.tool_code_generation.ToolFactory") as mock_factory_class:
        
        mock_llm_class.return_value = mock_llm_client
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCodeGenerationService(mock_db)
        result = service.generate(
            description="Fetch a webpage and extract all email addresses",
            agent_id="00001"
        )
        
        assert result["tool_name"] == "fetch_webpage_extract_emails"

def test_generate_raises_on_validation_failure(mock_db, mock_agent, mock_llm_client):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class, \
         patch("backend.services.tool_code_generation.ToolFactory") as mock_factory_class:
        
        mock_llm_class.return_value = mock_llm_client
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": False, "error": "Dangerous construct: eval()"}
        mock_factory_class.return_value = mock_factory
        
        service = ToolCodeGenerationService(mock_db)
        
        with pytest.raises(ValueError, match="Dangerous construct: eval"):
            service.generate(
                description="Run eval on user input",
                agent_id="00001"
            )

def test_generate_raises_on_llm_failure(mock_db, mock_agent):
    with patch("backend.services.tool_code_generation.LLMClient") as mock_llm_class:
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(side_effect=Exception("LLM unavailable"))
        mock_llm_class.return_value = mock_client
        
        service = ToolCodeGenerationService(mock_db)
        
        with pytest.raises(ValueError, match="Code generation failed"):
            service.generate(
                description="Simple tool",
                agent_id="00001"
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /app && python -m pytest backend/tests/unit/test_tool_code_generation.py -v --no-cov`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.services.tool_code_generation'"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/tool_code_generation.py
"""
Tool Code Generation Service
Extracts natural language → code generation logic from agent_orchestrator
for reuse by API endpoints and self-improvement workflows.
"""
import re
from typing import Dict, Any, List, Optional
from textwrap import dedent

from sqlalchemy.orm import Session
from backend.services.tool_factory import ToolFactory
from backend.core.llm_client import LLMClient
from backend.models.schemas.tool_creation import ToolParameter


class ToolCodeGenerationService:
    """
    Generates validated Python tool code from natural language descriptions.
    
    Reuses the system prompt and validation logic previously embedded in
    AgentOrchestrator._handle_tool_creation_request().
    """
    
    SYSTEM_PROMPT = (
        "You are the code-generation engine of an autonomous AI agent system. "
        "Write the BODY of a Python method `execute(self, **kwargs)` for a new tool.\n"
        "Rules:\n"
        "- Compute the tool's output and assign it to a variable named `result` "
        "(a dict or JSON-serialisable value).\n"
        "- You MAY call other already-registered tools via "
        "`from backend.core.tool_registry import tool_registry` then "
        "`tool_registry.get_tool_function('<name>')(**inputs)`.\n"
        "- Only use these imports: os, sys, json, re, datetime, math, typing, "
        "requests, pathlib, uuid, random, string, hashlib, time, collections, "
        "itertools, backend.\n"
        "- Do NOT use eval, exec, __import__, open, input, os.system, "
        "subprocess shell calls, or file deletion.\n"
        "Return ONLY Python code (the execute body). No markdown fences, no commentary."
    )
    
    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.factory = ToolFactory()
        self.llm_client = LLMClient(db=db)
    
    def generate(
        self,
        description: str,
        agent_id: str,
        tool_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate tool code from natural language description.
        
        Args:
            description: Natural language description of desired tool functionality
            agent_id: Agentium ID of the requesting agent (used for tier context)
            tool_name: Optional explicit tool name; derived from description if omitted
            
        Returns:
            Dict with keys: code_template (str), tool_name (str), parameters (List[ToolParameter])
            
        Raises:
            ValueError: If LLM generation fails or code fails security validation
        """
        # Derive tool name from description if not provided
        if tool_name is None:
            tool_name = self._derive_tool_name(description)
        
        # Get agent for LLM client
        agent = self._get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")
        
        # Generate code via LLM
        try:
            gen = self.llm_client.generate(
                agent=agent,
                user_message=(
                    f"The agent wants to create a tool named '{tool_name}'.\n"
                    f"Request: {description}\n\n"
                    "Return the execute() body that fulfills this request."
                ),
                system_prompt_override=self.SYSTEM_PROMPT,
            )
            raw_code = (gen or {}).get("content", "") or ""
        except Exception as exc:
            raise ValueError(f"Code generation failed: {exc}")
        
        # Clean up markdown fences if present
        code_template = self._clean_code(raw_code)
        
        if not code_template.strip():
            raise ValueError("Code generation produced empty implementation")
        
        # Validate generated code for security
        validation = self.factory.validate_tool_code(code_template)
        if not validation["valid"]:
            raise ValueError(f"Generated code failed validation: {validation['error']}")
        
        return {
            "code_template": code_template,
            "tool_name": tool_name,
            "parameters": []  # For now, all params via **kwargs
        }
    
    def _derive_tool_name(self, description: str) -> str:
        """Derive a valid tool name from the description."""
        # Take first 50 chars, lowercase, replace non-alphanum with underscore
        name = re.sub(r'[^a-z0-9]+', '_', description.lower()[:50]).strip('_')
        return name or "generated_tool"
    
    def _clean_code(self, raw_code: str) -> str:
        """Remove markdown fences and normalize indentation."""
        # Remove leading ```python or ``` fences
        code = re.sub(r"^```[a-zA-Z0-9]*\n", "", raw_code.strip())
        # Remove trailing ```
        code = re.sub(r"\n```$", "", code.strip())
        return dedent(code).strip()
    
    def _get_agent(self, agent_id: str):
        """Fetch agent from database."""
        from backend.models.entities.agents import Agent
        return self.db.query(Agent).filter(Agent.agentium_id == agent_id).first()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /app && python -m pytest backend/tests/unit/test_tool_code_generation.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/tool_code_generation.py backend/tests/unit/test_tool_code_generation.py
git commit -m "feat: add ToolCodeGenerationService for natural language tool creation"
```

---

### Task 2: Add create_from_natural_language to ToolCreationService

**Files:**
- Modify: `backend/services/tool_creation_service.py`
- Test: `backend/tests/unit/test_tool_creation_service.py`

**Interfaces:**
- Consumes: `ToolCodeGenerationService.generate()`, `ToolCreationService.propose_tool()`
- Produces: `ToolCreationService.create_from_natural_language(description, agent_id, tool_name=None, authorized_tiers=None) -> Dict[str, Any]` returning same structure as `propose_tool()`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_tool_creation_service.py (add to existing file)
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from backend.services.tool_creation_service import ToolCreationService
from backend.models.schemas.tool_creation import ToolCreationRequest

def test_create_from_natural_language_head_auto_activates():
    db = MagicMock()
    
    with patch("backend.services.tool_creation_service.ToolCodeGenerationService") as mock_gen_class, \
         patch("backend.services.tool_creation_service.ToolFactory") as mock_factory_class:
        
        mock_gen = MagicMock()
        mock_gen.generate.return_value = {
            "code_template": "result = {'emails': ['test@example.com']}",
            "tool_name": "extract_emails",
            "parameters": []
        }
        mock_gen_class.return_value = mock_gen
        
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        # Mock propose_tool to return auto-activated result
        with patch.object(ToolCreationService, "propose_tool", return_value={
            "proposed": True,
            "tool_name": "extract_emails",
            "status": "activated",
            "activated": True,
            "version": "v1.0.0"
        }):
            service = ToolCreationService(db)
            result = service.create_from_natural_language(
                description="Extract emails from webpage",
                agent_id="00001"
            )
        
        assert result["proposed"] is True
        assert result["tool_name"] == "extract_emails"
        assert result["status"] == "activated"

def test_create_from_natural_language_council_requires_vote():
    db = MagicMock()
    
    with patch("backend.services.tool_creation_service.ToolCodeGenerationService") as mock_gen_class, \
         patch("backend.services.tool_creation_service.ToolFactory") as mock_factory_class:
        
        mock_gen = MagicMock()
        mock_gen.generate.return_value = {
            "code_template": "result = {'data': 'test'}",
            "tool_name": "council_tool",
            "parameters": []
        }
        mock_gen_class.return_value = mock_gen
        
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        # Mock propose_tool to return vote-required result
        with patch.object(ToolCreationService, "propose_tool", return_value={
            "proposed": True,
            "tool_name": "council_tool",
            "status": "pending_vote",
            "voting_id": "vote-123",
            "requires_council_approval": True,
            "council_members": ["10001", "10002"]
        }):
            service = ToolCreationService(db)
            result = service.create_from_natural_language(
                description="Council tool",
                agent_id="10001"
            )
        
        assert result["proposed"] is True
        assert result["status"] == "pending_vote"
        assert result["requires_council_approval"] is True

def test_create_from_natural_language_blocks_task_agent():
    db = MagicMock()
    
    service = ToolCreationService(db)
    result = service.create_from_natural_language(
        description="Task agent tool",
        agent_id="30001"
    )
    
    assert result["proposed"] is False
    assert "Task agents cannot create tools" in result["error"]

def test_create_from_natural_language_passes_authorized_tiers():
    db = MagicMock()
    
    with patch("backend.services.tool_creation_service.ToolCodeGenerationService") as mock_gen_class, \
         patch("backend.services.tool_creation_service.ToolFactory") as mock_factory_class:
        
        mock_gen = MagicMock()
        mock_gen.generate.return_value = {
            "code_template": "result = {'ok': True}",
            "tool_name": "custom_tiers_tool",
            "parameters": []
        }
        mock_gen_class.return_value = mock_gen
        
        mock_factory = MagicMock()
        mock_factory.validate_tool_code.return_value = {"valid": True, "error": None}
        mock_factory_class.return_value = mock_factory
        
        with patch.object(ToolCreationService, "propose_tool") as mock_propose:
            mock_propose.return_value = {"proposed": True, "tool_name": "custom_tiers_tool", "status": "activated"}
            
            service = ToolCreationService(db)
            service.create_from_natural_language(
                description="Tool with custom tiers",
                agent_id="10001",
                authorized_tiers=["0xxxx", "1xxxx", "2xxxx"]
            )
            
            # Verify propose_tool was called with correct authorized_tiers
            call_args = mock_propose.call_args[0][0]
            assert isinstance(call_args, ToolCreationRequest)
            assert call_args.authorized_tiers == ["0xxxx", "1xxxx", "2xxxx"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /app && python -m pytest backend/tests/unit/test_tool_creation_service.py -v --no-cov -k "natural_language"`
Expected: FAIL with "AttributeError: 'ToolCreationService' object has no attribute 'create_from_natural_language'"

- [ ] **Step 3: Write minimal implementation**

Add this method to `ToolCreationService` class in `backend/services/tool_creation_service.py`:

```python
    def create_from_natural_language(
        self,
        description: str,
        agent_id: str,
        tool_name: Optional[str] = None,
        authorized_tiers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a tool from natural language description.
        
        Uses LLM to generate code, validates it, then proposes via existing workflow.
        
        Args:
            description: Natural language description of desired functionality
            agent_id: Agentium ID of requesting agent
            tool_name: Optional explicit tool name
            authorized_tiers: Optional list of authorized tiers (defaults to agent's tier + Head)
            
        Returns:
            Same structure as propose_tool(): proposed, tool_name, status, etc.
        """
        # Task agents (3xxxx) cannot create tools
        if agent_id.startswith("3"):
            return {"proposed": False, "error": "Task agents cannot create tools"}
        
        # Determine authorized tiers
        if authorized_tiers is None:
            creator_tier = f"{agent_id[0]}xxxx"
            authorized_tiers = [creator_tier, "0xxxx"]
        
        # Generate code from natural language
        from backend.services.tool_code_generation import ToolCodeGenerationService
        code_gen = ToolCodeGenerationService(self.db)
        
        try:
            gen_result = code_gen.generate(description, agent_id, tool_name)
        except ValueError as exc:
            return {"proposed": False, "error": str(exc)}
        
        # Build ToolCreationRequest
        request = ToolCreationRequest(
            tool_name=gen_result["tool_name"],
            description=description,
            parameters=gen_result["parameters"],
            code_template=gen_result["code_template"],
            test_cases=[],
            authorized_tiers=authorized_tiers,
            created_by_agentium_id=agent_id,
            rationale=description,
        )
        
        # Propose via existing workflow
        return self.propose_tool(request)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /app && python -m pytest backend/tests/unit/test_tool_creation_service.py -v --no-cov -k "natural_language"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/tool_creation_service.py backend/tests/unit/test_tool_creation_service.py
git commit -m "feat: add create_from_natural_language to ToolCreationService"
```

---

### Task 3: Add POST /from-natural-language Endpoint

**Files:**
- Modify: `backend/api/routes/tool_creation.py`
- Test: `backend/tests/integration/test_tool_creation_natural_language.py`

**Interfaces:**
- Consumes: `ToolCreationService.create_from_natural_language()`
- Produces: `POST /tool-management/from-natural-language` endpoint returning JSON response

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_tool_creation_natural_language.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}

def test_from_natural_language_head_activates(auth_headers):
    with patch("backend.api.routes.tool_creation.get_current_active_user", return_value={"id": "00001"}), \
         patch("backend.api.routes.tool_creation.get_current_agent_id", return_value="00001"), \
         patch("backend.api.routes.tool_creation.get_current_agent_tier", return_value="0xxxx"), \
         patch("backend.api.routes.tool_creation.ToolCreationService") as mock_service_class:
        
        mock_service = MagicMock()
        mock_service.create_from_natural_language.return_value = {
            "proposed": True,
            "tool_name": "extract_emails",
            "status": "activated",
            "activated": True,
            "version": "v1.0.0",
            "authorized_tiers": ["0xxxx", "1xxxx", "2xxxx"]
        }
        mock_service_class.return_value = mock_service
        
        response = client.post(
            "/tool-management/from-natural-language",
            json={
                "description": "Extract emails from a webpage",
                "authorized_tiers": ["0xxxx", "1xxxx", "2xxxx"]
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["proposed"] is True
        assert data["tool_name"] == "extract_emails"
        assert data["status"] == "activated"

def test_from_natural_language_council_requires_vote(auth_headers):
    with patch("backend.api.routes.tool_creation.get_current_active_user", return_value={"id": "10001"}), \
         patch("backend.api.routes.tool_creation.get_current_agent_id", return_value="10001"), \
         patch("backend.api.routes.tool_creation.get_current_agent_tier", return_value="1xxxx"), \
         patch("backend.api.routes.tool_creation.ToolCreationService") as mock_service_class:
        
        mock_service = MagicMock()
        mock_service.create_from_natural_language.return_value = {
            "proposed": True,
            "tool_name": "council_tool",
            "status": "pending_vote",
            "voting_id": "vote-123",
            "requires_council_approval": True,
            "council_members": ["10001", "10002"]
        }
        mock_service_class.return_value = mock_service
        
        response = client.post(
            "/tool-management/from-natural-language",
            json={"description": "Council tool description"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending_vote"
        assert data["requires_council_approval"] is True

def test_from_natural_language_blocks_task_agent(auth_headers):
    with patch("backend.api.routes.tool_creation.get_current_active_user", return_value={"id": "30001"}), \
         patch("backend.api.routes.tool_creation.get_current_agent_id", return_value="30001"), \
         patch("backend.api.routes.tool_creation.get_current_agent_tier", return_value="3xxxx"):
        
        response = client.post(
            "/tool-management/from-natural-language",
            json={"description": "Task agent tool"},
            headers=auth_headers
        )
        
        assert response.status_code == 403
        assert "Task agents cannot create tools" in response.json()["detail"]

def test_from_natural_language_validation_error(auth_headers):
    with patch("backend.api.routes.tool_creation.get_current_active_user", return_value={"id": "00001"}), \
         patch("backend.api.routes.tool_creation.get_current_agent_id", return_value="00001"), \
         patch("backend.api.routes.tool_creation.get_current_agent_tier", return_value="0xxxx"), \
         patch("backend.api.routes.tool_creation.ToolCreationService") as mock_service_class:
        
        mock_service = MagicMock()
        mock_service.create_from_natural_language.return_value = {
            "proposed": False,
            "error": "Generated code failed validation: Dangerous construct: eval()"
        }
        mock_service_class.return_value = mock_service
        
        response = client.post(
            "/tool-management/from-natural-language",
            json={"description": "Run eval on input"},
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "eval" in response.json()["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /app && python -m pytest backend/tests/integration/test_tool_creation_natural_language.py -v --no-cov`
Expected: FAIL with 404 Not Found (endpoint doesn't exist)

- [ ] **Step 3: Write minimal implementation**

Add to `backend/api/routes/tool_creation.py`:

```python
# Add near top with other request models (after line ~115)
class FromNaturalLanguageRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=5000, description="Natural language description of the tool")
    tool_name: Optional[str] = Field(None, max_length=100, description="Optional explicit tool name")
    authorized_tiers: Optional[List[str]] = Field(None, description="Authorized agent tiers")

# Add new route after the /propose endpoint (around line ~150)
@router.post(
    "/from-natural-language",
    summary="Create Tool from Natural Language",
    description="Generate a tool from a natural language description. Head (0xxxx) auto-activates; Council (1xxxx)/Lead (2xxxx) trigger Council vote. Task agents (3xxxx) blocked.",
    responses=build_responses(None),
)
async def create_tool_from_natural_language(
    request: FromNaturalLanguageRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """
    Create a tool from natural language description.
    
    - Head (0xxxx): auto-approved and activated immediately
    - Council (1xxxx) / Lead (2xxxx): triggers Council vote
    - Task agents (3xxxx): blocked
    """
    _require_not_task_agent(agent_tier)
    
    service = ToolCreationService(db)
    result = service.create_from_natural_language(
        description=request.description,
        agent_id=agent_id,
        tool_name=request.tool_name,
        authorized_tiers=request.authorized_tiers,
    )
    
    if not result.get("proposed") and "error" in result:
        raise BadRequestError(error=result["error"], code="RESULTERROR")
    
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /app && python -m pytest backend/tests/integration/test_tool_creation_natural_language.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/tool_creation.py backend/tests/integration/test_tool_creation_natural_language.py
git commit -m "feat: add POST /tool-management/from-natural-language endpoint"
```

---

### Task 4: Add generate_auto_tools Celery Task

**Files:**
- Modify: `backend/services/tasks/task_executor.py`
- Modify: `backend/celery_app.py`
- Test: `backend/tests/unit/test_generate_auto_tools_task.py`

**Interfaces:**
- Consumes: `SelfImprovementService.generate_auto_tools()`
- Produces: Celery task `agentium.tasks.task_executor.generate_auto_tools` scheduled weekly

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_generate_auto_tools_task.py
import pytest
from unittest.mock import MagicMock, patch
from backend.services.tasks.task_executor import generate_auto_tools

def test_generate_auto_tools_calls_self_improvement_service():
    with patch("backend.services.tasks.task_executor.BeatSessionLocal") as mock_session_class, \
         patch("backend.services.tasks.task_executor.self_improvement_service") as mock_service:
        
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        mock_service.generate_auto_tools.return_value = {"tools_generated": 2, "patterns_analyzed": 50}
        
        result = generate_auto_tools()
        
        assert result == {"tools_generated": 2, "patterns_analyzed": 50}
        mock_service.generate_auto_tools.assert_called_once_with(mock_db)
        mock_db.close.assert_called_once()

def test_generate_auto_tools_handles_exception():
    with patch("backend.services.tasks.task_executor.BeatSessionLocal") as mock_session_class, \
         patch("backend.services.tasks.task_executor.self_improvement_service") as mock_service:
        
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        mock_service.generate_auto_tools.side_effect = Exception("DB error")
        
        # Task should handle exception gracefully and return error dict
        result = generate_auto_tools()
        
        assert "error" in result
        mock_db.close.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /app && python -m pytest backend/tests/unit/test_generate_auto_tools_task.py -v --no-cov`
Expected: FAIL with "ImportError: cannot import name 'generate_auto_tools'"

- [ ] **Step 3: Write minimal implementation**

Add to `backend/services/tasks/task_executor.py` (near other task functions):

```python
@celery_app.task(name="agentium.tasks.task_executor.generate_auto_tools")
def generate_auto_tools():
    """
    Weekly task to auto-generate tools from repeated usage patterns.
    
    Calls SelfImprovementService.generate_auto_tools() which analyzes
    tool invocation patterns and creates composite tools for sequences
    executed >= 5 times with > 90% success rate.
    """
    from backend.models.database import BeatSessionLocal
    
    db = BeatSessionLocal()
    try:
        from backend.services.self_improvement_service import self_improvement_service
        return self_improvement_service.generate_auto_tools(db)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("generate_auto_tools task failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()
```

Add to `backend/celery_app.py` in `beat_schedule` dict (around line ~180):

```python
    # ── Phase 13.4: Continuous Self-Improvement Engine ────────────────────────
    'knowledge-consolidation-weekly': {
        'task': 'agentium.tasks.task_executor.knowledge_consolidation',
        'schedule': 604800.0,
    },
    'performance-optimization-weekly': {
        'task': 'agentium.tasks.task_executor.performance_optimization',
        'schedule': 604800.0,
    },
    'generate-auto-tools-weekly': {          # ← ADD THIS
        'task': 'agentium.tasks.task_executor.generate_auto_tools',
        'schedule': 604800.0,  # weekly (7 days)
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /app && python -m pytest backend/tests/unit/test_generate_auto_tools_task.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/tasks/task_executor.py backend/celery_app.py backend/tests/unit/test_generate_auto_tools_task.py
git commit -m "feat: add generate_auto_tools weekly Celery task for self-improvement"
```

---

### Task 5: Fix Failing Model Tests

**Files:**
- Modify: `backend/tests/unit/models/test_mcp_tool_models.py` (or fix underlying DB setup)
- Test: `backend/tests/unit/models/test_mcp_tool_models.py`

**Interfaces:** N/A - fix existing tests

- [ ] **Step 1: Run failing tests to see errors**

Run: `cd /app && python -m pytest backend/tests/unit/models/test_mcp_tool_models.py -v --no-cov`
Expected: Various DB-related errors

- [ ] **Step 2: Fix test setup**

Based on errors, likely need to:
- Ensure proper DB session fixture with transaction rollback
- Add missing imports or model relationships
- Fix any schema mismatches

Example fix pattern (adapt to actual errors):

```python
# In test_mcp_tool_models.py, ensure fixtures use proper DB setup
@pytest.fixture
def db_session():
    from backend.models.database import get_db_context
    with get_db_context() as db:
        yield db

def test_mcp_tool_creation(db_session):
    # Use db_session fixture instead of creating own
    ...
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd /app && python -m pytest backend/tests/unit/models/test_mcp_tool_models.py -v --no-cov`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/models/test_mcp_tool_models.py
git commit -m "fix: resolve failing MCP tool model tests"
```

---

### Task 6: End-to-End Integration Test

**Files:**
- Create: `backend/tests/integration/test_tool_creation_natural_language_e2e.py`

**Interfaces:**
- Tests full flow: API → Service → Code Generation → Proposal → Activation

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_tool_creation_natural_language_e2e.py
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

@pytest.mark.integration
def test_full_flow_natural_language_to_activated_tool():
    """Test complete flow: POST → generate → validate → propose → activate (Head)."""
    # This requires a running DB - mark as integration test
    pass  # Implement with real DB fixture when test infrastructure ready

@pytest.mark.integration
def test_full_flow_natural_language_to_council_vote():
    """Test complete flow for Council agent: POST → generate → vote required."""
    pass
```

- [ ] **Step 2: Run test to verify it fails** (or skip until DB available)

Run: `cd /app && python -m pytest backend/tests/integration/test_tool_creation_natural_language_e2e.py -v --no-cov -k "not integration"`
Expected: SKIP or PASS (placeholder)

- [ ] **Step 3: Implement when test infrastructure ready**

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_tool_creation_natural_language_e2e.py
git commit -m "test: add e2e integration test placeholder for natural language tool creation"
```

---

### Task 7: Update Frontend (Optional - Future Enhancement)

**Files:**
- Modify: `frontend/src/pages/ToolMarketplacePage.tsx` (add "Create from Description" button)

**Note:** This is marked optional in spec. Can be done separately.

---

## Execution Order Summary

1. **Task 1:** Create `ToolCodeGenerationService` + unit tests
2. **Task 2:** Add `create_from_natural_language()` to `ToolCreationService` + unit tests  
3. **Task 3:** Add `POST /from-natural-language` endpoint + integration tests
4. **Task 4:** Add `generate_auto_tools` Celery task + beat schedule + unit tests
5. **Task 5:** Fix failing `test_mcp_tool_models.py`
6. **Task 6:** Add e2e integration test placeholder
7. **Task 7:** Frontend enhancement (optional, separate PR)

---

## Acceptance Criteria Verification

After all tasks complete, verify:

- [ ] `POST /tool-management/from-natural-language` returns activated tool for Head agent
- [ ] Same endpoint returns pending_vote for Council agent
- [ ] Task agent (3xxxx) receives 403
- [ ] Generated code with `eval()` returns 400 validation error
- [ ] `generate_auto_tools` Celery task exists and runs weekly
- [ ] All existing tests still pass
- [ ] `test_mcp_tool_models.py` tests pass