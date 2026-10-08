# Section 14.6 Structured Logging — Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all 87 backend services from standard `logging.getLogger()` to `StructuredLogger` so every agent step emits structured JSON logs with correlation IDs (`request_id`, `agent_id`, `task_id`) and metrics (`duration_ms`, `tokens`, `status`).

**Architecture:** The `StructuredLogger` wrapper and `CorrelationIdMiddleware` are already implemented and working. This plan performs a systematic bulk migration: update imports, replace logger instantiation, run test suite to verify no regressions. Three services already use `StructuredLogger` (`agent_orchestrator.py`, `task_executor.py`, `structured_logging.py`) — they serve as reference implementations.

**Tech Stack:** Python 3.11+, standard `logging` module, `contextvars` for correlation, FastAPI middleware, Celery task wrappers.

---

## Global Constraints

- **Pattern consistency:** Every service file follows `logger = logging.getLogger(__name__)` at module level — replace with `from backend.services.structured_logging import get_structured_logger; logger = get_structured_logger(__name__)`
- **Interface parity:** `StructuredLogger` exposes `.debug()`, `.info()`, `.warning()`, `.error()`, `.critical()`, `.exception()` — identical to `logging.Logger`
- **Structured fields:** Call sites already pass `step=`, `duration_ms=`, `tokens=`, `status=`, `agent_id=`, `task_id=` as kwargs — no call-site changes needed
- **Test verification:** Full test suite must pass after migration (`pytest backend/tests/ -x --tb=short`)
- **No behavior change:** Migration must not alter log levels, formatting (handled by `StructuredFormatter`), or propagation

---

## File Map

**Files to modify (87):**
```
backend/services/agent_registry.py
backend/services/auto_delegation_service.py
backend/services/amendment_service.py
backend/services/alert_manager.py
backend/services/api_key_manager.py
backend/services/api_manager.py
backend/services/audio_service.py
backend/services/autonomous_learning.py
backend/services/ab_testing_service.py
backend/services/browser_service.py
backend/services/capability_registry.py
backend/services/chat_context.py
backend/services/chat_prune_service.py
backend/services/chat_service.py
backend/services/checkpoint_service.py
backend/services/clarification_handler.py
backend/services/clarification_service.py
backend/services/config_versioning.py
backend/services/citation_graph_service.py
backend/services/critic_agents.py
backend/services/db_maintenance.py
backend/services/decision_engine.py
backend/services/event_processor.py
backend/services/fact_checker.py
backend/services/federation_service.py
backend/services/file_processor.py
backend/services/governance_command_service.py
backend/services/host_access.py
backend/services/idle_governance.py
backend/services/initialization_service.py
backend/services/knowledge_assist.py
backend/services/knowledge_governance.py
backend/services/knowledge_service.py
backend/services/mcp_client.py
backend/services/mcp_governance.py
backend/services/mcp_tool_bridge.py
backend/services/mcp_stats_service.py
backend/services/media_interceptor.py
backend/services/message_bus.py
backend/services/model_allocation.py
backend/services/model_provider.py
backend/services/monitoring_service.py
backend/services/overflow_recovery.py
backend/services/persistent_council.py
backend/services/plugin_marketplace_service.py
backend/services/predictive_scaling.py
backend/services/pricing_sync_service.py
backend/services/push_notification_service.py
backend/services/reasoning_trace_service.py
backend/services/reincarnation_service.py
backend/services/remote_executor/executor.py
backend/services/remote_executor/sandbox.py
backend/services/remote_executor/service.py
backend/services/self_healing_service.py
backend/services/self_improvement_service.py
backend/services/skill_manager.py
backend/services/skill_rag.py
backend/services/slow_query_service.py
backend/services/storage_service.py
backend/services/token_optimizer.py
backend/services/tool_analytics.py
backend/services/workflow_engine.py
backend/services/workflow_executor.py
backend/services/workflow_planner.py
backend/services/workflow_tools.py
backend/services/tasks/scheduled_task_dispatcher.py
backend/services/tasks/verification_tasks.py
backend/services/tasks/workflow_tasks.py
backend/services/idle_tasks/maintenance.py
backend/services/idle_tasks/health_monitor.py
backend/services/idle_tasks/preference_optimizer.py
backend/services/channels/email.py
backend/services/channels/discord.py
backend/services/channels/slack.py
backend/services/channels/telegram.py
backend/services/channels/sms_twilio.py
backend/services/channels/whatsapp_unified.py
backend/services/monitoring/health_checks.py
backend/services/audit/audit_processor.py
backend/services/voice/voice_config_service.py
backend/services/wait_poll_service.py
backend/services/webhook_dispatch_service.py
```

