# Fix WebSocket Heartbeat Load Test Failures

**Date**: 2026-11-10  
**Status**: Design Phase  
**Related**: Phase 18.2 Performance Regression Gate, Load Testing (Phase 21.5.2)

---

## Problem Statement

The Locust load test (performance-tests CI job) fails with:
- **WebSocket heartbeat_ping**: 92.41% failure rate (73 failures) — "Expected pong, received chat_message", "Expected pong, received message_start", "Expected pong, received agent_reassigned", "Expected pong, received message_end"
- **WebSocket chat_exchange**: 39.39% failure rate (13 failures) — "ConnectionClosedError: keepalive ping timeout; no close frame received"
- Test exits with code 1 after 10m 37s

### Root Cause

The test's `heartbeat()` method in `websocket_user.py` sends a ping and immediately calls `ws.recv()` expecting a pong. However, WebSocket is full-duplex — the server may send other messages (broadcasts, chat responses) before the pong arrives. The client receives whichever message arrives first, causing false failures.

The server correctly responds to ping with pong (see `websocket.py:950-955`), but the test doesn't correlate request/response.

---

## Solution: Request ID Correlation (Approach 1)

Add `request_id` to ping/pong messages for proper request/response correlation. This is the standard WebSocket pattern for bidirectional protocols.

### Component Changes

#### 1. Server: `backend/api/routes/websocket.py` (lines 950-955)

```python
# Current
if msg_type == "ping":
    await websocket.send_json({
        "type": "pong",
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
    })
    continue

# Fixed
if msg_type == "ping":
    await websocket.send_json({
        "type": "pong",
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
        "request_id": data.get("request_id"),  # Echo client's request_id
    })
    continue
```

#### 2. Client: `backend/tests/load/websocket_user.py` (heartbeat method, lines 136-170)

```python
@task(3)
def heartbeat(self):
    if not self.ws or not self.connected:
        return

    start_time = time.perf_counter()
    request_id = str(uuid.uuid4())
    try:
        ping_payload = json.dumps({"type": "ping", "timestamp": time.time(), "request_id": request_id})
        self.ws.send(ping_payload)

        # Loop until matching pong received (handles interleaved broadcasts)
        while True:
            reply = self.ws.recv(timeout=2.0)
            data = json.loads(reply)
            if data.get("type") == "pong" and data.get("request_id") == request_id:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                if _HAS_LOCUST:
                    events.request.fire(
                        request_type="WebSocket",
                        name="ws:heartbeat_ping",
                        response_time=duration_ms,
                        response_length=len(reply),
                        exception=None,
                    )
                break
            # Non-pong or mismatched request_id - continue waiting
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        if _HAS_LOCUST:
            events.request.fire(
                request_type="WebSocket",
                name="ws:heartbeat_ping",
                response_time=duration_ms,
                response_length=0,
                exception=exc,
            )
```

---

## Data Flow

```
Client                                    Server
  |-- ping {type:"ping", request_id:"uuid1"} -->|
  |                                        |-- broadcast: agent_spawned --> (other clients)
  |                                        |-- broadcast: task_update --> (other clients)
  |<-- pong {type:"pong", request_id:"uuid1"} --|
  |                                        |-- chat_message --> (this client, from earlier chat)
  |                                        |-- message_start --> (this client)
  |-- ping {type:"ping", request_id:"uuid2"} -->|
  |<-- pong {type:"pong", request_id:"uuid2"} --|
```

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Timeout (2s) | Count as failure, fire Locust event with exception |
| Connection closed | Count as failure (existing behavior) |
| Unexpected message type | Log but continue waiting for matching pong |
| Malformed JSON | Count as failure (existing behavior) |
| Mismatched request_id | Ignore, continue waiting |

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Heartbeat failure rate | 92.41% | <1% |
| Chat exchange failure rate | 39.39% | <1% |
| p95 heartbeat latency | Variable (queued) | <100ms |
| Test exit code | 1 | 0 |
| Overall test duration | 10m 37s | ~2m (120s time limit) |

---

## Testing

1. Run load test locally: `cd backend && locust -f tests/load/locustfile.py --headless -u 20 -r 5 --run-time 120s`
2. Verify heartbeat_ping failures <1%
3. Verify chat_exchange failures <1%
4. Verify p95 latency <100ms for ws:heartbeat_ping
5. CI performance-tests job passes (exit code 0)

---

## Implementation Plan

1. **Server fix**: Add `request_id` echo to pong handler in `websocket.py`
2. **Client fix**: Update `heartbeat()` in `websocket_user.py` to correlate by `request_id`
3. **Add import**: Add `import uuid` to `websocket_user.py` (if not present)
4. **Run local load test** to verify fix
5. **Commit and push** — CI will validate

---

## Files Modified

- `backend/api/routes/websocket.py` (lines 950-955)
- `backend/tests/load/websocket_user.py` (lines 136-170, plus imports)

---

## Rollback Plan

If issues arise:
- Revert `websocket.py` pong handler to original
- Revert `websocket_user.py` heartbeat method to original
- No database migrations or schema changes involved