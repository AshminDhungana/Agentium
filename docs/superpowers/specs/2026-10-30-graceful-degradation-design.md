# Graceful Degradation & Component Fallback — Design Spec

**Task**: 21.5.1 — Verify resilience mechanisms (circuit breakers, cached fallbacks, degraded operation indicators) when LLMs, DB, or search providers fail.

**Date**: 2026-10-30
**Status**: Draft (awaiting user review)
**Related**: `docs/documents/TODO.md` line 1017

---

## 1. Architecture Overview

### 1.1 Goal
Verify and enhance the existing graceful degradation mechanisms across all failure domains (LLM providers, Database, Vector Search, Storage) with automated integration tests and operational observability.

### 1.2 System Boundaries & Current State

| Domain | Current Mechanism | Verification Gap |
|--------|------------------|------------------|
| **LLM Providers** | `ProviderCircuitBreaker` (closed/open/half-open), fallback configs (max 3), exponential backoff + jitter, `Retry-After` parsing | No tests simulating provider failures / circuit state transitions |
| **Database** | SQLAlchemy pool, health monitor `system_resource_check` | No tests for DB connection exhaustion / pool saturation |
| **Vector Search (ChromaDB)** | HTTP client with 3-attempt retry → Local `PersistentClient` fallback | No tests for HTTP→Local fallback trigger |
| **Storage (S3/MinIO)** | `_S3Backend` → `_LocalBackend` automatic fallback at startup | No tests for runtime S3 failure → Local failover |
| **Task Execution** | `task_degraded` WebSocket broadcast on provider exhaustion | No verification the broadcast fires with correct payload |
| **Health Monitoring** | 5 idle tasks broadcasting `system_alert` | No tests validating alert payloads / triggers |

### 1.3 Design Principle
**Test the seams, not the internals** — Each integration test exercises a public interface (LLMClient.generate, VectorStore.query, StorageService.upload) under simulated failure conditions and asserts on observable outcomes (fallback used, circuit opened, WebSocket event emitted, health endpoint reflects degraded state).

---

## 2. Components & Test Strategy

### 2.1 Test Infrastructure Components

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| **`FailureSimulator`** | Context manager to inject failures at specific seams | Patches `httpx.AsyncClient.request`, `sqlalchemy.Engine.connect`, `chromadb.HttpClient`, `boto3.client` |
| **`CircuitBreakerInspector`** | Read-only access to `ProviderCircuitBreaker` internal state for assertions | Exposes `state`, `failure_count`, `last_failure_time`, `success_count_in_half_open` |
| **`WebSocketEventCapture`** | Captures broadcasts from `manager.broadcast()` / `emit_task_update()` | Monkey-patches `WebSocketManager.broadcast` to append to in-memory queue |
| **`HealthEndpointClient`** | Helper to call enhanced `/health/degradation` endpoint and parse response | Thin wrapper around `httpx.AsyncClient` for test assertions |

### 2.2 Test Matrix (Integration Tests to Add)

| Test File | Scenario | Failure Injected | Expected Outcome |
|-----------|----------|------------------|------------------|
| `test_llm_circuit_breaker.py` | Provider fails 5× → circuit opens | `httpx` returns 500 / timeout | `ProviderCircuitBreaker.state == "open"`, fallback provider used |
| `test_llm_circuit_breaker.py` | Half-open success → circuit closes | First call fails, second succeeds | `state: closed`, `failure_count == 0` |
| `test_llm_failover.py` | Primary exhausted → fallback chain | All 3 fallback configs return 429 | `task_degraded` broadcast, task marked failed with `reason="rate_limited"` |
| `test_llm_retry_after.py` | Server returns `Retry-After: 2` | Mock response with header | Client waits ~2s + jitter before retry |
| `test_storage_fallback.py` | S3 unavailable at runtime | `boto3` `ClientError` on `put_object` | Falls back to `_LocalBackend`, file written locally |
| `test_vector_store_fallback.py` | ChromaDB HTTP timeout | `httpx.TimeoutException` on `query` | Switches to `PersistentClient`, query succeeds |
| `test_db_pool_exhaustion.py` | Pool checked_out == pool.size | Mock `engine.pool.checkedout()` | `system_resource_check` broadcasts `resource_warning` with DB pool metric |
| `test_health_monitor_alerts.py` | Stalled agent detected | Agent `last_heartbeat_at` > 2min ago | `system_alert` type `agent_health` with `stalled` list |

### 2.3 Health Endpoint Enhancements

**New Endpoint**: `GET /api/v1/health/degradation`

