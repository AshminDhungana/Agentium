# 2× Peak Load & Stress Testing — Design Spec

**Task**: 21.5.2 — Execute load testing at 2× expected peak request volume to verify connection pooling, memory stability, and system throughput.

**Date**: 2026-11-02
**Status**: Draft (awaiting user review)
**Related**: `docs/documents/TODO.md` line 1018

---

## 1. Architecture Overview

### 1.1 Goal
Verify system stability and performance at 2× expected peak load across all critical paths: API request handling, database connection pooling, Celery task throughput, WebSocket connection management, and LLM provider resilience.

### 1.2 System Boundaries & Current State

| Component | Current Capacity | 2× Target | Verification Gap |
|-----------|------------------|-----------|------------------|
| **API (FastAPI)** | ~500 RPS baseline | 1000 RPS sustained | No sustained load test at 2× |
| **DB Connection Pool** | QueuePool: size=20, overflow=10 | 30 concurrent connections | No burst/saturation test at pool limit |
| **Celery Workers** | 1000 tasks/hour baseline | 2000 tasks/hour | No throughput gate at 2× |
| **WebSocket** | Untested at scale | 500 concurrent | No WebSocket load test exists |
| **LLM Providers** | Mock provider for unit tests | Sustained mock traffic | No integration load test vs MockProviderServer |

### 1.3 Design Principle
**Measure, don't guess** — Establish baseline metrics first, then run 2× load with continuous system metric sampling (DB pool, Redis, Celery, process memory, ChromaDB). Produce a unified pass/fail report per component with CI-friendly quick mode (5 min, 75% of 2× = 1.5× baseline) and full mode (15 min, 100% of 2× = 2× baseline).

---

## 2. Components & Test Strategy

### 2.1 Load Testing Infrastructure Components

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| **`BaselineMeasurer`** | Establish pre-load baselines across 4 dimensions | Script running 3 warm-up iterations per dimension, outputs `baseline.json` |
| **`SystemSampler`** | Continuous metric collection during load test | Background async task sampling every 2s: DB pool checked_out/overflow, Redis memory/connected_clients, Celery queue depth/active tasks, process RSS/heap, ChromaDB query latency |
| **`WebSocketUser`** (Locust) | WebSocket connection load testing | New Locust `User` subclass maintaining persistent WS connections, simulating subscribe/publish patterns |
| **`MockProviderServer`** | LLM provider simulation for resilience testing | Existing in `locustfile.py` — FastAPI server mimicking OpenAI `/v1/chat/completions` with configurable latency/error injection |
| **`UnifiedReportGenerator`** | Per-component pass/fail + trend analysis | Aggregates Locust stats, SystemSampler time-series, baseline comparison → HTML + JSON report |
| **`LoadTestOrchestrator`** | CLI entry point for quick/full modes | `python -m backend.tests.load.orchestrator --mode quick\|full` |

### 2.2 Test Dimensions & 2× Targets

| Dimension | Baseline Metric | 2× Target (Full Mode) | Quick Mode (75% of 2× = 1.5× baseline) | Pass Criteria |
|-----------|-----------------|----------------------|----------------------------------------|---------------|
| **API RPS** | ~500 RPS | 1000 RPS sustained | 750 RPS | p95 < 500ms, error rate < 1%, no 5xx |
| **Concurrent Users** | 250 users | 500 concurrent | 375 concurrent | All Locust users spawn without timeout |
| **Task Throughput** | 1000 tasks/hr | 2000 tasks/hr | 1500 tasks/hr | Celery completes target within test window, queue drains |
| **WebSocket Connections** | N/A (new) | 500 concurrent | 375 concurrent | 99% connections stay alive, msg latency < 100ms |

### 2.3 Locust User Class Extensions

