# Constitution & Governance Gap-Filling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement missing Constitution API routes, unify ethos injection into LLM prompts, and complete sovereign preferences flow per the design spec.

**Architecture:** Minimal gap-filling approach. Add new API routes file, modify existing model_provider.py to use Agent.get_system_prompt(), extend persona.py for new preferences. No schema migrations needed.

**Tech Stack:** FastAPI, SQLAlchemy, existing Constitution/Amendment/Ethos models, React frontend (already built)

---

## Global Constraints

- Python 3.11+, FastAPI, SQLAlchemy 2.0
- All API responses must match frontend TypeScript interfaces exactly
- Use existing `Constitution` model methods: `get_articles_dict()`, `get_prohibited_actions_list()`, `get_sovereign_preferences()`
- No new database migrations — all models already exist
- Follow existing route registration pattern in `main.py`
- TDD: write test first, then implementation
- Commit after each task

---

### Task 1: Create Constitution API Routes

**Files:**
- Create: `backend/api/routes/constitution.py`
- Modify: `backend/main.py` (route registration)
- Test: `backend/tests/api/test_constitution_routes.py`

**Interfaces:**
- Consumes: `Constitution` model, `get_db` dependency, `get_current_active_user` dependency
- Produces: 4 endpoints matching frontend `constitutionService` expectations

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/api/test_constitution_routes.py
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_get_constitution_returns_active():
    response = client.get("/api/v1/constitution", headers={"Authorization": "Bearer test_token"})
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "preamble" in data
    assert "articles" in data
    assert "prohibited_actions" in data
    assert "sovereign_preferences" in data
    assert "effective_date" in data
    assert "is_active" in data

