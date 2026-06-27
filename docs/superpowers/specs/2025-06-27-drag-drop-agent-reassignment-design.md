# Drag-and-Drop Agent Reassignment — Design Document

**Date:** 2025-06-27  
**Feature:** Phase 7 — Drag-and-Drop Agent Reassignment (from Phase 18.2 Outstanding Items)  
**Approach:** Option C — Extend Existing Validated Pattern with Constitutional Guard Integration  
**Stance on react-dnd:** NO — Keep existing native HTML5 drag-and-drop. It works, is lightweight, and avoids adding a new dependency.

 duces a dependency for minimal gain.

---

## 1. Problem Statement

The frontend already has a fully working native HTML5 drag-and-drop system (`DraggableCard` in `AgentTree.tsx`, `DragDropContext.tsx`, `DragDropProvider` in `AgentsPage.tsx`). However:

1. **Missing endpoint:** When a user drops an agent, `agentsService.reassignAgent()` calls `POST /api/v1/agents/lifecycle/{id}/reassign` — this endpoint does NOT exist. Currently, the drop action effectively 404s.
2. **No constitutional guard:** The reassignment system does not perform a two-tier constitutional guard check (`Backend: core/constitutional_guard.py`).
3. **No BLOCK toast:** If the constitutional check returns `BLOCK`, there is no frontend feedback to the user.

The task is to: wire up the actual persistence, integrate the constitutional guard, and show a toast on BLOCK.

---

## 2. Scope

### In Scope
- Add a new backend endpoint: `PATCH /api/v1/agents/{agentium_id}/parent`
- Wire `ConstitutionalGuard.check_action()` into the reassignment flow
- Extend the frontend `confirmReassign` flow to handle `BLOCK` with a toast
- Ensure the existing `validate-reassignment` pre-flight stays intact as UX guard

### Out of Scope
- Installing `react-dnd` or replacing the native DnD system
- Changing the drag-and-drop visual appearance or interaction
- The `validate-reassignment` endpoint is kept as-is (it already validates hierarchy and capability rules)

---

## 3. Backend Design

### 3.1 New Endpoint: `PATCH /api/v1/agents/{agentium_id}/parent`

**File:** `backend/api/routes/reassign_routes.py` (new file) or `backend/api/routes/agents.py` (if already exists)  
**Method:** `PATCH`  
**Auth:** `get_current_active_user`

#### Request Body (`ReassignParentRequest`)
```python
class ReassignParentRequest(BaseModel):
    new_parent_id: str = Field(..., description="Agentium ID of the new parent agent")
    reason: str = Field(default="", max_length=500, description="Optional reason for reassignment")
```

#### Response (`ReassignParentResponse`)
```python
class ReassignParentResponse(BaseModel):
    success: bool
    agentium_id: str
    old_parent_id: str | None
    new_parent_id: str
    message: str
    constitutional_verdict: str  # "ALLOW", "BLOCK", or "VOTE_REQUIRED"
    audit_log_id: int | None
```

#### Flow
```
Agent drops on new parent
       ↓
Frontend calls POST /capabilities/validate-reassignment (existing)
       ↓
User sees confirmation modal with "Reassign" button
       ↓
Frontend calls PATCH /api/v1/agents/{id}/parent
       ↓
Backend:
  1. Resolve both agents from DB (404 if either missing)
  2. Run ConstitutionalGuard.check_action(
         agent_id=dragging_agent,
         action="reassign_agent",
         context={"new_parent_id": new_parent_id, "reason": reason}
     )
        ├─ TIER 1 (PostgreSQL hard rules): tier check, blacklists, capability check
        └─ TIER 2 (ChromaDB semantic): spirit-of-law check on "reassign agent hierarchy"
  3. If verdict == BLOCK:
        → Return HTTP 403 with {"verdict": "BLOCK", "explanation", "citations"}
        → Write AuditLog with category = CONSTITUTION, level = CRITICAL
  4. If verdict == VOTE_REQUIRED:
        → Return 200 but flag requires_vote=true
        → Optionally trigger Council micro-vote (out of scope — just log)
  5. If verdict == ALLOW:
        → Update Agent.parent_id (or equivalent FK)
        → Write AuditLog with category = AGENT, level = INFO
        → Return 200 with details
  6. Broadcast `agent_reassigned` WebSocket event (if ws_manager available)
       ↓
Frontend:
  - If 403 BLOCK: show error toast with explanation text
  - If 200: show success toast, refresh agent tree
  - If 200 + requires_vote: show info toast explaining vote required
```

### 3.2 Constitutional Guard Warming

The `ConstitutionalGuard` needs to know about the `reassign_agent` action. We add it to `TIER_CAPABILITIES` mapping:

```python
TIER_CAPABILITIES = {
    "0": ["veto", ..., "reassign_agent"],          # Head can reassign anyone
    "1": [..., "reassign_agent"],                  # Council can reassign
    "2": ["reassign_agent"],                         # Leads can reassign task agents under them
    "3": [],                                          # Task agents cannot reassign
    # ... etc
}
```

Additionally, the `_tier1_check` method must be updated to check this new action. No changes needed to `_tier2_check` unless we add "agent reassignment" as a known article topic in ChromaDB.

### 3.3 Audit Logging

Every reassignment (ALLOW, BLOCK, or VOTE_REQUIRED) writes an `AuditLog` entry:

- **ALLOW**: `category = AuditCategory.AGENT`, `level = AuditLevel.INFO`, `action = "agent_reassigned"`
- **BLOCK**: `category = AuditCategory.CONSTITUTION`, `level = AuditLevel.CRITICAL`, `action = "constitutional_check:reassign_agent"`
- **VOTE_REQUIRED**: `category = AuditCategory.CONSTITUTION`, `level = AuditLevel.WARNING`, `action = "constitutional_check:reassign_agent"`