| User Class | Current | Extension for 2× Testing |
|------------|---------|--------------------------|
| `APIUser` | REST endpoints (chat, agents, tasks) | Weight increased; add sustained think_time=0 for max throughput |
| `WebSocketUser` | **NEW** | Persistent WS to `/ws`, subscribe to task updates, heartbeat every 30s |
| `TaskUser` | Celery task submission via API | Batch submit 10 tasks/user, verify completion via result backend |
| `ProviderUser` | MockProviderServer calls | Configurable error rate (0%, 1%, 5%) for resilience validation |

---

## 3. Data Flow & Error Handling

### 3.1 Load Test Execution Flow

```
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│  1. Baseline │───▶│  2. Provision   │───▶│  3. Ramp Load    │───▶│  4. Sustain &      │
│  Measurement │    │  Infra (Docker) │    │  (spawn-rate)    │    │  Sample Metrics    │
└──────────────┘    └─────────────────┘    └──────────────────┘    └────────────────────┘
                                                                       │
                                                                       ▼
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│  7. Report   │◀───│  6. Analyze &   │◀───│  5. Ramp Down &  │◀───│  Test Duration     │
│  & Gate      │    │  Compare        │    │  Cooldown        │    │  (5m quick / 15m   │
└──────────────┘    └─────────────────┘    └──────────────────┘    │  full)             │
                                                                     └────────────────────┘
```

### 3.2 SystemSampler Metric Collection

```python
# Sampled every 2 seconds during load test
metrics = {
    "db_pool": {
        "checked_out": int,      # from engine.pool.checkedout()
        "overflow": int,         # from engine.pool.overflow()
        "utilization_pct": float # checked_out / (pool_size + max_overflow)
    },
    "redis": {
        "used_memory_bytes": int,
        "connected_clients": int,
        "queue_depth": int       # Celery broker queue length
    },
    "celery": {
        "active_tasks": int,     # inspect().active()
        "reserved_tasks": int,   # inspect().reserved()
        "completed_per_min": int # rate from events
    },
    "process": {
        "rss_mb": float,         # psutil.Process().memory_info().rss
        "heap_mb": float,        # tracemalloc or equivalent
        "cpu_pct": float         # psutil.cpu_percent()
    },
    "chromadb": {
        "query_latency_p95_ms": float,  # from sampled queries
        "collection_count": int
    }
}
```

### 3.3 Error Handling Strategy

| Failure Mode | Detection | Response |
|--------------|-----------|----------|
| **DB Pool Exhaustion** | `utilization_pct > 95%` for >30s | Mark DB component FAIL; continue test |
| **Redis OOM / Disconnect** | `connected_clients` drop or memory > 90% | Mark Redis component FAIL; continue test |
| **Celery Queue Backup** | `queue_depth` growing > 2× target rate | Mark Celery component FAIL; continue test |
| **Process Memory Leak** | `rss_mb` growth > 50 MB/min sustained | Mark Memory component FAIL; continue test |
| **WebSocket Mass Disconnect** | >5% connections drop in 10s window | Mark WebSocket component FAIL; continue test |
| **MockProvider Errors** | HTTP 5xx rate > configured injection | Expected — validates resilience, not a test failure |

### 3.4 Pass/Fail Gate Logic

```python
# Per-component verdict
component_pass = (
    error_rate < 0.01 and
    p95_latency < threshold_ms and
    no_critical_metric_breach and
    baseline_comparison_within_tolerance  # e.g., latency < 1.5× baseline
)

# Overall gate
overall_pass = all(component_pass.values())
```

---

## 4. Testing Strategy

### 4.1 Test Modes

| Mode | Duration | Load Level | Use Case |
|------|----------|------------|----------|
| **Quick** | 5 minutes | 75% of 2× (1.5× baseline, e.g., 750 RPS) | CI gate, PR validation |
| **Full** | 15 minutes | 100% of 2× (2× baseline, e.g., 1000 RPS) | Pre-release, capacity planning |
| **Soak** | 60 minutes | 100% of 2× | Overnight stability (manual) |

