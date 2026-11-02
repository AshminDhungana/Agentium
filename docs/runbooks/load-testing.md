# Operational Runbook: 2× Peak Load & Stress Testing

**Platform Task**: 21.5.2 — Execute load testing at 2× expected peak request volume to verify connection pooling, memory stability, and system throughput.  
**Version**: 1.0  
**Updated**: 2026-11-02  

---

## 1. Overview & Capacity Targets

This runbook describes how to execute, interpret, and troubleshoot 2× peak load and stress tests against Agentium.

### 1.1 Target Criteria (2× Expected Peak)

| Dimension | Baseline | 2× Target (Full Mode) | Quick Mode (CI / 1.5×) | Pass Criteria |
|-----------|----------|----------------------|------------------------|---------------|
| **API Throughput** | ~500 RPS | **1,000 RPS** sustained | 750 RPS | p95 $< 500$ms, error rate $< 1\%$, zero 5xx |
| **DB Connection Pool** | 30 conn (20+10) | **60 concurrent workers** | 45 concurrent workers | 0 timeouts, pool utilization $< 95\%$, return to baseline |
| **Celery Throughput** | 1,000 tasks/hr | **$\ge 2,000$ tasks/hr** | 1,500 tasks/hr | Queue drains, completion within timeout |
| **WebSocket Concurrency**| N/A | **500 persistent sessions** | 375 persistent sessions| $\ge 99\%$ connections retained, ping $< 100$ms |
| **Process Memory** | Baseline RSS | **$< 50$ MB/min growth** | $< 50$ MB/min growth | Zero unbounded memory leaks |

---

## 2. Test Execution Commands

### 2.1 Quick Mode (CI / PR Gate)
Runs a 5-minute test profile at 1.5× baseline (750 RPS, 375 WS users).
```bash
make load-test-quick
# or directly:
python -m backend.tests.load.orchestrator --mode quick --gate
```

### 2.2 Full Mode (Release / Pre-Deployment Gate)
Runs a 15-minute test profile at 100% of 2× peak target (1,000 RPS sustained, 500 WS users, 2,000 tasks/hr).
```bash
make load-test-full
# or directly:
python -m backend.tests.load.orchestrator --mode full --gate
```

### 2.3 Soak Mode (Overnight / Long-Running Stability)
Runs a 60-minute sustained stability test to detect slow memory leaks and thread exhaustion.
```bash
make load-test-soak
# or directly:
python -m backend.tests.load.orchestrator --mode soak
```

### 2.4 Targeted Component Verification Suites
To test individual components under load without running the full Locust cluster:

```bash
# 1. Database Connection Pool (Burst saturation & sustained leak test)
pytest backend/tests/load/test_connection_pool_load.py \
       backend/tests/load/test_connection_pool_leak.py --no-cov -v

# 2. Celery Task Throughput Gate
pytest backend/tests/load/test_celery_throughput.py --no-cov -v

# 3. System Telemetry & WebSocket User Tests
pytest backend/tests/unit/test_sampler.py \
       backend/tests/unit/test_baseline.py \
       backend/tests/unit/test_websocket_user.py \
       backend/tests/unit/test_load_report.py --no-cov -v
```

---

## 3. Reporting & Artifacts

Every test run outputs three consolidated artifacts in `backend/tests/load/`:

1. **`load_report.html`**: Interactive HTML report featuring:
   - Overall status banner (`PASS` or `FAIL`)
   - Component gate scorecard (API, DB Pool, Celery, WebSocket, Memory)
   - Real-time Chart.js time-series plots for Process RSS memory and DB pool utilization
2. **`load_report.json`**: Machine-readable JSON summary containing raw metrics, threshold comparisons, and boolean verdicts.
3. **`baseline.json`**: Reference baseline measurements used for regression comparison.

---

## 4. Triage & Troubleshooting Guide

### 4.1 Failure: DB Pool Exhaustion / Timeout
**Symptoms**:
- `QueuePool limit of size 20 overflow 10 reached, connection timed out, timeout 30.00`
- API responses returning 500 or hanging.

**Diagnosis**:
1. Check `load_report.html` for DB Pool Peak Utilization. If $\ge 95\%$, connections are being checked out longer than expected.
2. Inspect unclosed sessions or long transactions:
   ```bash
   SELECT pid, age(clock_timestamp(), query_start), query FROM pg_stat_activity WHERE state != 'idle';
   ```
3. Verify that `get_db_context()` or FastAPI `get_db()` dependencies consistently commit/rollback and close connections in `finally` blocks.

**Remediation**:
- Tune pool size in `.env` / `backend/core/config.py`:
  ```ini
  DATABASE_POOL_SIZE=30
  DATABASE_MAX_OVERFLOW=20
  DATABASE_POOL_TIMEOUT=30
  ```

---

### 4.2 Failure: Process Memory Growth / Leak
**Symptoms**:
- `SystemSampler` flags `memory_leak_detected = True`
- Growth rate exceeds $50.0$ MB/min.

**Diagnosis**:
1. Inspect the RSS time-series chart in `load_report.html`. A saw-tooth pattern with flat valleys indicates normal GC; a strictly monotonic upward slope indicates an uncollected reference leak.
2. Profile heap with `tracemalloc`:
   ```python
   import tracemalloc
   tracemalloc.start()
   # take snapshots before and after 100 requests
   ```
3. Check for unbounded module-level caches or WebSocket stream listeners that were not un-registered on disconnect.

---

### 4.3 Failure: Celery Task Backlog
**Symptoms**:
- Celery throughput falls below $2,000$ tasks/hr.
- Redis broker queue depth (`llen celery`) steadily increases.

**Diagnosis**:
1. Verify Celery worker concurrency:
   ```bash
   docker compose exec backend celery -A backend.celery_app inspect active_queues
   ```
2. Verify Redis broker memory and network latency:
   ```bash
   docker compose exec redis redis-cli info memory
   ```

**Remediation**:
- Increase worker concurrency or scale worker container replicas:
  ```bash
  celery -A backend.celery_app worker -c 8 --prefetch-multiplier=1
  ```

---

### 4.4 Failure: WebSocket Mass Disconnects
**Symptoms**:
- Drop rate exceeds $1\%$.
- Locust logs `ws:heartbeat_ping` timeouts.

**Diagnosis**:
1. Check event loop latency in `backend/api/routes/websocket.py`. Long-running synchronous CPU operations inside async route handlers freeze the event loop.
2. Verify Redis Pub/Sub buffer capacity for broadcast channels (`agentium:ws:buffer`).

---

## 5. Escalation Contacts

- **Platform Lead**: Lead Architect / On-Call Engineer
- **Database Administrator**: Database Infrastructure Team
- **Incident Channel**: `#incident-response`

