# Frontend Tool Creation → Backend Verification E2E Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an integration test proving a tool created through the frontend propose route is actually registered in `tool_registry.tools`, exported via `to_openai_tools`/`to_anthropic_tools`, and invocable by an authorized agent.

**Architecture:** One new integration test module with two layers — (A) drives the real `POST /api/v1/tool-management/propose` HTTP route as a Head-tier agent, (B) calls `ToolCreationService.propose_tool` directly. Both assert live persistence against the `tool_registry` singleton, then clean up via `deregister_tool`. A Head-tier JWT fixture mints a token because the default `admin` JWT defaults to Task tier and is blocked by the route.

**Tech Stack:** Python 3, pytest, pytest-asyncio, FastAPI `TestClient`, SQLAlchemy, `backend.core.tool_registry.ToolRegistry`, `backend.services.tool_creation_service.ToolCreationService`, `backend.core.auth.create_access_token`.

## Global Constraints

- Tests are integration tests: marked `@pytest.mark.integration`, run under the integration harness (`make test-integration`) with Postgres/Redis/ChromaDB test services available.
- Route under test: `POST /api/v1/tool-management/propose` (prefix `/api/v1` + router prefix `/tool-management` + `/propose`).
- `ToolCreationRequest` is pydantic v2 → serialize with `.model_dump()`, not `.dict()`.
- Head identity `agentium_id="00001"`, `tier="0xxxx"` auto-approves/activates (no Council vote).
- Tool name must be unique per test run (avoids `ToolStaging` name-collision rejection).
- `code_template` must pass `ToolFactory.validate_tool_code` — a benign expression `result = {...}` does.
- `tool_registry` is a process-wide singleton; every test MUST `deregister_tool(name)` in teardown so the tool does not leak into other tests.
- Commit style: conventional `feat:`/`test:` prefixes (repo convention).

---

### Task 1: Add Head-tier auth fixture

**Files:**
- Create: `backend/tests/integration/test_frontend_tool_creation_e2e.py` (fixture only — full module built across tasks)
- Reference: `backend/core/auth.py:32` (`create_access_token`)
- Reference: `backend/tests/integration/conftest.py:355` (`client` fixture)

**Interfaces:**
- Consumes: `create_access_token(data: dict, expires_delta=None) -> str` from `backend.core.auth`
- Produces: module-level `head_auth_headers` fixture returning `{"Authorization": f"Bearer {token}"}` — used by Task 3 HTTP test.

- [ ] **Step 1: Write the fixture module**

Create `backend/tests/integration/test_frontend_tool_creation_e2e.py`:

```python
"""E2E verification: tool created via frontend propose flow is registered,
exported to provider schemas, and invocable by an authorized agent.

Covers planning task §3.4 (P2): confirm UI-created tools actually persist on
the backend and are not lost to a stale registry / cache.
"""
import pytest

from backend.core.auth import create_access_token


@pytest.fixture
def head_auth_headers():
    """Mint a Head-tier (0xxxx) JWT so the propose route auto-activates.

    The default admin login JWT carries no `tier` claim, so
    get_current_agent_tier() defaults to 3xxxx (Task) and the route blocks it
    via _require_not_task_agent. The Head path auto-approves + activates.
    """
    token = create_access_token({
        "sub": "00001",
        "user_id": 1,
        "role": "head",
        "is_admin": True,
        "is_active": True,
        "tier": "0xxxx",
        "agentium_id": "00001",
    })
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: Sanity-check the fixture imports and token round-trips**

Run: `cd backend && python -c "from backend.tests.integration.test_frontend_tool_creation_e2e import head_auth_headers; print('import ok')"`

Expected: prints `import ok` (no ImportError).

- [ ] **Step 3: Commit**

```bash
git add -f backend/tests/integration/test_frontend_tool_creation_e2e.py
git commit -m "test: add Head-tier auth fixture for tool-creation E2E"
```

---

### Task 2: Add shared helpers and direct-service test (Test B)

**Files:**
- Modify: `backend/tests/integration/test_frontend_tool_creation_e2e.py` (append)
- Reference: `backend/services/tool_creation_service.py:54` (`propose_tool`)
- Reference: `backend/models/schemas/tool_creation.py:11` (`ToolCreationRequest`, `ToolParameter`)
- Reference: `backend/core/tool_registry.py:1650` (`register_tool`), `:1762` (`deregister_tool`), `:1808` (`to_openai_tools`), `:1739` (`to_anthropic_tools`), `:1735` (`get_tool_function`)

**Interfaces:**
- Consumes: `head_auth_headers` fixture (Task 1); `ToolCreationRequest` pydantic model; `ToolCreationService(db)` with `.propose_tool(request) -> dict`.
- Produces: `_make_request(name)` helper; `test_direct_service_tool_persists_and_is_invocable` — asserts registry/export/invoke for later reuse as reference behavior.

- [ ] **Step 1: Write the failing test (direct service path)**

Append to `backend/tests/integration/test_frontend_tool_creation_e2e.py`:

```python
from uuid import uuid4

from backend.core.tool_registry import tool_registry
from backend.models.schemas.tool_creation import ToolCreationRequest
from backend.services.tool_creation_service import ToolCreationService


def _make_request(unique_name: str) -> ToolCreationRequest:
    return ToolCreationRequest(
        tool_name=unique_name,
        description="E2E probe tool",
        parameters=[],
        code_template="result = {'echo': 'ok', 'n': 42}",
        test_cases=[],
        authorized_tiers=["0xxxx", "1xxxx"],
        created_by_agentium_id="00001",
        rationale="e2e verification",
    )