### 4.2 Baseline Measurement Protocol

1. Start system (Docker Compose) with production-like settings
2. Warm-up: 60s at 10% load
3. Measure 3 × 60s windows at target baseline load
4. Compute median RPS, p95 latency, memory growth rate
5. Save `baseline.json` for comparison

### 4.3 Locust Test Scenarios

| Scenario | Users | Spawn Rate | Duration | Target |
|----------|-------|------------|----------|--------|
| **API Sustained** | 500 | 10/s | 5m/15m | 1000 RPS |
| **WebSocket Hold** | 500 | 5/s | 5m/15m | 500 concurrent |
| **Task Burst** | 50 | 5/s | 2m | 2000 tasks submitted |
| **Provider Resilience** | 100 | 5/s | 3m | 5% error injection |

### 4.4 CI Integration

```yaml
# .github/workflows/load-test.yml
- name: Run Quick Load Test
  run: |
    make load-test-quick
```

- Fails PR if any component FAILs
- Uploads `load_report.html` as artifact
- Posts summary comment with pass/fail per component

### 4.5 Reporting Artifacts

| Artifact | Format | Contents |
|----------|--------|----------|
| `load_report.html` | HTML | Locust charts, SystemSampler time-series, pass/fail badges |
| `load_report.json` | JSON | Machine-readable verdicts, metrics, baseline comparison |
| `baseline.json` | JSON | Baseline measurements for regression detection |

---

## 5. Implementation Phasing & File Structure

### 5.1 Phased Implementation Plan

| Phase | Scope | Deliverables | Est. Effort |
|-------|-------|--------------|-------------|
| **Phase 1: Baseline & Sampler** | `BaselineMeasurer`, `SystemSampler`, metric schemas | `backend/tests/load/baseline.py`, `backend/tests/load/sampler.py` | ~3 hrs |
| **Phase 2: WebSocketUser** | New Locust user class for WS load | `backend/tests/load/websocket_user.py`, integrated into `locustfile.py` | ~2 hrs |
| **Phase 3: Orchestrator & Modes** | CLI entry point, quick/full/soak modes | `backend/tests/load/orchestrator.py`, updated `Makefile` | ~2 hrs |
| **Phase 4: Unified Report** | Aggregation, HTML/JSON output, baseline comparison | `backend/tests/load/report.py`, `backend/tests/load/templates/report.html` | ~3 hrs |
| **Phase 5: CI Integration** | GitHub Actions workflow, PR gate, artifact upload | `.github/workflows/load-test.yml` | ~1 hr |
| **Phase 6: Documentation & TODO** | Update TODO.md, add runbook | `docs/documents/TODO.md`, `docs/runbooks/load-testing.md` | ~1 hr |

**Total Estimated**: ~12 hours across 6 phases (Phases 1-2 independent, can parallelize)

### 5.2 New File Structure

```
backend/
├── tests/load/
│   ├── __init__.py
│   ├── locustfile.py                 # MODIFIED: add WebSocketUser, ProviderUser weights
│   ├── baseline.py                   # NEW: BaselineMeasurer class
│   ├── sampler.py                    # NEW: SystemSampler async collector
│   ├── websocket_user.py             # NEW: WebSocketUser Locust class
│   ├── orchestrator.py               # NEW: CLI entry point (quick/full/soak)
│   ├── report.py                     # NEW: UnifiedReportGenerator
│   ├── templates/
│   │   └── report.html               # NEW: Jinja2 report template
│   ├── test_connection_pool_load.py  # EXISTING: keep for regression
│   ├── test_connection_pool_leak.py  # EXISTING: keep for regression
│   ├── test_celery_throughput.py     # EXISTING: keep for regression
│   └── PROVIDER_LOAD_REPORT.md       # EXISTING: reference
├── requirements-dev.txt              # MODIFIED: ensure locust>=2.29, pytest-benchmark
Makefile                              # MODIFIED: load-test target with QUICK flag
.github/workflows/
└── load-test.yml                     # NEW: CI workflow
```

