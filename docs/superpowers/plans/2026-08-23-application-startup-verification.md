# Application Startup Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a verification procedure to confirm all 9 application startup items in TODO.md section 4.1 are functioning correctly.

**Architecture:** Leverage existing application startup mechanisms and logging to verify each initialization step completes successfully. The plan involves checking application logs for success/failure messages, verifying background processes are running, and testing API endpoints that depend on initialized services.

**Tech Stack:** Python, FastAPI, Docker, pytest, application logging system

## Global Constraints

- Must verify all 9 sub-items in TODO.md section 4.1
- Verification should be non-intrusive and not modify existing code
- Must work with existing application startup process
- Should provide clear pass/fail indicators for each verification item
- Use existing logging and status endpoints where available
---

### Task 1: Verify lifespan() completes all init steps without error

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs
- Produces: Pass/fail status for lifespan initialization

- [ ] **Step 1: Start application and capture logs**

```bash
# Start the application in background
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup to complete (adjust time as needed)
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee startup.log
# OR if running directly with uvicorn:
# cat startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify no errors in lifespan execution**

Check startup.log for:
- "✅ Database initialized"
- "✅ Default admin user created" (or "✅ Admin user permissions updated")  
- "✅ Fallback constitution seeded:" or "✅ Constitution already present:"
- "✅ Persistent Council already initialized" or "⏳ Persistent Council not yet initialized"
- "✅ API Manager initialized with universal provider support"
- "✅ Model Allocator initialized"
- "✅ Token Optimizer initialized"
- "✅ API Key Manager initialized with resilience"
- "✅ Idle Governance Engine and monitors started"
- "✅ Capability Registry loaded"
- "✅ MCP Tool Bridge initialized"
- "✅ Knowledge base bootstrapped"
- "🎉 Agentium startup complete!"

Expected: All success messages present, no error messages indicating failure

- [ ] **Step 3: Verify specific error handling behavior**

Test that non-fatal errors don't stop startup:
- Check for warning messages like "⚠️" that indicate non-fatal issues
- Verify application continues to start despite warnings

- [ ] **Step 4: Commit verification procedure**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add lifespan verification procedure for application startup"
```

### Task 2: Verify Security startup checks run (run_security_startup_checks)

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs
- Produces: Pass/fail status for security startup checks

- [ ] **Step 1: Start application with default MinIO credentials**

```bash
# Set environment variables for default MinIO credentials
export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin

# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee security-startup.log
# OR if running directly:
# cat security-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify security startup checks execute**

Check security-startup.log for:
- "SECURITY ALERT: MinIO/S3 object storage is configured with the well-known default credentials"
- Either:
  - "⚠️" warning message (if MINIO_BLOCK_DEFAULT_CREDS not set to true)
  - "❌" error message and startup failure (if MINIO_BLOCK_DEFAULT_CREDS=true)

Expected: Security startup check message appears in logs

- [ ] **Step 3: Verify behavior with non-default credentials**

```bash
# Set environment variables for non-default MinIO credentials
export MINIO_ROOT_USER=customuser
export MINIO_ROOT_PASSWORD=custompass123

# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee security-startup-good.log
# OR if running directly:
# cat security-startup-good.log

# Kill the background process
kill $APP_PID
```

Check security-startup-good.log for absence of security alert messages (since creds are not default)

- [ ] **Step 4: Commit security startup verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add security startup checks verification procedure"
```

### Task 3: Verify Workspace config validation runs

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs
- Produces: Pass/fail status for workspace config validation

- [ ] **Step 1: Start application with default workspace config**

```bash
# Start the application (default AGENTIUM_WORKSPACE_ENABLED=true)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee workspace-startup.log
# OR if running directly:
# cat workspace-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify workspace config validation executes**

Check workspace-startup.log for:
- Either:
  - "✅ Host workspace persistence configured" (if AGENTIUM_WORKSPACE_ROOT is under /host or /host_home)
  - "⚠️" warning message about workspace not being visible on host machine (if AGENTIUM_WORKSPACE_ROOT is not under /host or /host_home)

Expected: Workspace config validation message appears in logs

- [ ] **Step 3: Verify behavior when workspace disabled**

```bash
# Disable workspace feature
export AGENTIUM_WORKSPACE_ENABLED=false

# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee workspace-disabled.log
# OR if running directly:
# cat workspace-disabled.log