@pytest.mark.integration
def test_direct_service_tool_persists_and_is_invocable(seeded_db):
    name = f"e2e_probe_{uuid4().hex[:8]}"
    service = ToolCreationService(seeded_db)
    res = service.propose_tool(_make_request(name))
    try:
        assert res.get("proposed") is True, res
        assert res.get("status") == "activated", res

        # 1) Persisted in the live registry
        assert name in tool_registry.tools

        # 2) Exported to OpenAI schema
        oai = tool_registry.to_openai_tools("0xxxx")
        oai_names = [t["function"]["name"] for t in oai]
        assert name in oai_names
        spec = next(t for t in oai if t["function"]["name"] == name)
        assert spec["function"]["description"] == "E2E probe tool"

        # 3) Exported to Anthropic schema
        ant = tool_registry.to_anthropic_tools("0xxxx")
        assert name in [t["name"] for t in ant]

        # 4) Invocable by an authorized agent (ToolFactory wraps the return
        #    value in a {"status": "success", "result": ...} envelope — see
        #    backend/services/tool_factory.py:121)
        fn = tool_registry.get_tool_function(name)
        assert fn() == {"status": "success", "result": {"echo": "ok", "n": 42}}
    finally:
        tool_registry.deregister_tool(name)
```

- [ ] **Step 2: Run the test to verify it passes under the integration harness**

Run: `cd backend && python -m pytest tests/integration/test_frontend_tool_creation_e2e.py::test_direct_service_tool_persists_and_is_invocable -m integration -v`

Expected: PASS (the direct-service path is already wired; this locks the expected behavior). If it FAILS, stop — a persistence/export/invoke gap already exists and must be root-caused before proceeding.

- [ ] **Step 3: Commit**

```bash
git add -f backend/tests/integration/test_frontend_tool_creation_e2e.py
git commit -m "test: add direct-service tool-creation persistence/invoke E2E"
```

---

### Task 3: Add HTTP route E2E test (Test A)

**Files:**
- Modify: `backend/tests/integration/test_frontend_tool_creation_e2e.py` (append)
- Reference: `backend/api/routes/tool_creation.py:127` (propose route, prefix `/api/v1/tool-management`)
- Reference: `conftest.py:355` (`client` fixture), `conftest.py:146` (`seeded_db`)

**Interfaces:**
- Consumes: `head_auth_headers` fixture (Task 1); `client` fixture; `seeded_db` fixture; `_make_request` helper (Task 2); `tool_registry` singleton.
- Produces: `test_http_propose_route_registers_and_exports_tool` — the primary E2E through the real frontend→backend HTTP path.

- [ ] **Step 1: Write the failing test (real HTTP route)**

Append to `backend/tests/integration/test_frontend_tool_creation_e2e.py`:

```python
@pytest.mark.integration
def test_http_propose_route_registers_and_exports_tool(client, seeded_db, head_auth_headers):
    name = f"e2e_probe_{uuid4().hex[:8]}"
    body = _make_request(name).model_dump()
    resp = client.post(
        "/api/v1/tool-management/propose",
        json=body,
        headers=head_auth_headers,
    )
    try:
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "activated", data
        assert data.get("tool_name") == name, data

        # Live persistence in the registry singleton (catches stale/cache gaps)
        assert name in tool_registry.tools

        oai = tool_registry.to_openai_tools("0xxxx")
        assert name in [t["function"]["name"] for t in oai]

        ant = tool_registry.to_anthropic_tools("0xxxx")
        assert name in [t["name"] for t in ant]

        fn = tool_registry.get_tool_function(name)
        assert fn() == {"status": "success", "result": {"echo": "ok", "n": 42}}
    finally:
        tool_registry.deregister_tool(name)
```

- [ ] **Step 2: Run the full module to verify both tests pass**

Run: `cd backend && python -m pytest tests/integration/test_frontend_tool_creation_e2e.py -m integration -v`

Expected: Both `test_direct_service_tool_persists_and_is_invocable` and `test_http_propose_route_registers_and_exports_tool` PASS. If the HTTP test FAILS (e.g. 403 from tier default, or tool missing from `tool_registry.tools`), that is the §3.4 gap — root-cause and fix it (do not weaken the assertion).

- [ ] **Step 3: Commit**

```bash
git add -f backend/tests/integration/test_frontend_tool_creation_e2e.py
git commit -m "test: add HTTP-route E2E for frontend tool creation → backend verification"
```

---

### Task 4: Run full integration suite gate

**Files:**
- None (verification only)

**Interfaces:**
- Consumes: the committed test module.

- [ ] **Step 1: Run the module once more with coverage gate**

Run: `cd backend && python -m pytest tests/integration/test_frontend_tool_creation_e2e.py -m integration --cov=services --cov-report=term-missing --cov-fail-under=20 -v`

Expected: Both tests PASS; coverage gate satisfied (≥20%). No import errors, no leaked `tool_registry` entries affecting other tests.

- [ ] **Step 2: Final commit (if any fix was needed in step 1)**

If a fix was required, commit it:

```bash
git add -f backend/tests/integration/test_frontend_tool_creation_e2e.py
git commit -m "fix: resolve tool-creation E2E gap (registry/export/invoke)"
```

If no fix was needed, no commit required — work is complete.
