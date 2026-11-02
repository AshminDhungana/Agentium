# 2× Peak Load & Stress Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute and verify 2× peak load and stress testing for Agentium across API request handling (1,000 RPS), database connection pooling (60 concurrent workers / 2× saturation), Celery task throughput ($\ge 2,000$ tasks/hr), WebSocket connection concurrency (500 persistent sessions), process memory stability ($< 50$ MB/min growth), and LLM provider resilience.

**Architecture:** Build a modular load-testing suite combining continuous system metric sampling (`SystemSampler`), baseline measurement (`BaselineMeasurer`), high-concurrency WebSocket user (`WebSocketUser`), CLI orchestration with quick/full/soak modes (`LoadTestOrchestrator`), and unified HTML/JSON report generation (`UnifiedReportGenerator`). Fix known bugs in existing Celery throughput and pool burst test suites.

**Tech Stack:** Python 3.13, Locust, pytest, SQLAlchemy, Celery, Redis, websockets / httpx, psutil, Jinja2, Chart.js

---

## Global Constraints & Discrepancy Fixes

- **WebSocket Route**: Must target `/ws/chat` (mounted under `/ws` prefix in `backend/main.py` pointing to `websocket.py::websocket_chat_endpoint`). Requires initial auth message `{"type": "auth", "token": "<JWT>"}` followed by ping/pong heartbeat messages `{"type": "ping", "timestamp": ...}`.
- **Celery Eager Execution Bug**: Modern Celery's `celery_app.send_task(...)` ignores `task_always_eager=True` and attempts network broker connection. In tests and eager mode, tasks must use `.apply_async()` with a registered no-op task (`agentium.tasks.noop_perf_task`) and `cache+memory://` result backend to avoid Redis connection timeouts.
- **DB Connection Pool 2× Saturation**: Standard pool is 20 + 10 overflow = 30 connections. 2× peak burst testing must test 60 concurrent workers ($2 \times$ capacity) to verify queueing within `pool_timeout=30s` without starvation or handle leaks.
- **No-Cov Standalone Runs**: Load and stress test commands in dev / CI must pass `--no-cov` to prevent pytest coverage gates (`--cov-fail-under=20`) from failing pure load suites.
- **Artifacts & Reports**: Generate self-contained HTML + JSON reports at `backend/tests/load/load_report.html` and `backend/tests/load/load_report.json`.

---

## File Structure Map

```
backend/
├── tests/load/
│   ├── __init__.py
│   ├── conftest.py                   # MODIFIED: ensure Celery eager memory backend & task registration
│   ├── test_celery_throughput.py     # MODIFIED: fix eager execution, update gate to 2,000 tasks/hr
│   ├── test_connection_pool_load.py  # MODIFIED: add 2x peak burst test (60 workers) & memory tracking
│   ├── test_connection_pool_leak.py  # MODIFIED: expand to 2x concurrent wave stress (60 workers)
│   ├── baseline.py                   # NEW: BaselineMeasurer class for pre-load baseline capture
│   ├── sampler.py                    # NEW: SystemSampler async metric collection (pool, redis, celery, memory)
│   ├── websocket_user.py             # NEW: WebSocketUser Locust user class with heartbeat & message loop
│   ├── locustfile.py                 # MODIFIED: import WebSocketUser, tune user weights for 2x load
│   ├── orchestrator.py               # NEW: CLI orchestrator (--mode quick|full|soak, --gate)
│   ├── report.py                     # NEW: UnifiedReportGenerator aggregating Locust & sampler data
│   └── templates/
│       └── report.html               # NEW: Jinja2 HTML report template with Chart.js visualization
├── requirements-dev.txt              # MODIFIED: ensure jinja2, psutil, websockets pinned
Makefile                              # MODIFIED: add load-test-quick, load-test-full, load-test-soak
.github/workflows/
└── load-test.yml                     # NEW: GitHub Actions workflow for PR performance regression gating
docs/
├── runbooks/
│   └── load-testing.md               # NEW: Operational runbook for executing & triaging load tests
└── documents/
    └── TODO.md                       # MODIFIED: mark 21.5.2 COMPLETED with commit hash & test metrics
```

---

## Phase 1: Fix Existing Test Suites & Implement 2× Pool Saturation

### Task 1.1: Fix Celery Throughput Benchmark & Update Gate to 2,000 Tasks/hr

**Files:**
- Modify: `backend/tests/load/conftest.py`
- Modify: `backend/tests/load/test_celery_throughput.py`
- Modify: `backend/services/tasks/task_executor.py`

**Key Actions:**
1. Register a dedicated performance test task `agentium.tasks.noop_perf_task` in `backend/services/tasks/task_executor.py` that accepts arbitrary kwargs without signature conflict.
2. In `backend/tests/load/conftest.py`, ensure `celery_app.conf.update(task_always_eager=True, broker_url="memory://", result_backend="cache+memory://")` properly initializes eager state and registers the no-op task.
3. In `backend/tests/load/test_celery_throughput.py`, check if `task_always_eager` is set; if so, invoke `task.apply_async(...)` instead of `send_task` to prevent Celery bypass and Redis connection failures.
4. Raise `_MIN_THROUGHPUT_PER_HOUR` from 1,000 to **2,000** tasks/hour (2× expected peak throughput).
5. Run `pytest backend/tests/load/test_celery_throughput.py --no-cov -v` and verify green status in $< 2$ seconds.