def test_update_constitution_archives_old_creates_new(test_db, admin_token):
    # Setup: create initial constitution
    from backend.models.entities.constitution import Constitution
    c = Constitution(
        version="v1.0.0", version_number=1,
        preamble="Test", articles="{}", prohibited_actions="[]",
        sovereign_preferences="{}", created_by_agentium_id="00001"
    )
    test_db.add(c)
    test_db.commit()
    
    response = client.post(
        "/api/v1/constitution/update",
        json={"preamble": "Updated", "articles": {}, "prohibited_actions": [], "sovereign_preferences": {}},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["preamble"] == "Updated"
    assert data["version_number"] == 2

def test_update_constitution_rejects_empty_preamble(admin_token):
    response = client.post(
        "/api/v1/constitution/update",
        json={"preamble": "", "articles": {}, "prohibited_actions": [], "sovereign_preferences": {}},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 400

def test_preferences_endpoint_updates_sovereign_prefs(admin_token):
    response = client.post(
        "/api/v1/constitution/preferences",
        json={"communication_style": "concise", "response_format": "summary_first", "verbosity": "concise"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sovereign_preferences"]["communication_style"] == "concise"

def test_get_constitution_history_returns_list():
    response = client.get("/api/v1/constitution/history", headers={"Authorization": "Bearer test_token"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

Run: `pytest backend/tests/api/test_constitution_routes.py -v`
Expected: FAIL (routes don't exist)

- [ ] **Step 2: Create `backend/api/routes/constitution.py`**

```python
# backend/api/routes/constitution.py
"""
Constitution API routes for Agentium.
Handles constitution retrieval, updates, and sovereign preferences.
"""
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from backend.models.database import get_db
from backend.models.entities.constitution import Constitution
from backend.core.auth import get_current_active_user, get_current_admin_user
from backend.api.schemas.examples import build_responses

router = APIRouter(prefix="/constitution", tags=["constitution"])


class ConstitutionUpdate(BaseModel):
    preamble: str = Field(..., min_length=1)
    articles: Dict[str, Any] = Field(default_factory=dict)
    prohibited_actions: List[str] = Field(default_factory=list)
    sovereign_preferences: Dict[str, Any] = Field(default_factory=dict)


class PreferencesUpdate(BaseModel):
    communication_style: str = None
    response_format: str = None
    verbosity: str = None
    country_name: str = None


@router.get(
    "",
    response_model=dict,
    summary="Get Active Constitution",
    description="Returns the currently active constitution with all sections.",
    responses=build_responses(None),
)
async def get_constitution(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get the active constitution."""
    constitution = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    
    if not constitution:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    return constitution.to_dict()


@router.post(
    "/update",
    response_model=dict,
    summary="Update Constitution",
    description="Creates a new constitution version, archiving the previous one. Requires admin/sovereign.",
    responses=build_responses(None),
)
async def update_constitution(
    update: ConstitutionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    """Update constitution by creating new version."""
    if not update.preamble or not update.preamble.strip():
        raise HTTPException(status_code=400, detail="Preamble cannot be empty")
    
    # Get current active constitution
    current = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    
    if not current:
        raise HTTPException(status_code=404, detail="No active constitution to update")
    
    # Archive current
    current.archive()
    db.flush()
    
    # Create new version
    new_version_number = current.version_number + 1
    new_version = f"v{new_version_number}.0.0"
    
    import json
    new_constitution = Constitution(
        agentium_id=f"C{new_version_number:04d}",
        version=new_version,
        version_number=new_version_number,
        preamble=update.preamble,
        articles=json.dumps(update.articles),
        prohibited_actions=json.dumps(update.prohibited_actions),
        sovereign_preferences=json.dumps(update.sovereign_preferences),
        created_by_agentium_id=current.created_by_agentium_id,
        replaces_version_id=current.id,
        is_active=True,
    )
    
    db.add(new_constitution)
    db.flush()
    db.commit()
    
    return new_constitution.to_dict()


@router.post(
    "/preferences",
    response_model=dict,
    summary="Update Sovereign Preferences",
    description="Updates only the sovereign_preferences section of the active constitution.",
    responses=build_responses(None),
)
async def update_preferences(
    prefs: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    """Update sovereign preferences."""
    constitution = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    
    if not constitution:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    # Merge with existing preferences
    current_prefs = constitution.get_sovereign_preferences()
    update_data = prefs.model_dump(exclude_unset=True)
    merged = {**current_prefs, **update_data}
    
    constitution.sovereign_preferences = json.dumps(merged)
    db.commit()
    
    return constitution.to_dict()


@router.get(
    "/history",
    response_model=List[dict],
    summary="Get Constitution Amendment History",
    description="Returns history of constitutional amendments via voting service.",
    responses=build_responses(None),
)
async def get_constitution_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get amendment history."""
    from backend.services.amendment_service import AmendmentService
    
    service = AmendmentService(db)
    await service.initialize()
    history = await service.get_amendment_history(limit=limit)
    
    return history
```

- [ ] **Step 3: Register route in `backend/main.py`**

```python
# In main.py route registration section (around line 420)
# Add this import and registration:

from backend.api.routes import constitution
app.include_router(constitution.router, prefix="/api/v1")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/api/test_constitution_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/constitution.py backend/main.py backend/tests/api/test_constitution_routes.py
git commit -m "feat: add constitution API routes (GET, update, preferences, history)"
```

---

### Task 2: Unify Ethos Injection in ModelService

**Files:**
- Modify: `backend/services/model_provider.py` (generate_with_agent method)
- Test: `backend/tests/services/test_model_provider_ethos.py`

**Interfaces:**
- Consumes: `Agent.get_system_prompt(db, channel)` method
- Produces: Unified system prompt for all LLM calls

- [ ] **Step 1: Write failing test**

```python
# backend/tests/services/test_model_provider_ethos.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.model_provider import ModelService
from backend.models.entities.agents import Agent, AgentType

@pytest.mark.asyncio
async def test_generate_with_agent_uses_get_system_prompt():
    """Verify generate_with_agent calls agent.get_system_prompt with channel."""
    agent = MagicMock(spec=Agent)
    agent.agentium_id = "30001"
    agent.get_system_prompt = MagicMock(return_value="FULL PERSONA PROMPT")
    agent.ethos = MagicMock()
    agent.ethos.mission_statement = "Old mission"
    agent.ethos.behavioral_rules = '["rule1"]'
    
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="Response"))]
    ))
    
    with patch('backend.services.model_provider.get_async_client', return_value=mock_client):
        service = ModelService()
        await service.generate_with_agent(
            agent=agent,
            user_message="Test",
            channel="text",
            db=MagicMock()
        )
    
    # Verify get_system_prompt was called with channel
    agent.get_system_prompt.assert_called_once()
    call_kwargs = agent.get_system_prompt.call_args.kwargs
    assert call_kwargs.get("channel") == "text"

@pytest.mark.asyncio
async def test_generate_with_agent_voice_channel():
    """Verify voice channel gets VOICE_ADAPTATION."""
    agent = MagicMock(spec=Agent)
    agent.agentium_id = "30001"
    agent.get_system_prompt = MagicMock(return_value="VOICE PERSONA")
    agent.ethos = MagicMock()
    agent.ethos.mission_statement = "Mission"
    agent.ethos.behavioral_rules = "[]"
    
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="Response"))]
    ))
    
    with patch('backend.services.model_provider.get_async_client', return_value=mock_client):
        service = ModelService()
        await service.generate_with_agent(
            agent=agent,
            user_message="Test",
            channel="voice",
            db=MagicMock()
        )
    
    agent.get_system_prompt.assert_called_once_with(channel="voice", db=pytest.any)
```

Run: `pytest backend/tests/services/test_model_provider_ethos.py -v`
Expected: FAIL (generate_with_agent doesn't use get_system_prompt)

- [ ] **Step 2: Modify `backend/services/model_provider.py` — `generate_with_agent` method**

```python
# In model_provider.py, find generate_with_agent method (around line 2050)
# Replace the system prompt building section (lines 2080-2101) with:

# -- Build system prompt using Agent.get_system_prompt (unified) --
system_prompt = system_prompt_override
if not system_prompt:
    # Use the agent's unified system prompt builder which includes:
    # - Constitution persona (preamble, articles, prohibited, tier emphasis)
    # - Sovereign preferences (communication_style, response_format, verbosity)
    # - Ethos operational context (objective, working_method, capabilities, environment)
    system_prompt = agent.get_system_prompt(db=db, channel=channel)

# -- Hard response-length enforcement (Gap 3) ---
# Appended LAST so it cannot be overridden by ethos or caller content.
system_prompt += (
    "\n\nYour response MUST be 2-3 lines maximum. "
    "Never explain governance mechanics. "
    "Never reference internal architecture."
)
```

- [ ] **Step 3: Add `channel` parameter to `generate_with_agent` signature**

```python
# In model_provider.py, update the method signature (around line 2000):
async def generate_with_agent(
    self,
    agent: "Agent",
    user_message: str,
    history: List[Dict[str, str]] = None,
    caller_tools: List[Dict] = None,
    system_prompt_override: str = None,
    task_id: str = None,
    cancel_event: asyncio.Event = None,
    channel: str = "text",  # NEW PARAMETER
    db: Session = None,     # Ensure db is passed through
) -> str:
```

- [ ] **Step 4: Update all callers of `generate_with_agent` to pass `channel` and `db`**

Search for calls to `generate_with_agent` and update:
- `AgentOrchestrator` — pass `channel="text"` and `db`
- `TaskExecutor` — pass `channel="text"` and `db`
- Any other callers

Example:
```python
# Before:
response = await model_service.generate_with_agent(agent, message, history, tools)

# After:
response = await model_service.generate_with_agent(
    agent=agent,
    user_message=message,
    history=history,
    caller_tools=tools,
    channel="text",
    db=db
)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest backend/tests/services/test_model_provider_ethos.py -v`
Expected: PASS

Run: `pytest backend/tests/integration/test_model_provider.py -v` (regression)
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/model_provider.py backend/tests/services/test_model_provider_ethos.py
git commit -m "feat: unify ethos injection via Agent.get_system_prompt in ModelService"
```

---

### Task 3: Extend Persona for New Sovereign Preferences

**Files:**
- Modify: `backend/core/persona.py` (build_persona_directive function)
- Test: `backend/tests/test_constitution_persona.py` (extend existing)

**Interfaces:**
- Consumes: `constitution["sovereign_preferences"]` dict
- Produces: Enhanced persona prompt with response_format and verbosity hints

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_constitution_persona.py (add to existing file)
def test_persona_includes_response_format_preference():
    const = _sample_constitution()
    const["sovereign_preferences"] = {
        "communication_style": "formal",
        "response_format": "bullet_points",
        "verbosity": "verbose"
    }
    text = build_persona_directive(const, tier=3)
    assert "bullet points" in text.lower() or "bullet_points" in text.lower()
    assert "verbose" in text.lower() or "detail" in text.lower()

def test_persona_includes_concise_verbosity():
    const = _sample_constitution()
    const["sovereign_preferences"] = {
        "verbosity": "concise"
    }
    text = build_persona_directive(const, tier=3)
    assert "concise" in text.lower() or "brief" in text.lower()

def test_persona_includes_summary_first_format():
    const = _sample_constitution()
    const["sovereign_preferences"] = {
        "response_format": "summary_first"
    }
    text = build_persona_directive(const, tier=3)
    assert "summary" in text.lower()
```

Run: `pytest backend/tests/test_constitution_persona.py::test_persona_includes_response_format_preference -v`
Expected: FAIL

- [ ] **Step 2: Modify `backend/core/persona.py` — `build_persona_directive` function**

```python
# In persona.py, inside build_persona_directive function (after line 146)
# Extend the style_bits section:

    style_bits = []
    comm = sovereign.get("communication_style")
    if comm:
        style_bits.append(str(comm))
    
    # NEW: response_format preference
    response_format = sovereign.get("response_format")
    if response_format == "summary_first":
        style_bits.append(
            "Start responses with a concise standalone summary "
            "(1-3 sentences) that can stand alone as the full answer, "
            "then provide detail."
        )
    elif response_format == "bullet_points":
        style_bits.append(
            "Use bullet points and structured lists for clarity. "
            "Avoid long paragraphs."
        )
    elif response_format == "detailed":
        style_bits.append(
            "Provide thorough, detailed explanations with context."
        )
    
    # NEW: verbosity preference
    verbosity = sovereign.get("verbosity")
    if verbosity == "concise":
        style_bits.append("Be concise. Use minimal words. No fluff.")
    elif verbosity == "verbose":
        style_bits.append("Be thorough and verbose. Include all relevant details.")
    # "normal" = no extra instruction
    
    if channel == "voice":
        style_bits.append(VOICE_ADAPTATION)
    
    # Existing summary-first hint for response envelope (non-voice channels)
    if channel != "voice":
        from backend.core.config import get_settings
        if get_settings().RESPONSE_DELIVERY_ENVELOPE:
            style_bits.append(
                "Start responses with a concise standalone summary "
                "(1-3 sentences) that can stand alone as the full answer, "
                "then provide detail."
            )
```

- [ ] **Step 3: Run tests to verify pass**

Run: `pytest backend/tests/test_constitution_persona.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/core/persona.py backend/tests/test_constitution_persona.py
git commit -m "feat: extend persona with response_format and verbosity preferences"
```

---

### Task 4: Frontend Integration Verification

**Files:**
- Verify: `frontend/src/services/constitution.ts` calls work
- Verify: `frontend/src/pages/ConstitutionPage.tsx` edit/save works
- Test: Manual E2E or Playwright if available

**Interfaces:**
- Consumes: New API endpoints
- Produces: Working Constitution page

- [ ] **Step 1: Start backend and frontend**

```bash
# Terminal 1: Backend
cd E:\Ongoing Projects\Agentium
docker compose up backend

# Terminal 2: Frontend
cd frontend
npm run dev
```

- [ ] **Step 2: Verify Constitution page loads**

1. Login as admin
2. Navigate to Constitution page
3. Verify version, preamble, articles, prohibitions, preferences display
4. Verify stats cards show correct counts

- [ ] **Step 3: Verify Edit mode works**

1. Click "Edit Constitution"
2. Modify preamble
3. Click "Save Changes"
4. Verify toast "Constitution updated successfully"
5. Verify page reloads with new data

- [ ] **Step 4: Verify Preferences update works**

1. In edit mode, modify sovereign preferences (communication_style, etc.)
2. Save
3. Verify preferences persist
4. Verify agent responses reflect new style (manual check)

- [ ] **Step 5: Verify Propose Amendment works**

1. Click "Propose Amendment"
2. Fill form, submit
3. Verify appears in Voting page

- [ ] **Step 6: Verify Voting page works**

1. Navigate to Voting page
2. Verify amendments list loads
3. Verify voting UI functions

- [ ] **Step 7: Commit any frontend fixes if needed**

```bash
git add frontend/src/services/constitution.ts frontend/src/pages/ConstitutionPage.tsx
git commit -m "fix: frontend constitution integration adjustments"
```

---

### Task 5: Run Full Verification Suite

**Files:**
- Run: All existing tests + new tests

- [ ] **Step 1: Run Constitution-related tests**

```bash
pytest backend/tests/api/test_constitution_routes.py -v
pytest backend/tests/services/test_model_provider_ethos.py -v
pytest backend/tests/test_constitution_persona.py -v
pytest backend/tests/integration/test_governance.py -v
```

Expected: ALL PASS

- [ ] **Step 2: Run full test suite for regressions**

```bash
pytest backend/tests/ -x --tb=short
```

Expected: NO NEW FAILURES

- [ ] **Step 3: Update TODO.md Section 7**

Mark items as complete:
- [x] 7.1.2 — `GET /api/v1/constitution` returns current constitution
- [x] 7.1.4 — Sovereign preferences are stored and applied
- [x] 7.4.2 — Ethos is injected into LLM system prompts

```bash
git add docs/documents/TODO.md
git commit -m "docs: update TODO.md Section 7 verification complete"
```

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "feat: Constitution & Governance gap-filling complete (Section 7)"
```

---

## Spec Coverage Check

| Spec Section | Task | Status |
|--------------|------|--------|
| 1. Constitution API Routes | Task 1 | ✅ Covered |
| 2. Ethos Injection Unification | Task 2 | ✅ Covered |
| 3. Head of Council Veto | N/A | ✅ Accepted as-is |
| 4. Sovereign Preferences Flow | Task 1, 3 | ✅ Covered |
| 5. Verification Checklist | Task 5 | ✅ Covered |

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-07-constitution-governance-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**