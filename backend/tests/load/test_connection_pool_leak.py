"""
Sustained load test for SQLAlchemy connection pool leak detection.
Runs 60 seconds of concurrent requests, verifies checked-out connections return to baseline.
"""
import concurrent.futures
import time
import statistics
from backend.models.database import engine, get_db_context
from sqlalchemy import text


POOL_SIZE = 20
MAX_OVERFLOW = 10
TOTAL_CONNECTIONS = POOL_SIZE + MAX_OVERFLOW  # 30
CONCURRENT_WORKERS = 30
REQUESTS_PER_WAVE = 1
WAVES = 12  # 12 waves x ~5 sec = ~60 seconds
WAVE_INTERVAL = 5  # seconds between waves


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
    Run sustained load for 60 seconds, track checked-out connections.
    Assert checked-out count returns to baseline after each wave.
    """
    print(f"\nStarting pool leak test: {WAVES} waves x {CONCURRENT_WORKERS} workers")
    print(f"Pool capacity: {POOL_SIZE} + {MAX_OVERFLOW} overflow = {TOTAL_CONNECTIONS}")
    
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
        time.sleep(0.5)
        
        checked_out = engine.pool.checkedout()
        pool_size = engine.pool.size()
        overflow = engine.pool.overflow()
        
        print(f"Wave {wave + 1}/{WAVES}: {wave_duration:.1f}s | "
              f"checked_out={checked_out} | pool_size={pool_size} | overflow={overflow} | "
              f"errors={len([e for e in all_errors if e.get('worker') >= wave*CONCURRENT_WORKERS])}")
        
        # Allow small variance (+2) for connections being returned
        if checked_out > baseline_checked_out + 2:
            leak_detected = True
            print(f"  ⚠️  LEAK DETECTED: {checked_out} checked out (baseline: {baseline_checked_out})")
    
    # Final verification after all waves
    time.sleep(1)
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


def test_check_health_under_sustained_load():
    """Verify check_health() works correctly under concurrent load."""
    from backend.models.database import check_health
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_health) for _ in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        assert r["status"] == "healthy", f"Health check failed under load: {r}"
        assert r["database"] == "connected"