---

### Task 1.2: Upgrade DB Connection Pool Load & Leak Tests to 2× Peak (60 Workers)

**Files:**
- Modify: `backend/tests/load/test_connection_pool_load.py`
- Modify: `backend/tests/load/test_connection_pool_leak.py`

**Key Actions:**
1. In `test_connection_pool_load.py`:
   - Add `test_connection_pool_under_2x_peak_burst()`:
     - Total capacity = 30 (20 pool + 10 overflow).
     - Test concurrency = **60 concurrent workers** ($2 \times$ total pool capacity), 3 requests each = 180 total queries.
     - Verify zero connection timeouts, zero `TimeoutError`, all queries succeed within `pool_timeout=30s`.
     - Verify memory RSS before and after burst shows no unbounded expansion.
2. In `test_connection_pool_leak.py`:
   - Update `CONCURRENT_WORKERS = 60` (2× pool capacity).
   - Verify `checked_out` returns to baseline ($\le \text{baseline} + 1$) after each wave and at completion.
   - Assert average query latency $< 5000\text{ms}$ and maximum latency $< 30000\text{ms}$.
3. Run `pytest backend/tests/load/test_connection_pool_load.py backend/tests/load/test_connection_pool_leak.py --no-cov -v` to ensure 100% pass rate.

---

## Phase 2: System Metric Sampling & Baseline Measurement

### Task 2.1: Implement `SystemSampler` (`backend/tests/load/sampler.py`)

**Files:**
- Create: `backend/tests/load/sampler.py`
- Create: `backend/tests/unit/test_sampler.py`

**Key Actions:**
1. Build `SystemSampler` class with background async collection loop sampling every `interval_sec=2.0`.
2. Collect 5 metric categories:
   - **DB Pool**: `engine.pool.checkedout()`, `engine.pool.overflow()`, `engine.pool.size()`, pool utilization percentage.
   - **Process Memory & CPU**: `psutil.Process().memory_info().rss / (1024*1024)` (MB), `psutil.Process().cpu_percent()`.
   - **Redis**: client connection count and memory usage (graceful fallback if Redis offline).
   - **Celery**: active/reserved task inspect counts (graceful fallback if workers offline).
   - **ChromaDB**: collection query ping latency.
3. Provide summary methods: `get_summary()`, `get_time_series()`, `detect_memory_leak(max_mb_per_min=50.0)`.
4. Unit tests in `backend/tests/unit/test_sampler.py` verifying start, stop, sample capture, and serialization.

---

### Task 2.2: Implement `BaselineMeasurer` (`backend/tests/load/baseline.py`)

**Files:**
- Create: `backend/tests/load/baseline.py`
- Create: `backend/tests/unit/test_baseline.py`

**Key Actions:**
1. Build `BaselineMeasurer` class to measure pre-load baseline across:
   - Base API response latency (p50, p95).
   - DB single-query latency.
   - Process baseline RSS (MB).
   - Task completion latency.
2. Runs 60s warm-up followed by 3 measurement iterations, computes median values, and saves to `baseline.json`.
3. Unit tests verifying baseline computation, JSON export, and schema compliance.

---

## Phase 3: WebSocket 2× Load Testing

### Task 3.1: Implement `WebSocketUser` (`backend/tests/load/websocket_user.py`)

**Files:**
- Create: `backend/tests/load/websocket_user.py`
- Modify: `backend/tests/load/locustfile.py`

**Key Actions:**
1. Create `WebSocketUser(User)` leveraging `websockets` async client or threaded WebSocket client.
2. Connect to endpoint `/ws/chat`.
3. Perform handshake:
   - Send `{"type": "auth", "token": "<JWT>"}`.
   - Await welcome response `{"type": "system", ...}`.
4. Periodic heartbeat:
   - Send `{"type": "ping", "timestamp": ...}` every 30 seconds.
   - Record response latency for `{"type": "pong"}` into Locust request metrics.
5. Interactive chat simulation:
   - Periodically send `{"type": "chat_message", "content": "..."}`.
   - Track time to first token and stream completion.
6. Handle reconnection gracefully with backoff; assert $\le 1\%$ dropped connections under 500 concurrent connections.
7. Integrate `WebSocketUser` into `backend/tests/load/locustfile.py`.

---

## Phase 4: Unified Report Generator & HTML Templates

### Task 4.1: Implement `UnifiedReportGenerator` (`backend/tests/load/report.py`)

**Files:**
- Create: `backend/tests/load/report.py`
- Create: `backend/tests/load/templates/report.html`
- Create: `backend/tests/unit/test_load_report.py`

**Key Actions:**
1. Create `UnifiedReportGenerator` that consumes:
   - Locust execution statistics (`StatsEntry` / JSON exports).
   - `SystemSampler` time-series data.
   - Baseline measurements (`baseline.json`).
