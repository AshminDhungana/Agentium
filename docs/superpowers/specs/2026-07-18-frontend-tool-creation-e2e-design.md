# E2E Test: Frontend Tool Creation → Backend Verification (Task 3.4)

**Date:** 2026-07-18
**Status:** approved
**Domain:** project
**Source task:** Planning doc §3.4 — [P2] Frontend tool creation → backend verification

## Problem

It is unconfirmed whether tools created via the frontend UI are actually
persisted and registered correctly on the backend. The worry (explicitly called
out in the task) is a gap such as:

- the registry is not reloaded after creation, or
- a cache layer serves a stale tool set, or
- the tool is written to the DB but never reaches `tool_registry.tools`, so it
  is never exported to the model providers nor invocable.

This spec defines an end-to-end (E2E) integration test that closes that gap.

## Flow Under Test

```
Frontend ToolMarketplacePage.tsx (Propose New Tool)
  → toolManagementApi.proposeTool(...)
  → POST /api/v1/tool-management/propose            (backend/api/routes/tool_creation.py:127)
  → ToolCreationService.propose_tool(request)       (backend/services/tool_creation_service.py:54)
      • Head (0xxxx) → auto-approve → activate_tool()
      • Council/Lead → triggers Council vote
      • Task (3xxxx) → blocked
  → ToolCreationService.activate_tool()             (backend/services/tool_creation_service.py:196)
      → ToolFactory.load_tool(...)
      → tool_registry.register_tool(name, ..., function, ...)   (backend/core/tool_registry.py:1650)
  → tool_registry.tools[name] populated
  → to_openai_tools(tier) / to_anthropic_tools(tier) read from tool_registry.tools
  → get_tool_function(name)(...) executes the tool
```

## Acceptance Criteria

1. E2E test passes in CI (`make test-integration`).
2. The test asserts, for a tool created through the real HTTP propose route:
   - it is present in `tool_registry.tools`,
   - it is exported via `tool_registry.to_openai_tools(tier)` and
     `tool_registry.to_anthropic_tools(tier)`,
   - it is invocable by an authorized agent (call returns the expected result).
3. If a gap exists (registry not reloaded / cache staleness / not registered),
   the test fails — and the root cause is fixed, not papered over.

## Decisions (from brainstorming)

- **Auth:** Use BOTH a real-HTTP route test (with a Head-tier JWT) AND a
  direct-service-call test. Covers the API boundary and the persistence chain.
- **Tool type:** A simple stateless pure-Python tool (returns a static dict),
  no DB/async dependencies. Fast and deterministic.
- **Staleness:** Assert LIVE persistence against the running `tool_registry`
  singleton — i.e. that the freshly proposed tool appears immediately in
  `.tools`, both export schemas, and is callable. No separate restart-reload
  scenario (out of scope).

## Design

### New auth fixture

The default `admin` JWT (conftest `auth_headers`) carries no `tier` claim, so
`get_current_agent_tier` defaults to `3xxxx` (Task), and the propose route
blocks Task agents (`_require_not_task_agent`). To exercise the Head
auto-activate path we mint a Head-tier token.

Add a `head_auth_headers` fixture that builds a JWT with claims
`tier="0xxxx"`, `agentium_id="00001"`, `is_admin=True`, `is_active=True` using
`backend.core.auth.create_access_token`, then returns
`{"Authorization": f"Bearer {token}"}`.

This can live in the new test module (module-scoped) or in
`backend/tests/integration/conftest.py` next to `auth_headers`.

### New file: `backend/tests/integration/test_frontend_tool_creation_e2e.py`

All tests marked `@pytest.mark.integration`. They require `client` (or
`async_client`), `seeded_db`, and the new `head_auth_headers` fixture.

Helper (module-local):

```python
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
```

**Test A — HTTP E2E through the real route**

1. `client.post("/api/v1/tool-management/propose", json=request.dict(),
   headers=head_auth_headers)` → assert `200`.
2. Parse body; assert `result["status"] == "activated"` and
   `result["tool_name"] == unique_name`.
3. `from backend.core.tool_registry import tool_registry`.
4. `assert unique_name in tool_registry.tools`.
5. OpenAI export:
   ```python
   oai = tool_registry.to_openai_tools("0xxxx")
   names = [t["function"]["name"] for t in oai]
   assert unique_name in names
   spec = next(t for t in oai if t["function"]["name"] == unique_name)
   assert spec["function"]["description"] == "E2E probe tool"
   ```
6. Anthropic export:
   ```python
   ant = tool_registry.to_anthropic_tools("0xxxx")
   assert unique_name in [t["name"] for t in ant]
   ```
7. Invoke by an authorized agent:
   ```python
   fn = tool_registry.get_tool_function(unique_name)
   out = fn()
   assert out == {"echo": "ok", "n": 42}
   ```
8. **Teardown:** `tool_registry.deregister_tool(unique_name)` in `finally` so
   the module singleton does not leak the tool into other tests.

**Test B — Direct service variant**

1. `service = ToolCreationService(seeded_db)`.
2. `res = service.propose_tool(_make_request(unique_name))` (created_by is
   `0xxxx`, so auto-activates).
3. Assert `res["proposed"] is True` and `res["status"] == "activated"`.
4. Same assertions as Test A steps 4–7 against `tool_registry` / exports /
   invoke.
5. Teardown: `tool_registry.deregister_tool(unique_name)`.

### Notes / risks

- `ToolCreationRequest` forbids Task proposers only via the route's
  `_require_not_task_agent`; the service's own `propose_tool` blocks
  `3xxxx` strings too. The Head id `00001` satisfies both.
- A unique name per test (e.g. `f"e2e_probe_{uuid4().hex[:8]}"`) avoids the
  `ToolStaging` name-collision rejection in `propose_tool`.
- `seeded_db` provides an active Head/Council, so the Head path needs no vote.
- `code_template` must pass `ToolFactory.validate_tool_code` — a benign
  `result = {...}` expression does.

## Verification

```bash
cd backend
python -m pytest tests/integration/test_frontend_tool_creation_e2e.py -m integration -v
```

Run inside the integration harness (`make test-integration`) so Postgres,
Redis, and ChromaDB test services are available. The test must pass; any
failure indicating a persistence/export/invoke gap is fixed at its root.

## Out of scope

- Council-vote (non-Head) activation path.
- DB-only / post-restart reload of the registry from `ToolStaging`.
- Tools that declare `db`/`agent_id` params (analytics-wrapped execution path).