# Kill the background process
kill $APP_PID
```

Check workspace-disabled.log for absence of workspace validation messages (since feature is disabled)

- [ ] **Step 4: Commit workspace config verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add workspace config validation verification procedure"
```

### Task 4: Verify Constitution seed executes on first boot

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs, database state
- Produces: Pass/fail status for constitution seeding

- [ ] **Step 1: Start application with clean database (first boot scenario)**

```bash
# Ensure we have a clean state (for testing, we'd typically use a fresh DB)
# For actual verification, check logs from a fresh startup

# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee constitution-startup.log
# OR if running directly:
# cat constitution-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify constitution seed executes**

Check constitution-startup.log for:
- Either:
  - "✅ Fallback constitution seeded: v1.0.0" (when no active constitution exists)
  - "✅ Constitution already present: v1.0.0" (when constitution already exists)

Expected: Constitution seeding message appears in logs

- [ ] **Step 3: Verify constitution is actually in database**

```bash
# Check if constitution exists in database (requires db access)
# This would typically be done via a database query or API endpoint
# For simplicity in this plan, we'll rely on the log messages

# Alternative: Check via API if available
# curl http://localhost:8000/api/v1/constitution
```

- [ ] **Step 4: Commit constitution seed verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add constitution seed verification procedure"
```

### Task 5: Verify Persistent Council status check runs

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs
- Produces: Pass/fail status for persistent council status check

- [ ] **Step 1: Start application**

```bash
# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee council-startup.log
# OR if running directly:
# cat council-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify persistent council status check executes**

Check council-startup.log for:
- Either:
  - "✅ Persistent Council already initialized (Head 00001 present)"
  - "⏳ Persistent Council not yet initialized"
  - "⚠️ Persistent Council status check failed (non-fatal):" followed by error details

Expected: Persistent council status check message appears in logs

- [ ] **Step 3: Verify with HeadOfCouncil present vs absent**

This would require setting up two scenarios:
1. With HeadOfCouncil agent present in database (agentium_id="00001")
2. Without HeadOfCouncil agent (clean state or after deletion)

- [ ] **Step 4: Commit persistent council verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add persistent council status check verification procedure"
```

### Task 6: Verify API Manager, Model Allocator, Token Optimizer initialize

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs
- Produces: Pass/fail status for API Manager, Model Allocator, Token Optimizer initialization

- [ ] **Step 1: Start application**

```bash
# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee allocator-startup.log
# OR if running directly:
# cat allocator-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify all three components initialize**

Check allocator-startup.log for:
- "✅ API Manager initialized with universal provider support"
- "✅ Model Allocator initialized"
- "✅ Token Optimizer initialized" followed by:
  - "   - Idle Budget: $X.XX/day"
  - "   - Active Mode Budget: $X.XX/day"

Expected: All three initialization success messages appear in logs

- [ ] **Step 3: Verify Token Optimizer shows budget information**

Check that the Token Optimizer initialization log includes both idle budget and active budget amounts

- [ ] **Step 4: Commit allocator initialization verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add API Manager, Model Allocator, Token Optimizer initialization verification procedure"
```

### Task 7: Verify MCP Tool Bridge initializes (init_bridge)

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs
- Produces: Pass/fail status for MCP Tool Bridge initialization

- [ ] **Step 1: Start application**

```bash
# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee mcp-startup.log
# OR if running directly:
# cat mcp-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify MCP Tool Bridge initializes**

Check mcp-startup.log for:
- "✅ MCP Tool Bridge initialized — X approved tool(s) loaded" (where X is number of tools)
- "   - Agents can now discover MCP tools via GET /tools/"
- "   - MCP tools also visible at GET /tools/mcp"

Expected: MCP Tool Bridge initialization success message appears in logs

- [ ] **Step 3: Verify behavior when MCP Tool Bridge fails to initialize**

This would require mocking or causing a failure in the MCP tool bridge initialization to see the warning message:
- "⚠️ MCP Tool Bridge initialization failed:"
- "   - System will continue — MCP tools can be synced manually via approve endpoint"

- [ ] **Step 4: Commit MCP Tool Bridge verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add MCP Tool Bridge initialization verification procedure"
```

### Task 8: Verify Pricing sync runs in background

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs, background process verification
- Produces: Pass/fail status for pricing sync background execution

- [ ] **Step 1: Start application**

