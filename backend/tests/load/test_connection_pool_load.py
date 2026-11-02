"""
Load test for SQLAlchemy connection pool under concurrent requests (Phase 21.5.2).
Verifies pool (size=20, max_overflow=10) handles baseline burst (35 workers)
and 2x peak burst (60 concurrent workers = 2x total pool capacity) with memory stability.
"""
import concurrent.futures
import time
import statistics
import psutil
from backend.models.database import get_db_context, check_health, engine
from sqlalchemy import text


POOL_SIZE = 20
MAX_OVERFLOW = 10
TOTAL_CONNECTIONS = POOL_SIZE + MAX_OVERFLOW  # 30
CONCURRENT_REQUESTS = 35  # Exceeds pool capacity (baseline)
CONCURRENT_REQUESTS_2X = 60  # 2x total pool capacity
REQUESTS_PER_WORKER = 3


def _single_request(worker_id: int, request_num: int) -> dict:
    """Execute a single SELECT 1 via get_db_context()."""
    start = time.perf_counter()
    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000  # ms
        return {"worker": worker_id, "request": request_num, "latency_ms": latency, "success": True}
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return {"worker": worker_id, "request": request_num, "latency_ms": latency, "success": False, "error": str(e)}


def test_connection_pool_under_burst_load():
    """
    Spawn CONCURRENT_REQUESTS concurrent workers, each making REQUESTS_PER_WORKER requests.
    Total connections attempted = 35 * 3 = 105, but only 30 available (20 pool + 10 overflow).
    Workers should queue and succeed (pool_timeout=30s), not fail.
    """
    print(f"\nStarting pool load test: {CONCURRENT_REQUESTS} workers x {REQUESTS_PER_WORKER} requests")
    print(f"Pool capacity: {POOL_SIZE} + {MAX_OVERFLOW} overflow = {TOTAL_CONNECTIONS}")

    latencies = []
    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as executor:
        futures = [
            executor.submit(_single_request, worker_id, req_num)
            for worker_id in range(CONCURRENT_REQUESTS)
            for req_num in range(REQUESTS_PER_WORKER)
        ]

        for future in concurrent.futures.as_completed(futures, timeout=60):
            result = future.result()
            if result["success"]:
                latencies.append(result["latency_ms"])
            else:
                errors.append(result)

    # Assertions
    assert len(errors) == 0, f"Pool exhaustion errors: {errors[:5]}"
    assert len(latencies) == CONCURRENT_REQUESTS * REQUESTS_PER_WORKER

    # Latency stats
    avg_latency = statistics.mean(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    max_latency = max(latencies)

    print(f"Results: {len(latencies)} successful, {len(errors)} failed")
    print(f"Latency: avg={avg_latency:.2f}ms, p95={p95_latency:.2f}ms, max={max_latency:.2f}ms")

    # Sanity checks - pool_timeout is 30s
    assert avg_latency < 5000, "Average latency too high (possible pool contention)"
    assert p95_latency < 10000, "P95 latency too high"
    assert max_latency < 30000, "Max latency exceeds pool_timeout (30s)"


def test_connection_pool_under_2x_peak_burst():
    """
    Execute 2x peak burst testing (Phase 21.5.2):
    Spawn 60 concurrent workers (2x total capacity of 30), each making 3 requests (180 total).
    Verifies connection queuing, zero timeouts, return to baseline, and memory RSS stability.
    """
    process = psutil.Process()
    mem_before_mb = process.memory_info().rss / (1024 * 1024)
    baseline_checked_out = engine.pool.checkedout()

    print(f"\nStarting 2x peak pool load test: {CONCURRENT_REQUESTS_2X} workers x {REQUESTS_PER_WORKER} requests")
    print(f"Pool capacity: {TOTAL_CONNECTIONS} | Concurrency: {CONCURRENT_REQUESTS_2X} (2x pool saturation)")

    latencies = []
    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS_2X) as executor:
        futures = [
            executor.submit(_single_request, worker_id, req_num)
            for worker_id in range(CONCURRENT_REQUESTS_2X)
            for req_num in range(REQUESTS_PER_WORKER)
        ]

        for future in concurrent.futures.as_completed(futures, timeout=60):
            result = future.result()
            if result["success"]:
                latencies.append(result["latency_ms"])
            else:
                errors.append(result)

    # 1. Zero connection errors under 2x saturation
    assert len(errors) == 0, f"2x pool exhaustion errors: {errors[:5]}"
    assert len(latencies) == CONCURRENT_REQUESTS_2X * REQUESTS_PER_WORKER

    # 2. Connection return verification
    final_checked_out = engine.pool.checkedout()
    assert final_checked_out <= baseline_checked_out + 1, (
        f"Connections not returned: {final_checked_out} checked out (baseline: {baseline_checked_out})"
    )

    # 3. Latency bounds
    avg_latency = statistics.mean(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    max_latency = max(latencies)

    print(f"2x Results: {len(latencies)} successful, {len(errors)} failed")
    print(f"2x Latency: avg={avg_latency:.2f}ms, p95={p95_latency:.2f}ms, max={max_latency:.2f}ms")

    assert avg_latency < 5000, f"Average latency too high: {avg_latency:.2f}ms"
    assert p95_latency < 10000, f"P95 latency too high: {p95_latency:.2f}ms"
    assert max_latency < 30000, f"Max latency exceeded pool_timeout (30s): {max_latency:.2f}ms"

    # 4. Memory stability check: memory growth during burst must be under 50 MB
    mem_after_mb = process.memory_info().rss / (1024 * 1024)
    mem_diff_mb = mem_after_mb - mem_before_mb
    print(f"Memory RSS: before={mem_before_mb:.2f}MB, after={mem_after_mb:.2f}MB, diff={mem_diff_mb:.2f}MB")
    assert mem_diff_mb < 50.0, f"Memory growth during 2x burst exceeded 50MB: {mem_diff_mb:.2f}MB"


def test_check_health_under_load():
    """Verify check_health() works correctly under concurrent load."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_health) for _ in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        assert r["status"] == "healthy", f"Health check failed under load: {r}"
        assert r["database"] == "connected"
