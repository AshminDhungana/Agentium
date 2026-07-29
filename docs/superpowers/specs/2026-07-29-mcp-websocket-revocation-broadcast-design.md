# MCP WebSocket Revocation Broadcast Design

**Date**: 2026-07-29  
**Status**: Approved for Implementation  
**Related**: Phase 6 — "Real-time MCP tool usage stats; revoked tools unavailable < 1 second"  
**Gap Addressed**: While revocation enforcement is sub-second via Redis SET, connected clients were not notified in real-time.

---

## 1. Problem Statement

The MCP revocation system (Phase 15.2) provides:
- ✅ Sub-second revocation **enforcement** via Redis SET (`agentium:mcp:revoked`)
- ✅ Real-time **usage stats** broadcast via WebSocket every 30s (`mcp_stats_update`)
- ❌ **Real-time revocation notification** — clients discover revocation only on next stats poll (up to 60s) or next execution attempt

This design adds a WebSocket event `mcp_tool_revoked` broadcast immediately when an admin revokes a tool, completing the "real-time" experience.

---

## 2. Architecture

### 2.1 Event Flow

```
Admin clicks "Emergency Revoke"
        ↓
POST /api/v1/mcp-tools/{id}/revoke
        ↓
mcp_governance.revoke_mcp_tool()
  ├─ DB: UPDATE mcp_tools SET status='revoked' WHERE id=...
  ├─ Redis: SADD agentium:mcp:revoked "tool_id"
  └─ WebSocket: broadcast mcp_tool_revoked event  ← NEW
        ↓
Frontend receives event → updates local state → re-renders
```

### 2.2 Key Properties

| Property | Value |
|----------|-------|
| **Latency** | < 100ms end-to-end (Redis write + WebSocket broadcast) |
| **Reliability** | Fail-soft: broadcast failure is logged but doesn't block revocation |
| **Ordering** | Broadcast occurs AFTER successful Redis write |
| **Scope** | All authenticated WebSocket connections (same as `mcp_stats_update`) |

---

## 3. Backend Changes

### 3.1 WebSocket Manager — `backend/api/routes/websocket.py`

Add new typed broadcast method to `ConnectionManager` class:

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

### 3.2 Revoke Endpoint — `backend/api/routes/mcp_tools.py`

Modify `revoke_mcp_tool()` to broadcast after successful revocation:

```python
@router.post("/{tool_id}/revoke", ...)
async def revoke_mcp_tool(...):
    # ... existing validation ...
    
    svc = _governance(db)
    try:
        tool = svc.revoke_mcp_tool(tool_id, revoked_by=req.revoked_by, reason=req.reason)
    except ValueError as exc:
        raise NotFoundError(...)
    
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

---

## 4. Frontend Changes

### 4.1 WebSocket Listener — `frontend/src/components/mcp/MCPToolRegistry.tsx`

Add handler in the existing WebSocket effect (around line 769):

```typescript
// Inside useEffect listening to `lastMessage` from WebSocket store
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

---

## 5. WebSocket Event Specification

### 5.1 Event: `mcp_tool_revoked`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Always `"mcp_tool_revoked"` |
| `tool_id` | string (UUID) | Yes | Database UUID of revoked tool |
| `tool_name` | string | Yes | Human-readable tool name |
| `reason` | string | Yes | Revocation reason from admin |
| `revoked_by` | string | Yes | Agentium ID of revoking admin |
| `timestamp` | string (ISO8601) | Yes | UTC timestamp of revocation |

### 5.2 Example Payload

```json
{
  "type": "mcp_tool_revoked",
  "tool_id": "a1b2c3d4e5f6789012345678",
  "tool_name": "Weather API",
  "reason": "Security vulnerability in v2.3 — CVE-2026-12345",
  "revoked_by": "00001",
  "timestamp": "2026-07-29T14:32:15.123Z"
}
```

---

## 6. Error Handling & Fallbacks

| Failure Point | Behavior |
|---------------|----------|
| WebSocket broadcast fails | Log warning; revocation still completes; clients fall back to 60s polling |
| Redis write fails (existing) | Already logged as CRITICAL; broadcast not attempted |
| No connected clients | `broadcast()` handles gracefully (no-op) |
| Frontend disconnected | On reconnect, `fetchTools()` picks up revoked status |

---

## 7. Testing

### 7.1 Integration Test Addition

Extend `backend/tests/integration/test_mcp_revocation.py`:

```python
def test_revoke_broadcasts_websocket_event(self, client, redis_client, db_session, auth_headers):
    """Revoking a tool should emit mcp_tool_revoked WebSocket event."""
    tool_id = self._propose_tool(client, auth_headers, "test-revoke-ws", "http://localhost:9999/test-mcp-ws")
    self._approve_tool(client, auth_headers, tool_id)
    
    # Capture WebSocket events (requires test WebSocket connection)
    # ... test helper to connect and capture events ...
    
    self._revoke_tool(client, auth_headers, tool_id)
    
    # Assert event was broadcast with correct payload
    assert ws_event_received["type"] == "mcp_tool_revoked"
    assert ws_event_received["tool_id"] == tool_id
```

### 7.2 Manual Verification

1. Connect two browser tabs to the MCP Tool Registry
2. In Tab 1, approve a tool
3. In Tab 1, click "Emergency Revoke" with a reason
4. Verify Tab 2 shows "Revoked" status within < 1 second without refresh

---

## 8. Scope & Non-Goals

### In Scope
- Backend WebSocket broadcast on revoke
- Frontend handler for immediate UI update
- Integration test coverage

### Out of Scope
- Re-approval broadcast (can be added later if needed)
- Per-user filtering (all sovereign connections receive all events)
- Historical event replay (stateless broadcast like `mcp_stats_update`)

---

## 9. Dependencies

- Existing: `ConnectionManager.broadcast()` (websocket.py:228)
- Existing: `mcp_stats_service.add_to_revoked()` (mcp_stats_service.py:188)
- Existing: Frontend `useWebSocketStore` for message delivery

---

## 10. Rollback Plan

If issues arise:
1. Remove `emit_mcp_tool_revoked` call from `revoke_mcp_tool()`
2. Remove handler from `MCPToolRegistry.tsx`
3. System reverts to 60s polling fallback — no data loss, only latency increase