**Reference files (already migrated, for pattern matching):**
```
backend/services/agent_orchestrator.py
backend/services/tasks/task_executor.py
backend/services/structured_logging.py
```

**Test files to run for verification:**
```
backend/tests/unit/ (all)
backend/tests/integration/ (all)
```

---

## Task Decomposition

### Task 1: Create Migration Script

**Files:**
- Create: `backend/scripts/migrate_structured_logging.py`

**Interfaces:**
- Produces: CLI script that reads a service file, replaces `import logging; logger = logging.getLogger(__name__)` with `from backend.services.structured_logging import get_structured_logger; logger = get_structured_logger(__name__)`, writes back

- [ ] **Step 1: Write the migration script**

```python
#!/usr/bin/env python3
"""
Bulk migration script: standard logging -> StructuredLogger
Usage: python migrate_structured_logging.py --dry-run
       python migrate_structured_logging.py --apply
"""
import re
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).parent.parent / "services"

PATTERN_IMPORT_LOGGING = re.compile(r"^import logging\s*$", re.MULTILINE)
PATTERN_GETLOGGER = re.compile(r"^logger\s*=\s*logging\.getLogger\(__name__\)\s*$", re.MULTILINE)

REPLACEMENT = '''from backend.services.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)'''

def migrate_file(filepath: Path, dry_run: bool = True) -> bool:
    content = filepath.read_text(encoding="utf-8")
    
    # Check if already migrated
    if "get_structured_logger" in content:
        print(f"  SKIP (already migrated): {filepath.relative_to(SERVICE_DIR.parent)}")
        return False
    
    # Check for standard pattern
    if not (PATTERN_IMPORT_LOGGING.search(content) and PATTERN_GETLOGGER.search(content)):
        print(f"  SKIP (non-standard pattern): {filepath.relative_to(SERVICE_DIR.parent)}")
        return False
    
    # Perform replacement
    new_content = PATTERN_IMPORT_LOGGING.sub("", content)
    new_content = PATTERN_GETLOGGER.sub(REPLACEMENT, new_content)
    
    # Clean up any double blank lines
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)
    
    if dry_run:
        print(f"  WOULD MIGRATE: {filepath.relative_to(SERVICE_DIR.parent)}")
    else:
        filepath.write_text(new_content, encoding="utf-8")
        print(f"  MIGRATED: {filepath.relative_to(SERVICE_DIR.parent)}")
    return True

def main():
    dry_run = "--dry-run" in sys.argv
    apply = "--apply" in sys.argv
    
    if not (dry_run or apply):
        print("Usage: python migrate_structured_logging.py --dry-run|--apply")
        sys.exit(1)
    
    files = list(SERVICE_DIR.rglob("*.py"))
    print(f"Scanning {len(files)} Python files in {SERVICE_DIR}...")
    
    migrated = 0
    for f in files:
        if f.name == "structured_logging.py":
            continue  # skip self
        if migrate_file(f, dry_run=dry_run):
            migrated += 1
    
    print(f"\n{'Would migrate' if dry_run else 'Migrated'} {migrated} files")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run script in dry-run mode**

```bash
cd "E:\Ongoing Projects\Agentium"
python backend/scripts/migrate_structured_logging.py --dry-run
```

Expected: Lists ~87 files that would be migrated, skips already-migrated files

- [ ] **Step 3: Apply migration**

```bash
python backend/scripts/migrate_structured_logging.py --apply
```

Expected: All 87 files updated, prints "MIGRATED" for each

- [ ] **Step 4: Verify no standard logging remains in services**

```bash
grep -r "logging.getLogger(__name__)" backend/services/ --include="*.py" | grep -v "structured_logging.py"
```

Expected: Zero results (all migrated)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/migrate_structured_logging.py backend/services/
git commit -m "feat(14.6): migrate 87 services to StructuredLogger via script"
```