### 5.3 Key Implementation Decisions

| Decision | Rationale |
|----------|-----------|
| **Separate `sampler.py`** | Decouples metric collection from Locust; runs in background thread, survives Locust master/worker topology |
| **`orchestrator.py` as CLI** | Single entry point for all modes; handles Docker Compose up/teardown, baseline, load, report |
| **Jinja2 HTML template** | Self-contained report viewable without Locust UI; embeds Chart.js for time-series |
| **Baseline stored as JSON** | Enables regression detection across runs; committed as artifact in CI |
| **Per-component pass/fail** | Allows partial success — e.g., API passes but WebSocket fails → actionable signal |
| **MockProviderServer reused** | Already in `locustfile.py`; extends with error injection API for resilience scenarios |

### 5.4 Makefile Target Updates

```make
# Quick mode (CI): 5 min, 75% of 2× (1.5× baseline)
load-test-quick:
	@python -m backend.tests.load.orchestrator --mode quick --gate

# Full mode (release): 15 min, 100% of 2× (2× baseline)
load-test-full:
	@python -m backend.tests.load.orchestrator --mode full --gate

# Soak mode (manual): 60 min, 100% of 2×
load-test-soak:
	@python -m backend.tests.load.orchestrator --mode soak

# Legacy direct Locust run (backward compat)
load-test-legacy:
	@cd backend/tests/load && \
	  locust \
	    --host $(STAGING_HOST) \
	    --users $(or $(LOCUST_USERS),1000) \
	    --spawn-rate $(or $(LOCUST_SPAWN_RATE),10) \
	    --run-time $(or $(LOCUST_RUN_TIME),5m) \
	    --headless \
	    --html locust_report.html

# Default alias
load-test: load-test-quick
```

### 5.5 Success Criteria (Definition of Done)

- [ ] Baseline measurement script runs and produces valid `baseline.json`
- [ ] `WebSocketUser` class sustains 500 concurrent connections for 15 minutes
- [ ] `SystemSampler` collects all 5 metric categories every 2s without gaps
- [ ] Quick mode (5 min) completes in CI and gates PR on component failures
- [ ] Full mode (15 min) achieves 1000 RPS API, 2000 tasks/hr, 500 WS with pass criteria
- [ ] Unified HTML report shows time-series charts, pass/fail badges, baseline comparison
- [ ] GitHub Actions workflow runs on PR, uploads artifacts, posts summary
- [ ] TODO.md item 21.5.2 marked complete with commit reference

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Test environment resource contention** | High | Medium | Use dedicated Docker Compose profile; limit CPU/memory in CI |
| **Flaky WebSocket connections** | Medium | High | Implement reconnect logic in `WebSocketUser`; tolerate 1% disconnect rate |
| **Baseline variance between runs** | Medium | Medium | Use median of 3 runs; set tolerance bands (±20% for latency, ±10% for RPS) |
| **CI timeout on full mode** | Low | High | Quick mode for CI (5 min); full mode only on release tags/manual |
| **MockProviderServer not representative** | Low | Medium | Validate mock latency/error profiles match real provider characteristics |
| **ChromaDB sampling adds overhead** | Low | Low | Sample 1 query per 10s per collection; negligible impact |

---

## 7. Future Extensions (Out of Scope)

- **Distributed Locust** — Multi-worker mode for >2000 users (requires Redis coordination)
- **Chaos Engineering Integration** — Inject network partition, CPU throttle during load
- **Autoscaling Validation** — Test K8s HPA triggers under simulated load
- **Cost Attribution** — Correlate load test metrics with provider API costs
- **Regression Dashboard** — Historical trend visualization across releases

---

*Design doc to be committed at: `docs/superpowers/specs/2026-11-02-2x-peak-load-stress-testing-design.md`*