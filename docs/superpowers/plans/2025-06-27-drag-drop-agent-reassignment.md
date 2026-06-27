# Drag-and-Drop Agent Reassignment - Implementation Plan

> For agentic workers: Use superpowers:subagent-driven-development to implement this plan task-by-task.

## Goal
Wire a working PATCH /api/v1/agents/{id}/parent endpoint with constitutional guard integration and frontend toast on BLOCK, without changing the existing native HTML5 drag-and-drop.

## Architecture
New FastAPI router bolted onto existing agent API. Constitutional guard runs check_action("reassign_agent") before touching DB. Frontend updates confirmReassign to handle 403 BLOCK and revert optimistic tree update. Existing validate-reassignment pre-flight remains as first gate.

## Tech Stack
FastAPI, SQLAlchemy, Pydantic v2, React 18, TypeScript, Tailwind, native HTML5 DnD.

## Global Constraints
- Python 3.10+, FastAPI, SQLAlchemy 2, Pydantic v2
- React 18, TypeScript, no new dependencies
- Keep existing native HTML5 drag-and-drop; do NOT install react-dnd
- All HTTP errors return standard shape { "error": str, "code": str, "detail": dict | None }
- Every blocked reassignment writes an AuditLog
- Tests must cover ALLOW, BLOCK, and VOTE_REQUIRED paths

## File Map

| # | File | Responsibility |
|---|------|---------------|
| 1 | backend/api/routes/reassign_routes.py | New router - PATCH /api/v1/agents/{id}/parent, runs guard, persists, audits |
| 2 | backend/core/constitutional_guard.py | Add reassign_agent to TIER_CAPABILITIES so guard recognizes action |
| 3 | backend/main.py | Register new router with app.include_router(...) |
| 4 | frontend/src/services/agents.ts | Update reassignAgent() to call the new PATCH endpoint |
| 5 | frontend/src/pages/AgentsPage.tsx | Update confirmReassign to handle 403 BLOCK with toast; revert optimistic UI on failure |
| 6 | backend/tests/integration/test_reassignment.py | Integration tests for ALLOW, BLOCK, VOTE_REQUIRED paths |

## Implementation Order

### Task 1: Add reassign_agent to Constitutional Guard
**Files:** backend/core/constitutional_guard.py
**Goal:** Guard has entry for reassign_agent in TIER Preface Text: none (file is text-based, no imports needed)

Step 1: Open TIER_CAPABILITIES dict in constitutional_guard.py.
Step 2: Add "reassign_agent" to tier "0", tier "1", and tier "2" lists.
Step 3: Add "reassign_agent" to named keys "head", "council", and "lead".
Step 4: Verify no syntax errors by running: python -m py_compile backend/core/constitutional_guard.py

Expected: Script compiles without error.

### Task 2: Create Backend Reassignment Router
**Files:** backend/api/routes/reassign_routes.py (new)
**Goal:** FastAPI router with PATCH endpoint that resolves agents, runs guard, and persists reassignment.
Step 1: Create the new file.
Step 2: Define request/response pydantic models (ReassignParentRequest, ReassignParentResponse).
Step 3: Implement the PATCH endpoint logic:
  - Resolve both agents from DB (404 if missing)
  - Initialize ConstitutionalGuard(db) and guard.initialize()
  - Run guard.check_action(agent_id, "reassign_agent", context)
  - If BLOCK: write AuditLog(CRITICAL, CONSTITUTION), return HTTP 403 with explanation and citations
  - If VOTE_REQUIRED: write AuditLog(WARNING, CONSTITUTION), return 200 with requires_vote=True
  - If ALLOW: update parent relationship, write AuditLog(INFO, AGENT), return 200 with details
  - Broadcast agent_reassigned WebSocket event if ws_manager available
Step 4: Run python -m py_compile backend/api/routes/reassign_routes.py to verify syntax.

### Task 3: Register Router in FastAPI App
**Files:** backend/main.py
**Goal:** New router is mounted under /api/v1/agents.
Step 1: Import reassign_routes router in backend/main.py.
Step 2: Add app.include_router(reassign_routes.router) alongside existing includes.
Step 3: Verify by running the backend (or at least importing the module) and checking no import errors.

### Task 4: Update Frontend API Service
**Files:** frontend/src/services/agents.ts
**Goal:** reassignAgent uses PATCH /api/v1/agents/{id}/parent instead of non-existent POST.
Step 1: Change the reassignAgent method to call api.patch instead of api.post.
Step 2: Update URL path from /api/v1/agents/lifecycle/{agentId}/reassign to PATCH /api/v1/agents/{agentId}/parent.
Step 3: Verify TypeScript compiles without errors.

### Task 5: Update Frontend Confirm Reassign Flow
**Files:** frontend/src/pages/AgentsPage.tsx
**Goal:** Handle 403 BLOCK from backend and show toast with explanation.
Step 1: In confirmReassign, wrap the agentsService.reassignAgent call in try/catch.
Step 2: In catch block, check for error.response.status === 403 and error.response.data.verdict === "BLOCK".
Step 3: Show constitutional block toast using showToast.error(explanation).
Step 4: Revert the optimistic local tree update (remove agent from old parent's subordinates, return to old parent).
Step 5: Verify the ReassignModal still works correctly.

### Task 6: Integration Tests
**Files:** backend/tests/integration/test_reassignment.py (new)
**Goal:** Cover ALLOW, BLOCK, and VOTE_REQUIRED reassignment paths.
Step 1: Create test file.
Step 2: Write test_reassign_agent_allow: drag a task agent under a different lead. Expect 200, parent updated, audit log written.
Step 3: Write test_reassign_agent_block: drag council member under a task agent. Expect 403, no DB mutation, audit log written.
Step 4: Write test_reassign_guard_vote_required: simulate dragging agent affecting >3 other agents. Expect 200 with requires_vote=true, audit log written.
Step 5: Run pytest tests/integration/test_reassignment.py -v and verify all three pass.