2. Implement pass/fail component gate logic:
   - **API RPS**: $\ge 1,000$ RPS (quick: 750), p95 $< 500\text{ms}$, error rate $< 1\%$.
   - **DB Pool**: 0 pool exhaustion errors, utilization $< 95\%$, final checked-out equals baseline.
   - **Celery Tasks**: $\ge 2,000$ tasks/hr (quick: 1500), queue drains.
   - **WebSocket**: 500 concurrent (quick: 375), $\ge 99\%$ connection retention, ping latency $< 100\text{ms}$.
   - **Memory Stability**: RSS growth rate $< 50$ MB/min, no monotonic memory leak.
3. Render self-contained Jinja2 HTML report `load_report.html` with interactive Chart.js line graphs for memory RSS, pool utilization, and request latency.
4. Export machine-readable `load_report.json` with overall and per-component boolean verdicts.

---

## Phase 5: CLI Load Test Orchestrator

### Task 5.1: Implement `LoadTestOrchestrator` (`backend/tests/load/orchestrator.py`)

**Files:**
- Create: `backend/tests/load/orchestrator.py`
- Modify: `Makefile`

**Key Actions:**
1. CLI entry point: `python -m backend.tests.load.orchestrator --mode quick|full|soak [--gate] [--output-dir DIR]`:
   - `--mode quick`: 5 minutes duration, 75% load (750 RPS, 375 WS users, 1500 tasks/hr). Ideal for CI.
   - `--mode full`: 15 minutes duration, 100% of 2× peak (1,000 RPS, 500 WS users, 2000 tasks/hr).
   - `--mode soak`: 60 minutes duration, 100% of 2× peak.
   - `--gate`: Exits with code 1 if any component fails criteria.
2. Coordinates execution:
   - Step 1: Initialize `SystemSampler` and `MockProviderServer`.
   - Step 2: Establish baseline if `baseline.json` absent.
   - Step 3: Run Locust in headless mode with specified user count and duration.
   - Step 4: Stop sampler and collect time-series.
   - Step 5: Generate unified HTML and JSON reports.
   - Step 6: Print terminal summary table with pass/fail badges.
3. Add Makefile targets:
   - `load-test-quick`: runs `--mode quick --gate`
   - `load-test-full`: runs `--mode full --gate`
   - `load-test-soak`: runs `--mode soak`
   - Alias `load-test` to `load-test-quick`.

---

## Phase 6: CI Integration & Runbook

### Task 6.1: CI Workflow & Load Test Gate

**Files:**
- Create: `.github/workflows/load-test.yml`

**Key Actions:**
1. Configure GitHub Actions workflow running on pull requests targeting `main` and manual `workflow_dispatch`.
2. Steps:
   - Set up Python 3.13 and dependencies.
   - Run unit and load pool tests: `pytest backend/tests/load/test_connection_pool_load.py backend/tests/load/test_celery_throughput.py --no-cov`.
   - Run quick load test: `python -m backend.tests.load.orchestrator --mode quick --gate`.
   - Upload `load_report.html` and `load_report.json` as GitHub Actions artifacts.
   - Post PR summary comment with component pass/fail breakdown.

---

### Task 6.2: Operational Runbook & Documentation

**Files:**
- Create: `docs/runbooks/load-testing.md`
- Modify: `docs/documents/TODO.md`

**Key Actions:**
1. Write comprehensive runbook in `docs/runbooks/load-testing.md`:
   - Pre-requisites, command invocations for quick/full/soak modes.
   - Metric interpretation guide (pool utilization, p95 latency, worker stability).
   - Troubleshooting guides for common failures: DB pool timeout, Redis memory pressure, Celery backlog, process memory leaks.
2. Update `docs/documents/TODO.md` line 1018:
   - Mark `21.5.2` as **COMPLETED**.
   - Include test metrics: 1,000 RPS sustained API target, 60-worker 2× DB pool burst verified, $\ge 2,000$ tasks/hr Celery throughput verified, 500-session WebSocket stability verified, memory drift $< 50$ MB/min verified.

---

## Verification & Execution Order

1. **Verify Celery Throughput Fix**:
   `pytest backend/tests/load/test_celery_throughput.py --no-cov -v` (passes $\ge 2,000$ tasks/hr).
2. **Verify 2× DB Pool Saturation**:
   `pytest backend/tests/load/test_connection_pool_load.py backend/tests/load/test_connection_pool_leak.py --no-cov -v` (passes 60 concurrent workers).
3. **Verify Sampler & Baseline Unit Tests**:
   `pytest backend/tests/unit/test_sampler.py backend/tests/unit/test_baseline.py backend/tests/unit/test_load_report.py --no-cov -v`.
4. **Verify Orchestrator Dry-Run / Quick Mode**:
   `python -m backend.tests.load.orchestrator --mode quick --gate`.
5. **Verify Report Generation**:
   Inspect generated `load_report.html` and `load_report.json`.
6. **Mark Task Complete in TODO.md**.

