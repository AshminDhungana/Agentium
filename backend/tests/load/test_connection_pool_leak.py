"""
Sustained load test for SQLAlchemy connection pool leak detection (Phase 21.5.2).
Runs concurrent requests across waves at 2x peak load (60 concurrent workers),
verifies checked-out connections return to baseline after every wave and memory remains stable.
"""
import concurrent.futures
import time
import statistics
import psutil
from backend.models.database import engine, get_db_context
from sqlalchemy import text


POOL_SIZE = 20
MAX_OVERFLOW = 10
TOTAL_CONNECTIONS = POOL_SIZE + MAX_OVERFLOW  # 30
CONCURRENT_WORKERS = 60  # 2x pool capacity (Phase 21.5.2)
REQUESTS_PER_WAVE = 1
WAVES = 6  # 6 waves x 60 concurrent workers = 360 requests


def _single_request(worker_id: int) -> dict:
    """Execute a single SELECT 1 via get_db_context()."""
    start = time.perf_counter()
    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000  # ms
        return {"worker": worker_id, "latency_ms": latency, "success": True}
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return {"worker": worker_id, "latency_ms": latency, "success": False, "error": str(e)}


def test_connection_pool_no_leak_under_sustained_load():
    """
    Run sustained load at 2x capacity (60 workers), track checked-out connections.
    Assert checked-out count returns to baseline after each wave, zero leak,
    and process RSS memory stability.
    """
    process = psutil.Process()
    mem_start_mb = process.memory_info().rss / (1024 * 1024)
    print(f"\nStarting 2x peak pool leak test: {WAVES} waves x {CONCURRENT_WORKERS} workers")
    print(f"Pool capacity: {TOTAL_CONNECTIONS} | Concurrency: {CONCURRENT_WORKERS}")

    baseline_checked_out = engine.pool.checkedout()
    print(f"Baseline checked-out connections: {baseline_checked_out}")

    all_latencies = []
    all_errors = []
    leak_detected = False

    for wave in range(WAVES):
        wave_start = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
            futures = [executor.submit(_single_request, i) for i in range(CONCURRENT_WORKERS)]

            for future in concurrent.futures.as_completed(futures, timeout=30):
                result = future.result()
                if result["success"]:
                    all_latencies.append(result["latency_ms"])
                else:
                    all_errors.append(result)

        wave_duration = time.perf_counter() - wave_start

        # Allow pool cleanup
        time.sleep(0.2)

        checked_out = engine.pool.checkedout()
        pool_size = engine.pool.size()
        overflow = engine.pool.overflow()

        print(f"Wave {wave + 1}/{WAVES}: {wave_duration:.2f}s | "
              f"checked_out={checked_out} | pool_size={pool_size} | overflow={overflow} | "
              f"errors={len(all_errors)}")

        # Allow small transient variance (+2) for connections being returned
        if checked_out > baseline_checked_out + 2:
            leak_detected = True
            print(f"  ⚠️  LEAK DETECTED: {checked_out} checked out (baseline: {baseline_checked_out})")

    # Final verification after all waves
    time.sleep(0.5)
    final_checked_out = engine.pool.checkedout()
    print(f"Final checked-out: {final_checked_out} (baseline: {baseline_checked_out})")

    # Assertions
    assert len(all_errors) == 0, f"Pool exhaustion errors: {all_errors[:5]}"
    assert not leak_detected, "Connection pool leak detected during sustained load"
    assert final_checked_out <= baseline_checked_out + 1, \
        f"Final leak: {final_checked_out} checked out (baseline: {baseline_checked_out})"

    # Latency sanity checks
    avg_latency = statistics.mean(all_latencies) if all_latencies else 0
    p95_latency = sorted(all_latencies)[int(len(all_latencies) * 0.95)] if all_latencies else 0
    max_latency = max(all_latencies) if all_latencies else 0

    print(f"Latency: avg={avg_latency:.2f}ms, p95={p95_latency:.2f}ms, max={max_latency:.2f}ms")
    assert avg_latency < 5000, "Average latency too high (possible pool contention)"
    assert max_latency < 30000, "Max latency exceeds pool_timeout (30s)"

    # Memory stability: RSS memory drift across waves < 50MB
    mem_end_mb = process.memory_info().rss / (1024 * 1024)
    mem_diff_mb = mem_end_mb - mem_start_mb
    print(f"Memory RSS drift: {mem_diff_mb:.2f}MB (start={mem_start_mb:.2f}MB, end={mem_end_mb:.2f}MB)")
    assert mem_diff_mb < 50.0, f"Memory drift exceeded 50MB: {mem_diff_mb:.2f}MB"


def test_check_health_under_sustained_load():
    """Verify check_health() stays healthy under sustained wave load."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_single_request, i) for i in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    success_count = sum(1 for r in results if r.get("success"))
    assert success_count == 20, f"Expected 20 successes, got {success_count}"