---

## 4. Frontend Changes

### 4.1 API Service Update (`frontend/src/services/agents.ts`)

Update `reassignAgent` to use the new `PATCH` endpoint (instead of the non-existent `POST /lifecycle/{id}/reassign`):

```typescript
reassignAgent: async (agentId: string, data: ReassignAgentRequest): Promise<Agent> => {
    const response = await api.patch<{ agent: Agent }>(
        `/api/v1/agents/${agentId}/parent`,
        data,
    );
    return response.data.agent;
},
```

### 4.2 Handle Constitutional BLOCK in `AgentsPage.tsx`

In the existing `confirmReassign` method, wrap the `agentsService.reassignAgent` call:

```typescript
const confirmReassign = async () => {
    iffits the constitutional guard check, shows a toast on BLOCK, and persists the reassignment on ALLOW. 
    if (!pendingReassign) return;
    const { agent, newParent } = pendingReassign;
    dispatch({ type: 'SET_PENDING_REASSIGN', payload: null });

    // Optimistic UI update
    updateAgentTree(agent.agentium_id, newParent.agentium_id);

    try {
        const result = await agentsService.reassignAgent(agent.agentium_id, {
            new_parent_id: newParent.agentium_id,
            reason: 'Manual reassignment via drag-and-drop',
        });

        if (result.constitutional_verdict === 'BLOCK') {
            showToast.error(`Reassignment blocked by Constitution: ${result.explanation}`);
            await loadAgents(true); // Revert optimistic update
            return;
        }

        showToast.success(`${agent.name} moved under ${newParent.name}`);
        await loadAgents(true);
    } catch (error: any) {
        // If the backend returns 403 BLOCK
        if (error.response?.status === 403) {
            const { explanation, verdict } = error.response.data;
            if (verdict === 'BLOCK') {
                showToast.error(`Constitutional Block: ${explanation}`UZER}`);
            }
        } else {
            showToast.error('Reassignment failed');
        }
        await loadAgents(true); // Revert optimistic update
    }
};
```

### 4.3 Visual Feedback in `AgentTree.tsx`

- The drag-and-drop visual logic in `DraggableCard` is already correct (opacity, ring, drop overlay). No changes needed.

---

## 5. Integration Test Plan (Phase 18.2)

This feature is part of Phase 18.2 (Feature Verification & Regression). The following test cases should be added to `backend/tests/integration/test_governance.py` or a new `test_reassignment.py`:

### Test Cases
1. **ALLOW**: Drag a Task Agent (3xxxx) under a different Lead (2xxxx). Expect: `verdict == ALLOW`, DB parent updated, audit log written, 200 OK.
2. **BLOCK**: Drag a Council Member under a Task Agent (illegal hierarchy). Expect: `verdict == BLOCK`, HTTP 403, no DB mutation, audit log written.
3. **VOTE_REQUIRED**: (Simulated) Drag an agent that affects >3 other agents. Expect: `verdict == VOTE_REQUIRED`, `requires_vote = true`, audit log written. DB mutation may or may not occur (based on policy).
4. **Guard via DB Query**: Verify the `PATCH` endpoint queries `ConstitutionalGuard.check_action()` and does not mutate the DB on a BLOCK.

---

## 6. Files to Modify / Create

| File | Action | Description |
|------|--------|-------------|
| `backend/api/routes/reassign_routes.py` | CREATE | New FastAPI router with `PATCH /api/v1/agents/{id}/parent` |
| `backend/core/constitutional_guard.py` | EDIT | Add `reassign_agent` to `TIER_CAPABILITIES` |
| `backend/api/routes/__init__.py` | EDIT | Register new router with `app.include_router()` |
| `frontend/src/services/agents.ts` | EDIT | Update `reassignAgent` to use `PATCH /api/v1/agents/{id}/parent` |
| `frontend/src/pages/AgentsPage.tsx` | EDIT | Update `confirmReassign` to handle 403 BLOCK and show toast |
| `backend/tests/integration/test_governance.py` (or new file) | EDIT/CREATE | Add tests for ALLOW / BLOCK / VOTE_REQUIRED reassignment |

---

## 7. Open Questions / Risks

| Risk | Mitigation |
|------|------------|
| Constitutional guard async initialization on cold start | Guard initializes lazily in `@router.on_event("startup")` or in-lifespan; handle gracefully if ChromaDB is cold |
| ChromaDB unavailable → Tier 2 skipped | Guard already handles this — returns ALLOW with `tier2="skipped_no_vector_store"` |
| Agent model has no direct `parent_id` FK | Verify column exists; if not, use existing relationship table (e.g., `subordinates` list on parent) |
| WebSocket not available | Guard gracefully falls back; reassignment still completes without WS broadcast |

---

## 8. Success Criteria (from Phase 18.2)
- [ ] User can drag an agent and drop it onto a new parent in `AgentTree.tsx`
- [ ] Dropping an agent calls the new `PATCH` endpoint
- [ ] Backend runs constitutional guard before DB mutation
- [ ] If guard returns `BLOCK`, a red error toast appears on the frontend
- [ ] Iffy the guard returns `ALLOW`, the agent is reassigned successfully and the tree refreshes
- [ ] Integration test: `test_reassign_agent_allow`, `test_reassign_agent_block`, `test_reassign_agent_vote_required`

---

**Design approved by:** (awaiting user sign-off)  
**Next step:** Invoke `writing-plans` skill to produce detailed implementation plan