```json
{
  "circuit_breakers": {
    "openai": {"state": "closed", "failures": 0, "last_failure": null},
    "anthropic": {"state": "open", "failures": 5, "last_failure": "2026-10-30T14:23:00Z"},
    "google": {"state": "half_open", "failures": 3, "successes_in_half_open": 1}
  },
  "active_fallbacks": {
    "storage": "local",
    "vector_store": "persistent",
    "llm_provider": "anthropic"
  },
  "provider_health": {
    "openai": {"score": 1.0, "last_error": null},
    "anthropic": {"score": 0.0, "last_error": "rate_limited"},
    "google": {"score": 0.6, "last_error": "timeout"}
  },
  "system_alerts_recent": [
    {"type": "resource_warning", "timestamp": "...", "warnings": ["Memory at 85%"]}
  ]
}
```

**Enhanced Celery Task**: `run_health_check` now returns degradation summary alongside basic status.

---

## 3. Data Flow & Error Handling

### 3.1 Failure Injection → Observable Outcome Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐     ┌─────────────────────┐
│  Test Injects   │────▶│  Component Under │────▶│  Fallback / Circuit │────▶│  Assert Observable  │
│  Failure at Seam│     │  Test (e.g.      │     │  Breaker Activates │     │  (WebSocket, Health │
│  (HTTP, DB, S3) │     │   LLMClient)     │     │  (or exhausts)     │     │   Endpoint, Logs)   │
└─────────────────┘     └──────────────────┘     └────────────────────┘     └─────────────────────┘
```

**Key Seams (Injection Points)**:

| Seam | Injection Method | Restored By |
|------|------------------|-------------|
| `httpx.AsyncClient.request` | `FailureSimulator.patch_http()` | Context manager exit |
| `sqlalchemy.Engine.connect` | `FailureSimulator.patch_db()` | Context manager exit |
| `chromadb.HttpClient.__init__` | `FailureSimulator.patch_chroma()` | Context manager exit |
| `boto3.client('s3')` | `FailureSimulator.patch_s3()` | Context manager exit |

### 3.2 Error Handling Strategy per Domain

| Domain | Transient Errors (Retry) | Permanent Errors (Fallback) | Exhaustion (Degraded Broadcast) |
|--------|--------------------------|----------------------------|----------------------------------|
| **LLM** | 429, 5xx, timeout, network | 401/403 (invalid key), 400 (bad request) | All fallback configs exhausted → `task_degraded` |
| **Storage** | S3 timeout, 5xx | 403 (credentials), 404 (bucket) | S3 → Local (automatic, no broadcast) |
| **Vector Store** | HTTP timeout, 5xx | N/A (local always available) | HTTP → PersistentClient (automatic) |
| **Database** | Pool timeout, deadlock | N/A (single source of truth) | Health monitor `resource_warning` alert |

### 3.3 Circuit Breaker State Machine (Verification Points)

```
CLOSED (normal) ──5 failures──▶ OPEN (reject fast) ──30s timeout──▶ HALF_OPEN (probe)
     ▲                                                                    │
     │                                                                    ▼
     └────────────── 2 successes ──────────────────────────────────────▶ CLOSED
```

**Test Assertions per State**:
- **CLOSED**: `failure_count == 0`, requests pass through
- **OPEN**: `state == "open"`, calls raise `CircuitOpenError` immediately (no HTTP call)
- **HALF_OPEN**: `success_count_in_half_open` tracked, 2 successes → CLOSED, 1 failure → OPEN

### 3.4 WebSocket Event Contracts (for Capture & Assert)

```python
# task_degraded (from task_executor.py:379-384)
{
    "type": "task_degraded",
    "task_id": "uuid",
    "reason": "all_keys_invalid" | "rate_limited" | "provider_unreachable",
    "message": "The AI provider is temporarily unavailable..."
}

