# Fix WebSocket Heartbeat Load Test Failures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the WebSocket heartbeat ping/pong correlation in load tests by adding request_id to ping/pong messages, eliminating false failures from interleaved broadcast messages.

**Architecture:** Add request_id correlation to WebSocket ping/pong protocol. Server echoes client's request_id in pong response. Client loops recv() until matching pong received. This is the standard pattern for bidirectional WebSocket protocols.

**Tech Stack:** FastAPI WebSocket, python-websockets (sync client), Locust load testing, python-jose for JWT

## Global Constraints

- Python 3.11+, FastAPI, python-websockets sync client
- Locust 2.x for load testing
- No new dependencies — use existing uuid, json, time modules
- Target: <1% heartbeat failure rate, <100ms p95 latency, exit code 0
- Changes only to: `backend/api/routes/websocket.py` and `backend/tests/load/websocket_user.py`

---

### Task 1: Add request_id Echo to Server Pong Handler

**Files:**
- Modify: `backend/api/routes/websocket.py:950-955`

**Interfaces:**
- Consumes: WebSocket message dict with optional `request_id` field
- Produces: WebSocket response dict with `type="pong"`, `timestamp`, and echoed `request_id`

- [ ] **Step 1: Read current pong handler**

```bash
# View the current ping handler
sed -n '948,960p' backend/api/routes/websocket.py
```

Expected output showing current handler at lines 950-955.

- [ ] **Step 2: Modify pong handler to echo request_id**

```python
# backend/api/routes/websocket.py:950-955
                    # ── Ping / heartbeat ──────────────────────────────────────────────
                    if msg_type == "ping":
                        await websocket.send_json({
                            "type":      "pong",
                            "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
                            "request_id": data.get("request_id"),  # Echo client's request_id
                        })
                        continue
```

- [ ] **Step 3: Verify syntax and run quick test**

```bash
cd backend && python -c "from api.routes import websocket; print('Import OK')"
```

Expected: No syntax errors, "Import OK"

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/websocket.py
git commit -m "feat(ws): echo request_id in pong response for heartbeat correlation"
```

---

### Task 2: Update Client Heartbeat to Correlate by request_id

**Files:**
- Modify: `backend/tests/load/websocket_user.py:1-206` (heartbeat method lines 136-170, add uuid import)

**Interfaces:**
- Consumes: WebSocket connection (self.ws), Locust events
- Produces: Locust request events for `ws:heartbeat_ping` with correlated response times

- [ ] **Step 1: Read current heartbeat method**

```bash
# View current heartbeat method
sed -n '135,175p' backend/tests/load/websocket_user.py
```

Expected output showing current heartbeat method.

- [ ] **Step 2: Add uuid import if not present**

```bash
# Check imports at top of file
head -20 backend/tests/load/websocket_user.py
```

If `uuid` not in imports, add it after `import time` (around line 15).

- [ ] **Step 3: Replace heartbeat method with correlated version**

```python
# backend/tests/load/websocket_user.py:136-170
    @task(3)
    def heartbeat(self):
        """Send ping message and verify pong response with request_id correlation."""
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

- [ ] **Step 4: Verify syntax**

```bash
cd backend && python -c "from tests.load.websocket_user import WebSocketUser; print('Import OK')"
```

Expected: No syntax errors, "Import OK"

- [ ] **Step 5: Commit**

```bash
git add backend/tests/load/websocket_user.py
git commit -m "feat(load-test): correlate heartbeat ping/pong by request_id to handle interleaved messages"
```

---

### Task 3: Run Local Load Test to Verify Fix

**Files:**
- Test: `backend/tests/load/locustfile.py` (run via Locust)

**Interfaces:**
- Consumes: Modified server and client code
- Produces: Locust report with <1% heartbeat failure rate

- [ ] **Step 1: Start backend server in background**

```bash
cd backend
# Ensure TESTING mode is set
export TESTING=true
export SECRET_KEY="test-secret-key-for-ci"
# Start server
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 3  # wait for startup
```

- [ ] **Step 2: Run Locust load test (headless, 20 users, 120s)**

```bash
cd backend
locust -f tests/load/locustfile.py --headless -u 20 -r 5 --run-time 120s --host http://localhost:8000 2>&1 | tee locust_output.txt
```

- [ ] **Step 3: Kill server**

```bash
kill $SERVER_PID
```

- [ ] **Step 4: Verify results**

```bash
# Check heartbeat failure rate
grep "ws:heartbeat_ping" locust_output.txt | tail -5
# Check chat_exchange failure rate
grep "ws:chat_exchange" locust_output.txt | tail -5
# Check exit code
echo $?
```

Expected:
- `ws:heartbeat_ping` failures < 1%
- `ws:chat_exchange` failures < 1%
- Exit code 0

- [ ] **Step 5: Commit (if tests pass)**

```bash
git add -A
git commit -m "test: verify WebSocket heartbeat fix passes load test"
```

---

### Task 4: Run Unit Tests for WebSocket Module

**Files:**
- Test: Any existing WebSocket-related tests

**Interfaces:**
- Consumes: Modified server code
- Produces: Passing unit tests

- [ ] **Step 1: Find and run WebSocket-related tests**

```bash
cd backend
# Search for WebSocket tests
find tests -name "*.py" -exec grep -l "websocket\|WebSocket" {} \;
```

- [ ] **Step 2: Run found tests**

```bash
# Run any WebSocket tests found
pytest tests/ -k "websocket" -v
# Or run all tests to ensure no regression
pytest tests/ -x -v 2>&1 | head -100
```

Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git commit -am "test: all WebSocket tests pass after heartbeat fix" || true
```

---

### Task 5: Push and Verify CI

**Files:**
- None (git push)

**Interfaces:**
- Consumes: All committed changes
- Produces: Green CI pipeline

- [ ] **Step 1: Push to remote**

```bash
git push origin main
```

- [ ] **Step 2: Monitor CI performance-tests job**

Wait for GitHub Actions to complete. Check:
- Job `performance-tests` passes (exit code 0)
- Locust report shows <1% heartbeat failures
- Overall test duration ~2 minutes

---

## Plan Self-Review

**Spec Coverage Check:**
- ✅ Server echoes request_id in pong (Task 1)
- ✅ Client correlates by request_id (Task 2)
- ✅ Error handling for timeout/connection close (Task 2, existing)
- ✅ Success criteria verified locally (Task 3)
- ✅ Unit tests pass (Task 4)
- ✅ CI validation (Task 5)

**Placeholder Scan:** No TBD/TODO/implement-later — all steps have exact code/commands

**Type Consistency:** 
- Server: `data.get("request_id")` → echoed in response
- Client: `str(uuid.uuid4())` sent in ping, matched in pong
- Both use same field name `request_id`

**File Paths:** All exact, relative to repo root

---

**Plan complete and saved to** `docs/superpowers/plans/2026-11-10-fix-websocket-heartbeat-load-test.md`

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration  
**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**