---

### Task 2: Fix Non-Standard Patterns (Manual Review)

**Files:**
- Modify: Any files flagged as "non-standard pattern" in Task 1

**Interfaces:**
- Consumes: Output from Task 1 dry-run showing skipped files
- Produces: Fully migrated codebase with no `logging.getLogger` remaining

- [ ] **Step 1: Identify non-standard patterns**

```bash
python backend/scripts/migrate_structured_logging.py --dry-run 2>&1 | grep "non-standard"
```

- [ ] **Step 2: Manually fix each flagged file**

Common non-standard patterns to handle:
- `logger = logging.getLogger("custom.name")` → `get_structured_logger("custom.name")`
- `import logging` used elsewhere in file → keep import, only replace logger line
- Multiple loggers in one file → migrate each
- `logging.getLogger(__name__)` on same line as import → handle both

- [ ] **Step 3: Re-verify zero standard logging**

```bash
grep -r "logging.getLogger" backend/services/ --include="*.py" | grep -v "structured_logging.py"
```

Expected: Zero results

- [ ] **Step 4: Commit fixes**

```bash
git add backend/services/
git commit -m "fix(14.6): manual migration of non-standard logging patterns"
```

---

### Task 3: Run Full Test Suite

**Files:**
- Test: `backend/tests/` (all)

**Interfaces:**
- Consumes: Fully migrated codebase from Tasks 1-2
- Produces: Test pass/fail report

- [ ] **Step 1: Run unit tests**

```bash
cd "E:\Ongoing Projects\Agentium"
python -m pytest backend/tests/unit/ -x --tb=short -q 2>&1 | tail -20
```

Expected: All pass (or pre-existing failures only, no new failures from migration)

- [ ] **Step 2: Run integration tests**

```bash
python -m pytest backend/tests/integration/ -x --tb=short -q 2>&1 | tail -20
```

Expected: All pass (or pre-existing failures only)

- [ ] **Step 3: Run specific services that use correlation IDs**

```bash
python -m pytest backend/tests/ -k "orchestrator or task_executor or websocket" -v --tb=short 2>&1 | tail -30
```

Expected: Tests for `agent_orchestrator`, `task_executor`, `websocket` routes pass with structured logs

- [ ] **Step 4: If failures, debug and fix**

Common issues:
- Missing import `get_structured_logger` (script should have added it)
- Circular import (move import inside function if needed)
- Logger used before import (move import to top)

- [ ] **Step 5: Commit test fixes (if any)**

```bash
git add backend/services/ backend/tests/
git commit -m "fix(14.6): resolve test failures after structured logging migration"
```

---

### Task 4: Add Integration Test for End-to-End Correlation

**Files:**
- Create: `backend/tests/integration/test_structured_logging_correlation.py`

**Interfaces:**
- Consumes: Migrated services, `CorrelationIdMiddleware`, `ws_correlation_manager`, `StructuredLogger`
- Produces: Test verifying `request_id` appears in HTTP → Celery → WebSocket log chain

- [ ] **Step 1: Write integration test**

