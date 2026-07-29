# MCP WebSocket Revocation Broadcast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time WebSocket broadcast when an MCP tool is revoked, so connected clients update their UI within <100ms without waiting for the 60s polling fallback.

**Architecture:** Follow the existing `mcp_stats_update` broadcast pattern in `ConnectionManager`. Add a new `emit_mcp_tool_revoked()` method called synchronously from the `/revoke` endpoint after successful DB commit + Redis write. Frontend listens for `mcp_tool_revoked` event and immediately removes the tool from its stats map + refreshes the tool list.

**Tech Stack:** FastAPI WebSocket, Redis (via existing `mcp_stats_service`), React TypeScript frontend, existing Celery/beat infrastructure (not used for this broadcast — it's synchronous).

## Global Constraints

- Python 3.11+, TypeScript 5.x, React 18
- Follow existing code patterns in `backend/api/routes/websocket.py` and `backend/api/routes/mcp_tools.py`
- Frontend uses `useWebSocketStore` for message delivery (Zustand store)
- All WebSocket broadcasts go through `ConnectionManager.broadcast()`
- Redis key for revocation SET: `agentium:mcp:revoked`
- Non-fatal broadcast failures: log warning, continue — frontend has polling fallback
- Commit after each task with descriptive messages

---

### Task 1: Add `emit_mcp_tool_revoked` to ConnectionManager

**Files:**
- Modify: `backend/api/routes/websocket.py` (add method to `ConnectionManager` class, ~line 480)

**Interfaces:**
- Produces: `ConnectionManager.emit_mcp_tool_revoked(tool_id: str, tool_name: str, reason: str, revoked_by: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_websocket_revocation_broadcast.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.api.routes.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_emit_mcp_tool_revoked_broadcasts_correct_payload():
    """emit_mcp_tool_revoked should broadcast a properly structured event."""
    manager = ConnectionManager()
    manager.broadcast = AsyncMock()
    
    await manager.emit_mcp_tool_revoked(
        tool_id="tool-123",
        tool_name="Test Tool",
        reason="Security issue",
        revoked_by="admin-001"
    )
    
    manager.broadcast.assert_called_once()
    call_args = manager.broadcast.call_args[0][0]
    
    assert call_args["type"] == "mcp_tool_revoked"
    assert call_args["tool_id"] == "tool-123"
    assert call_args["tool_name"] == "Test Tool"
    assert call_args["reason"] == "Security issue"
    assert call_args["revoked_by"] == "admin-001"
    assert "timestamp" in call_args  # ISO8601 string
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/unit/test_websocket_revocation_broadcast.py::test_emit_mcp_tool_revoked_broadcasts_correct_payload -v
```
Expected: FAIL — `emit_mcp_tool_revoked` not defined

- [ ] **Step 3: Write minimal implementation**

Add to `ConnectionManager` class in `backend/api/routes/websocket.py` after `emit_mcp_stats_update` (~line 480):

```python
    async def emit_mcp_tool_revoked(
        self,
        tool_id: str,
        tool_name: str,
        reason: str,
        revoked_by: str,
    ) -> None:
        """
        Broadcast MCP tool revocation to all connected clients.
        
        Called synchronously from the revoke endpoint after successful Redis write.
        
        WebSocket payload:
            {
                "type":      "mcp_tool_revoked",
                "tool_id":   "<uuid>",
                "tool_name": "<name>",
                "reason":    "<revocation reason>",
                "revoked_by": "<agentium_id>",
                "timestamp": "<ISO8601>"
            }
        """
        from datetime import datetime
        await self.broadcast({
            "type":      "mcp_tool_revoked",
            "tool_id":   tool_id,
            "tool_name": tool_name,
            "reason":    reason,
            "revoked_by": revoked_by,
            "timestamp": datetime.utcnow().isoformat(),
        })
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/unit/test_websocket_revocation_broadcast.py::test_emit_mcp_tool_revoked_broadcasts_correct_payload -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/websocket.py backend/tests/unit/test_websocket_revocation_broadcast.py
git commit -m "feat(websocket): add emit_mcp_tool_revoked broadcast method"
```

---

### Task 2: Call Broadcast from Revoke Endpoint

**Files:**
- Modify: `backend/api/routes/mcp_tools.py` (in `revoke_mcp_tool` function, ~line 293)

**Interfaces:**
- Consumes: `ConnectionManager.emit_mcp_tool_revoked` (from Task 1)
- Produces: Side effect — WebSocket broadcast after revoke

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_mcp_revocation_broadcast.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_revoke_endpoint_broadcasts_websocket_event(client, db_session, auth_headers):
    """POST /revoke should emit mcp_tool_revoked WebSocket event after successful revocation."""
    # 1. Create and approve a tool
    r = client.post("/api/v1/mcp-tools", json={
        "name": "Test Tool for Revoke",
        "description": "Test",
        "server_url": "http://localhost:9999/test",
        "tier": "pre_approved",
        "capabilities": [],
    }, headers=auth_headers)
    assert r.status_code == 201
    tool_id = r.json()["id"]
    
    r = client.post(f"/api/v1/mcp-tools/{tool_id}/approve", json={"approved_by": "admin"}, headers=auth_headers)
    assert r.status_code == 200
    
    # 2. Mock ConnectionManager.broadcast to capture call
    with patch("backend.api.routes.mcp_tools.manager") as mock_manager:
        mock_manager.emit_mcp_tool_revoked = AsyncMock()
        
        # 3. Revoke the tool
        r = client.post(f"/api/v1/mcp-tools/{tool_id}/revoke", json={
            "revoked_by": "admin",
            "reason": "Test revocation"
        }, headers=auth_headers)
        assert r.status_code == 200
        
        # 4. Verify broadcast was called with correct args
        mock_manager.emit_mcp_tool_revoked.assert_called_once()
        call_kwargs = mock_manager.emit_mcp_tool_revoked.call_args.kwargs
        
        assert call_kwargs["tool_id"] == tool_id
        assert call_kwargs["tool_name"] == "Test Tool for Revoke"
        assert call_kwargs["reason"] == "Test revocation"
        assert call_kwargs["revoked_by"] == "admin"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/integration/test_mcp_revocation_broadcast.py::test_revoke_endpoint_broadcasts_websocket_event -v --no-cov
```
Expected: FAIL — broadcast not called

- [ ] **Step 3: Write minimal implementation**

In `backend/api/routes/mcp_tools.py`, modify `revoke_mcp_tool()` after `bridge.deregister(tool)` (~line 295):

```python
    # ... existing code ...
    bridge = _bridge()
    if bridge:
        bridge.deregister(tool)
    
    # ── Phase 15.2/6: Broadcast revocation to WebSocket clients ──
    try:
        from backend.api.routes.websocket import manager
        await manager.emit_mcp_tool_revoked(
            tool_id=str(tool.id),
            tool_name=tool.name,
            reason=req.reason,
            revoked_by=req.revoked_by,
        )
    except Exception as exc:
        # Non-fatal: frontend has polling fallback
        logger.warning("[MCPTools] WebSocket revocation broadcast failed: %s", exc)
    
    return MCPToolResponse(**tool.to_dict())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/integration/test_mcp_revocation_broadcast.py::test_revoke_endpoint_broadcasts_websocket_event -v --no-cov
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/mcp_tools.py backend/tests/integration/test_mcp_revocation_broadcast.py
git commit -m "feat(mcp-tools): broadcast revocation event on tool revoke"
```

---

### Task 3: Frontend Handler for `mcp_tool_revoked` Event

**Files:**
- Modify: `frontend/src/components/mcp/MCPToolRegistry.tsx` (in WebSocket effect, ~line 769)

**Interfaces:**
- Consumes: WebSocket message `{ type: "mcp_tool_revoked", tool_id: string, ... }`
- Produces: Updates `statsMap` state, triggers `fetchTools()`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/mcp/__tests__/MCPToolRegistry.revocation.test.tsx
import { render, screen, waitFor, act } from '@testing-library/react';
import { MCPToolRegistry } from '../MCPToolRegistry';
import { useWebSocketStore } from '@/store/websocketStore';

// Mock the WebSocket store
jest.mock('@/store/websocketStore', () => ({
  useWebSocketStore: jest.fn(),
}));

const mockUseWebSocketStore = useWebSocketStore as jest.Mock;

describe('MCPToolRegistry revocation handling', () => {
  const mockFetchTools = jest.fn();
  const mockSetStatsMap = jest.fn();
  
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseWebSocketStore.mockImplementation((selector) => selector({
      lastMessage: null,
    }));
  });

  it('removes revoked tool from statsMap and calls fetchTools on mcp_tool_revoked event', async () => {
    // This test requires the component to be mounted and the WebSocket effect to run
    // We'll test the handler logic directly by simulating the message
    
    const { result } = renderHook(() => useMCPToolRegistry());
    
    // Simulate the WebSocket message
    act(() => {
      result.current.handleWebSocketMessage({
        type: 'mcp_tool_revoked',
        tool_id: 'tool-123',
        tool_name: 'Test Tool',
        reason: 'Security issue',
        revoked_by: 'admin',
        timestamp: new Date().toISOString(),
      });
    });
    
    expect(mockSetStatsMap).toHaveBeenCalled();
    expect(mockFetchTools).toHaveBeenCalled();
  });
});
```

Note: Since this requires React testing setup, we'll verify manually in Step 4.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm test -- --testPathPattern=MCPToolRegistry.revocation --watchAll=false
```
Expected: FAIL or test not found (implementation not yet added)

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/mcp/MCPToolRegistry.tsx`, inside the `useEffect` that handles `lastMessage` (~line 769-785), add:

```typescript
// ── Phase 15.2/6: WebSocket listener for mcp_tool_revoked ───────────────────
useEffect(() => {
    if (!lastMessage) return;
    const msg = lastMessage as any;

    // Existing: mcp_stats_update
    if (msg.type === 'mcp_stats_update') { ... }

    // NEW: mcp_tool_revoked
    if (msg.type === 'mcp_tool_revoked') {
      // 1. Immediately remove from live stats map
      setStatsMap(prev => {
        const next = new Map(prev);
        next.delete(msg.tool_id);
        return next;
      });
      
      // 2. Refresh tool list to get updated status from API
      fetchTools();
    }
}, [lastMessage]);
```

- [ ] **Step 4: Manual verification**

Start the dev server and test end-to-end:

```bash
# Terminal 1: Start backend
cd backend && uvicorn main:app --reload

# Terminal 2: Start frontend
cd frontend && npm run dev

# Browser: Open MCP Tool Registry page
# 1. Propose and approve a tool
# 2. Click "Emergency Revoke" with a reason
# 3. Verify the tool shows "Revoked" status immediately in the same browser tab
# 4. Open a second browser tab to same page — should also show "Revoked" without refresh
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/mcp/MCPToolRegistry.tsx
git commit -m "feat(frontend): handle mcp_tool_revoked WebSocket event for instant UI update"
```

---

### Task 4: Add Integration Test for Full Flow

**Files:**
- Modify: `backend/tests/integration/test_mcp_revocation.py` (add new test method)

**Interfaces:**
- Verifies: End-to-end revocation → Redis + WebSocket broadcast

- [ ] **Step 1: Write the test**

```python
# Add to TestMCPSubSecondRevocation class in backend/tests/integration/test_mcp_revocation.py

def test_revoke_broadcasts_websocket_event(self, client, redis_client, db_session, auth_headers):
    """
    Revoking a tool should emit mcp_tool_revoked WebSocket event.
    Note: This tests the broadcast call, not WebSocket delivery (requires separate WS test infrastructure).
    """
    from unittest.mock import AsyncMock, patch
    
    tool_id = self._propose_tool(client, auth_headers, "test-revoke-ws", "http://localhost:9999/test-mcp-ws")
    self._approve_tool(client, auth_headers, tool_id)
    
    with patch("backend.api.routes.mcp_tools.manager") as mock_manager:
        mock_manager.emit_mcp_tool_revoked = AsyncMock()
        
        self._revoke_tool(client, auth_headers, tool_id)
        
        mock_manager.emit_mcp_tool_revoked.assert_called_once()
        call_kwargs = mock_manager.emit_mcp_tool_revoked.call_args.kwargs
        assert call_kwargs["tool_id"] == tool_id
```

- [ ] **Step 2: Run test**

```bash
cd backend && python -m pytest tests/integration/test_mcp_revocation.py::TestMCPSubSecondRevocation::test_revoke_broadcasts_websocket_event -v --no-cov
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_mcp_revocation.py
git commit -m "test: verify revoke endpoint broadcasts WebSocket event"
```

---

### Task 5: Update Documentation

**Files:**
- Modify: `docs/documents/agentium_guide.md` (if WebSocket events are documented)
- Modify: `README.md` (if real-time features are mentioned)

**Interfaces:**
- Documents: New `mcp_tool_revoked` WebSocket event type

- [ ] **Step 1: Search for WebSocket event documentation**

```bash
grep -r "mcp_stats_update" docs/
grep -r "WebSocket" docs/ | head -20
```

- [ ] **Step 2: Update relevant docs**

If WebSocket events are documented, add `mcp_tool_revoked` to the list with payload description.

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: document mcp_tool_revoked WebSocket event"
```

---

### Task 6: Final Verification & Cleanup

**Files:** None new — verify all works together

- [ ] **Step 1: Run full test suite for affected areas**

```bash
cd backend
python -m pytest tests/unit/test_websocket_revocation_broadcast.py -v --no-cov
python -m pytest tests/integration/test_mcp_revocation.py -v --no-cov
python -m pytest tests/integration/test_mcp_revocation_broadcast.py -v --no-cov
```

- [ ] **Step 2: Manual end-to-end test**

1. Start full stack (`docker-compose up -d` or local dev)
2. Open MCP Tool Registry in two browser tabs
3. Create → Approve → Revoke a tool in Tab 1
4. Verify Tab 2 updates to "Revoked" within 1 second
5. Verify no console errors in either tab

- [ ] **Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "fix: final polish for MCP revocation broadcast"
```

---

## Execution Order Summary

| Task | Description | Depends On |
|------|-------------|------------|
| 1 | Add `emit_mcp_tool_revoked` to ConnectionManager | — |
| 2 | Call broadcast from revoke endpoint | Task 1 |
| 3 | Frontend handler for `mcp_tool_revoked` | Task 1 (event type) |
| 4 | Integration test for full flow | Task 2 |
| 5 | Update documentation | Task 1-3 |
| 6 | Final verification | Task 1-5 |

**Total estimated time**: 30-45 minutes