```bash
# Start the application in background
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup to ensure background tasks start
sleep 15

# Check if background pricing sync task is running
# We'll check via logs or by verifying the background task started

# Capture logs from startup period
docker logs agentium-backend 2>&1 | tee pricing-startup.log
# OR if running directly:
# cat pricing-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify pricing sync starts in background**

Check pricing-startup.log for:
- No explicit "pricing sync started" message in lifespan (it's started as background task)
- But look for evidence that background tasks were started:
  - "✅ Idle Governance Engine and monitors started"
  - "✅ Database Maintenance & Backup Scanners active"

The pricing sync is started as a background task in lifespan via:
```python
import asyncio
asyncio.create_task(run_background_sync())
```

So we need to verify the task was created. Best evidence is in logs showing the function was called.

- [ ] **Step 3: Alternative: Check for pricing sync activity via logs or API**

Since pricing sync runs in background, we can:
1. Check application logs periodically for pricing sync activity
2. Verify that pricing cache is being updated
3. Check if there are any API endpoints that show pricing sync status

For simplicity in verification, we'll confirm the background task creation logic exists in the code and trust that if the lifespan completes, the background task was started.

- [ ] **Step 4: Commit pricing sync verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add pricing sync background execution verification procedure"
```

### Task 9: Verify Idle Governance engine starts

**Files:**
- Modify: `docs/superpowers/plans/2026-08-23-application-startup-verification.md` (this file)

**Interfaces:**
- Consumes: Application startup logs, idle governance status API
- Produces: Pass/fail status for idle governance engine start

- [ ] **Step 1: Start application**

```bash
# Start the application
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for startup
sleep 10

# Capture logs
docker logs agentium-backend 2>&1 | tee idle-startup.log
# OR if running directly:
# cat idle-startup.log

# Kill the background process
kill $APP_PID
```

- [ ] **Step 2: Verify Idle Governance engine starts**

Check idle-startup.log for:
- "✅ Idle Governance Engine and monitors started"
- "   - Eternal Council and Background Health Scanners active"
- "   - Database Maintenance & Backup Scanners active"

Expected: Idle governance engine started message appears in logs

- [ ] **Step 3: Verify Idle Governance status via API**

```bash
# After application has started, check idle governance status
# curl http://localhost:8000/api/v1/governance/idle/status

# Expected response should show:
# {
#   "status": "running",
#   "idle_mode_active": true/false,
#   "time_since_last_user_activity": X,
#   "statistics": {...},
#   "persistent_council": {
#     "head": "00001",
#     "council_members": ["10001", "10002"]
#   }
# }
```

- [ ] **Step 4: Test pause/resume functionality**

```bash
# Test pausing idle governance
# curl -X POST http://localhost:8000/api/v1/governance/idle/pause

# Expected: {"status": "success", "message": "Idle governance paused"}

# Test resuming idle governance
# curl -X POST http://localhost:8000/api/v1/governance/idle/resume

# Expected: {"status": "success", "message": "Idle governance resumed"}
```

- [ ] **Step 5: Commit idle governance verification**

```bash
git add docs/superpowers/plans/2026-08-23-application-startup-verification.md
git commit -m "feat: add idle governance engine start verification procedure"
```

## Plan Summary

This plan provides verification procedures for all 9 application startup items in TODO.md section 4.1:

1. ✅ lifespan() completes all init steps without error
2. ✅ Security startup checks run (run_security_startup_checks)
3. ✅ Workspace config validation runs
4. ✅ Constitution seed executes on first boot
5. ✅ Persistent Council status check runs
6. ✅ API Manager, Model Allocator, Token Optimizer initialize
7. ✅ MCP Tool Bridge initializes (init_bridge)
8. ✅ Pricing sync runs in background
9. ✅ Idle Governance engine starts

Each task includes:
- Clear steps to execute the verification
- Expected log output or API responses
- git commit procedures for tracking changes
- Interface definitions showing what is consumed and produced

## Implementation Notes

The verification procedures are designed to be non-intrusive, leveraging existing application startup mechanisms, logging, and API endpoints. Where possible, they use the existing logging system to verify that each initialization step completed successfully.

For background processes like pricing sync, the verification focuses on confirming the background task was started during application initialization rather than waiting for the periodic task to execute, which would make verification take too long.

All verification steps can be performed manually or automated into test scripts as needed.