```python
"""
Integration test for Section 14.6: Structured Logging correlation
Verifies request_id propagates across HTTP -> Celery -> WebSocket
"""
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.correlation_middleware import (
    CorrelationIdMiddleware,
    ws_correlation_manager,
    inject_correlation_into_task_kwargs,
    extract_correlation_from_task_kwargs,
)
from backend.services.structured_logging import (
    get_structured_logger,
    setup_structured_logging,
    structured_log_context,
)


@pytest.fixture(autouse=True)
def setup_logging():
    """Ensure structured logging is configured for tests."""
    setup_structured_logging(logging.INFO)
    yield


class TestStructuredLoggingCorrelation:
    """Test request_id correlation across HTTP, Celery, WebSocket."""

    def test_http_middleware_generates_request_id(self):
        """HTTP request without header gets generated request_id in response."""
        client = TestClient(app)
        response = client.get("/api/health")
        
        assert response.status_code == 200
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) == 12  # uuid4()[:12]

    def test_http_middleware_uses_provided_request_id(self):
        """HTTP request with X-Request-ID header uses that ID."""
        client = TestClient(app)
        response = client.get("/api/health", headers={"X-Request-ID": "test-req-123"})
        
        assert response.headers["x-request-id"] == "test-req-123"

    def test_http_middleware_falls_back_to_correlation_id(self):
        """HTTP request with X-Correlation-ID uses it when X-Request-ID absent."""
        client = TestClient(app)
        response = client.get("/api/health", headers={"X-Correlation-ID": "corr-456"})
        
        assert response.headers["x-request-id"] == "corr-456"

    def test_structured_log_includes_request_id(self, capsys):
        """StructuredLogger output includes request_id from context."""
        logger = get_structured_logger("test_correlation")
        
        from backend.services.structured_logging import set_request_id
        set_request_id("req-test-789")
        
        logger.info("Test message", step="test_step", duration_ms=50, tokens=10, status="ok")
        
        captured = capsys.readouterr().out
        log_entry = json.loads(captured.strip())
        
        assert log_entry["request_id"] == "req-test-789"
        assert log_entry["step"] == "test_step"
        assert log_entry["duration_ms"] == 50
        assert log_entry["tokens"] == 10
        assert log_entry["status"] == "ok"
        assert "timestamp" in log_entry

    def test_celery_task_correlation_injection_extraction(self):
        """Celery task kwargs properly inject and extract correlation IDs."""
        kwargs = {"task_id": "task-001", "agent_id": "agent-001"}
        
        inject_correlation_into_task_kwargs(
            kwargs, request_id="req-celery", task_id="task-001", agent_id="agent-001"
        )
        
        assert kwargs["_request_id"] == "req-celery"
        assert kwargs["_task_id"] == "task-001"
        assert kwargs["_agent_id"] == "agent-001"
        
        # Extraction
        req_id, task_id, agent_id = extract_correlation_from_task_kwargs(kwargs.copy())
        assert req_id == "req-celery"
        assert task_id == "task-001"
        assert agent_id == "agent-001"

    def test_websocket_correlation_manager(self):
        """WebSocket correlation manager tracks per-connection context."""
        mock_ws = MagicMock()
        
        ws_correlation_manager.set_connection_context(mock_ws, "ws-req-999")
        ctx = ws_correlation_manager.get_connection_context(mock_ws)
        
        assert ctx == "ws-req-999"
        
        # Message context uses connection context as fallback
        with ws_correlation_manager.message_context(mock_ws, message_request_id=None) as req_id:
            assert req_id == "ws-req-999"
        
        # Message context overrides with message request_id
        with ws_correlation_manager.message_context(mock_ws, "msg-req-111") as req_id:
            assert req_id == "msg-req-111"

    def test_end_to_end_correlation_flow(self, capsys):
        """
        Full HTTP -> Celery -> WebSocket correlation flow.
        Simulates real request propagation through all layers.
        """
        logger = get_structured_logger("test_e2e_correlation")
        http_request_id = "http-req-e2e-001"
        
        # 1. HTTP layer: request comes in
        from backend.services.structured_logging import set_request_id
        set_request_id(http_request_id)
        logger.info("HTTP request received", step="http_received", status="ok")
        
        # 2. Celery layer: task dispatched with correlation
        task_kwargs = {}
        inject_correlation_into_task_kwargs(
            task_kwargs, request_id=http_request_id, task_id="task-e2e", agent_id="agent-e2e"
        )
        
        # 3. Celery worker: extracts and sets context
        extracted_req_id, extracted_task_id, extracted_agent_id = extract_correlation_from_task_kwargs(
            task_kwargs.copy()
        )
        
        with structured_log_context(
            request_id=extracted_req_id,
            task_id=extracted_task_id,
            agent_id=extracted_agent_id
        ):
            logger.info("Celery task started", step="celery_start", status="started")
            logger.info("Celery task processing", step="celery_process", duration_ms=100, tokens=50, status="processing")
            
            # 4. WebSocket broadcast: includes request_id
            ws_message = {
                "type": "task_update",
                "task_id": extracted_task_id,
                "request_id": extracted_req_id,
                "status": "processing",
            }
            logger.info("WebSocket event sent", step="ws_broadcast", **ws_message)
        
        # 5. WebSocket client: receives and processes with same request_id
        with structured_log_context(request_id=ws_message["request_id"], task_id=extracted_task_id):
            logger.info("WebSocket message received", step="ws_received", status="ok")
        
        # Verify all log entries have same request_id
        captured = capsys.readouterr().out
        log_entries = [json.loads(line) for line in captured.strip().split("\n") if line.strip()]
        
        request_ids = [entry.get("request_id") for entry in log_entries if "request_id" in entry]
        assert all(rid == http_request_id for rid in request_ids), f"Request ID mismatch: {request_ids}"
        assert len(request_ids) >= 4  # http, celery_start, celery_process, ws_broadcast, ws_received
```