# system_alert (from health_monitor.py)
# Agent health
{"type": "system_alert", "alert_type": "agent_health", "stalled": [...], "crashed": [...], "recovered": [...], "timestamp": "..."}
# Resource warning
{"type": "system_alert", "type": "resource_warning", "warnings": ["CPU at 85%"], "metrics": {...}, "timestamp": "..."}
# Channel unhealthy
{"type": "system_alert", "type": "channel_unhealthy", "channels": [...], "timestamp": "..."}
# Anomaly detected
{"type": "system_alert", "type": "anomaly_detected", "anomalies": [...], "timestamp": "..."}
# Overflow review
{"type": "system_alert", "type": "overflow_review_needed", "queue_depth": 500, "timestamp": "..."}
```

---

## 4. Implementation Phasing & File Structure

### 4.1 Phased Implementation Plan

| Phase | Scope | Deliverables | Est. Effort |
|-------|-------|--------------|-------------|
| **Phase 1: Test Infrastructure** | `FailureSimulator`, `CircuitBreakerInspector`, `WebSocketEventCapture`, `HealthEndpointClient` | `tests/conftest.py` additions, `tests/utils/failure_simulator.py` | ~2 hrs |
| **Phase 2: LLM Resilience Tests** | Circuit breaker transitions, failover chain, `Retry-After` parsing, `task_degraded` broadcast | `tests/integration/test_llm_circuit_breaker.py`, `test_llm_failover.py`, `test_llm_retry_after.py`, `test_task_degraded_broadcast.py` | ~3 hrs |
| **Phase 3: Storage & Vector Store Tests** | S3→Local fallback, ChromaDB HTTP→PersistentClient fallback | `tests/integration/test_storage_fallback.py`, `test_vector_store_fallback.py` | ~2 hrs |
| **Phase 4: DB & Health Monitor Tests** | Pool exhaustion warning, agent health alerts, resource warnings, channel alerts, anomaly detection | `tests/integration/test_db_pool_exhaustion.py`, `test_health_monitor_alerts.py` | ~2 hrs |
| **Phase 5: Health Endpoint Enhancement** | `GET /api/v1/health/degradation` endpoint, enhanced `run_health_check` Celery task | `backend/api/routes/health.py` (new), update `backend/services/monitoring/health_checks.py` | ~2 hrs |
| **Phase 6: CI Integration & Documentation** | Add to pytest suite, GitHub Actions workflow, update TODO.md | `.github/workflows/resilience-tests.yml`, this design doc | ~1 hr |

**Total Estimated**: ~12 hours across 6 phases (Phases 2-4 independent, can parallelize)

### 4.2 New File Structure

```
backend/
├── api/routes/
│   └── health.py                 # NEW: /health/degradation endpoint
├── services/monitoring/
│   └── health_checks.py          # MODIFIED: enhanced run_health_check
tests/
├── conftest.py                   # MODIFIED: FailureSimulator, inspectors, capture fixtures
├── utils/
│   └── failure_simulator.py      # NEW: Failure injection context managers
├── integration/
│   ├── test_llm_circuit_breaker.py
│   ├── test_llm_failover.py
│   ├── test_llm_retry_after.py
│   ├── test_task_degraded_broadcast.py
│   ├── test_storage_fallback.py
│   ├── test_vector_store_fallback.py
│   ├── test_db_pool_exhaustion.py
│   └── test_health_monitor_alerts.py
```

### 4.3 Key Implementation Decisions

| Decision | Rationale |
|----------|-----------|
| **Separate `tests/utils/failure_simulator.py`** | Reusable across all integration tests; single source of truth for injection patterns |
| **Fixtures in `conftest.py`** | `failure_simulator`, `circuit_breaker_inspector`, `ws_capture` available to all tests without imports |
| **Health endpoint at `/api/v1/health/degradation`** | Follows existing `/api/v1/health` pattern; versioned for future evolution |
| **No changes to production circuit breaker logic** | Tests verify existing behavior; any bugs found become separate fix tickets |
| **WebSocket capture via monkey-patch** | Non-invasive; doesn't require modifying `WebSocketManager` or adding test-only code paths |

### 4.4 Success Criteria (Definition of Done)

- [ ] All 8 integration tests pass in CI against real dependencies (test DB, local ChromaDB, MinIO)
- [ ] `GET /api/v1/health/degradation` returns accurate circuit breaker states and active fallbacks
- [ ] `run_health_check` Celery task includes degradation summary in result
- [ ] `task_degraded` broadcast verified with correct payload for each exhaustion reason
- [ ] All `system_alert` event types from health monitor verified
- [ ] TODO.md item 21.5.1 marked complete with commit reference

---

## 5. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Test flakiness from timing (circuit breaker timeouts) | Medium | High | Use `asyncio.wait_for` with generous margins; mock time in unit tests |
| WebSocket capture misses events in async context | Low | Medium | Use `asyncio.ensure_future` pattern matching production code |
| Health endpoint exposes internal state | Low | Low | Read-only endpoint; no sensitive data; behind existing auth |
| CI failures from missing MinIO/ChromaDB | Medium | Medium | Use testcontainers or mock services in CI; document local requirements |

---

## 6. Future Extensions (Out of Scope)

- **Chaos Engineering Framework** (Approach B) — Runtime fault injection via feature flags for staging drills
- **Predictive Degradation** — Extend `predictive_health_api` to forecast circuit breaker openings
- **Automated Failover Testing** — Periodic CI job that kills dependencies and verifies recovery
- **Degradation Dashboards** — Grafana panels consuming `/health/degradation` for real-time ops visibility

---

*Design doc committed at: `docs/superpowers/specs/2026-10-30-graceful-degradation-design.md`*