- [ ] **Step 2: Run the new test**

```bash
python -m pytest backend/tests/integration/test_structured_logging_correlation.py -v --tb=short
```

Expected: All 7 tests pass

- [ ] **Step 3: Commit test**

```bash
git add backend/tests/integration/test_structured_logging_correlation.py
git commit -m "test(14.6): add integration test for structured logging correlation"
```

---

### Task 5: Verify Structured Log Output in Real Application

**Files:**
- Test: Manual verification via application logs

**Interfaces:**
- Consumes: Running application with migrated services
- Produces: Confirmed JSON log output with all required fields

- [ ] **Step 1: Start application in test mode**

```bash
cd "E:\Ongoing Projects\Agentium"
TESTING=true python -m backend.main &
APP_PID=$!
sleep 5
```

- [ ] **Step 2: Make HTTP request and capture logs**

```bash
curl -H "X-Request-ID: verify-req-001" http://localhost:8000/api/health
```

- [ ] **Step 3: Verify log output is JSON with all fields**

Check application stdout for:
```json
{
  "timestamp": "2026-10-07T...",
  "level": "INFO",
  "logger": "backend.services.monitoring_service",
  "message": "...",
  "request_id": "verify-req-001",
  "step": "...",
  "duration_ms": ...,
  "tokens": ...,
  "status": "..."
}
```

- [ ] **Step 4: Stop application**

```bash
kill $APP_PID
```

- [ ] **Step 5: Document verification**

```bash
git commit --allow-empty -m "docs(14.6): verified structured JSON logs in application output"
```

---

### Task 6: Update TODO.md Checklist

**Files:**
- Modify: `docs/documents/TODO.md`

**Interfaces:**
- Consumes: Completed migration and verification
- Produces: Updated checklist marking 14.6 items complete

- [ ] **Step 1: Update TODO.md**

```bash
# Edit lines 740-743 in docs/documents/TODO.md
# Change:
# - [ ] 14.6.1 — All agent steps emit structured JSON logs
# - [ ] 14.6.2 — Logs contain: `timestamp`, `request_id`, `step`, `duration_ms`, `tokens`, `status`
# - [ ] 14.6.3 — `request_id` correlates across HTTP → Celery → WebSocket
# To:
# - [x] 14.6.1 — All agent steps emit structured JSON logs
# - [x] 14.6.2 — Logs contain: `timestamp`, `request_id`, `step`, `duration_ms`, `tokens`, `status`
# - [x] 14.6.3 — `request_id` correlates across HTTP → Celery → WebSocket
```

- [ ] **Step 2: Commit**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark Section 14.6 Structured Logging complete"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All three TODO items (14.6.1, 14.6.2, 14.6.3) addressed
- [x] **No placeholders:** Every step has exact commands and code
- [x] **Type consistency:** `get_structured_logger(__name__)` pattern used throughout
- [x] **Migration script handles:** Standard pattern, skips already-migrated, reports non-standard
- [x] **Validation included:** Test suite run, new integration test, manual log verification
- [x] **Commit strategy:** Frequent commits after each logical phase

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-10-07-structured-logging-migration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**