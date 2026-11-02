"""SystemSampler - Continuous metric sampling during load and stress tests (Phase 21.5.2).

Samples DB pool utilization, process RSS/CPU, Redis memory/clients, Celery tasks,
and ChromaDB latency at fixed intervals (default 2s) to detect memory leaks,
connection starvation, and saturation during load tests.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import psutil

try:
    from backend.models.database import engine
except Exception:  # pragma: no cover
    engine = None

logger = logging.getLogger(__name__)


class SystemSampler:
    """Collects real-time system metrics in a background daemon thread."""

    def __init__(self, interval_sec: float = 2.0, target_pid: Optional[int] = None):
        self.interval_sec = interval_sec
        self.target_pid = target_pid or psutil.Process().pid
        self._process = psutil.Process(self.target_pid)
        self._samples: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None

        # Reachability caching to prevent connection timeouts from delaying sampling
        self._redis_checked = False
        self._redis_available = False
        self._last_redis_check = 0.0

    def _check_redis_reachability(self) -> bool:
        """Non-blocking socket check (<=20ms) to verify if Redis is listening."""
        now = time.time()
        if self._redis_checked and (now - self._last_redis_check) < 30.0:
            return self._redis_available

        self._last_redis_check = now
        self._redis_checked = True
        try:
            from backend.core.config import settings
            parsed = urlparse(settings.REDIS_URL)
            host = parsed.hostname or "localhost"
            port = parsed.port or 6379

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.02)
            result = sock.connect_ex((host, port))
            sock.close()
            self._redis_available = (result == 0)
        except Exception:
            self._redis_available = False
        return self._redis_available

    def start(self) -> None:
        """Start background sampling."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._samples.clear()
        self._start_time = time.time()
        self._end_time = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="SystemSamplerThread")
        self._thread.start()
        logger.info("SystemSampler started with %ss sampling interval", self.interval_sec)

    def stop(self) -> None:
        """Stop background sampling and wait for thread to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_sec * 3)
            self._thread = None
        self._end_time = time.time()
        logger.info("SystemSampler stopped. Total samples collected: %d", len(self._samples))

    def _run_loop(self) -> None:
        """Worker loop sampling at interval_sec."""
        while not self._stop_event.is_set():
            sample = self.sample_once()
            with self._lock:
                self._samples.append(sample)
            self._stop_event.wait(self.interval_sec)

    def sample_once(self) -> Dict[str, Any]:
        """Perform a single metric sample across all dimensions without blocking."""
        now = time.time()
        elapsed = now - (self._start_time or now)

        # 1. Process Metrics (<1ms)
        try:
            mem_info = self._process.memory_info()
            rss_mb = round(mem_info.rss / (1024 * 1024), 2)
            cpu_pct = round(self._process.cpu_percent(), 2)
        except Exception as e:
            logger.debug("Failed to read process stats: %s", e)
            rss_mb = 0.0
            cpu_pct = 0.0

        # 2. Database Connection Pool Metrics (<1ms)
        pool_metrics = {"checked_out": 0, "overflow": 0, "size": 0, "utilization_pct": 0.0}
        if engine is not None and hasattr(engine, "pool"):
            try:
                checked_out = getattr(engine.pool, "checkedout", lambda: 0)()
                overflow = getattr(engine.pool, "overflow", lambda: 0)()
                size = getattr(engine.pool, "size", lambda: 0)()
                total_cap = 30  # Default 20 pool + 10 overflow
                utilization = min(100.0, round(((checked_out + max(0, overflow)) / max(1, total_cap)) * 100.0, 1))
                pool_metrics = {
                    "checked_out": checked_out,
                    "overflow": overflow,
                    "size": size,
                    "utilization_pct": utilization,
                }
            except Exception as e:
                logger.debug("Failed to read DB pool metrics: %s", e)

        # 3. Redis Metrics (Skipped if Redis offline to prevent timeout)
        redis_metrics = {"connected_clients": 0, "used_memory_bytes": 0, "queue_depth": 0}
        if self._check_redis_reachability():
            try:
                from backend.core.config import settings
                import redis
                from redis.retry import Retry
                from redis.backoff import NoBackoff
                r = redis.from_url(
                    settings.REDIS_URL,
                    socket_connect_timeout=0.05,
                    socket_timeout=0.05,
                    retry=Retry(NoBackoff(), 0),
                )
                info = r.info()
                redis_metrics = {
                    "connected_clients": int(info.get("connected_clients", 0)),
                    "used_memory_bytes": int(info.get("used_memory", 0)),
                    "queue_depth": int(r.llen("celery") or 0),
                }
            except Exception:
                pass

        # 4. Celery Metrics (Skipped if eager or Redis offline)
        celery_metrics = {"active_tasks": 0, "reserved_tasks": 0}
        if self._redis_available:
            try:
                from backend.celery_app import celery_app
                if not celery_app.conf.task_always_eager:
                    insp = celery_app.control.inspect(timeout=0.05)
                    if insp:
                        active = insp.active() or {}
                        reserved = insp.reserved() or {}
                        celery_metrics["active_tasks"] = sum(len(v) for v in active.values())
                        celery_metrics["reserved_tasks"] = sum(len(v) for v in reserved.values())
            except Exception:
                pass

        return {
            "timestamp": now,
            "elapsed_sec": round(elapsed, 1),
            "process": {"rss_mb": rss_mb, "cpu_pct": cpu_pct},
            "db_pool": pool_metrics,
            "redis": redis_metrics,
            "celery": celery_metrics,
        }

    def get_time_series(self) -> List[Dict[str, Any]]:
        """Return a copy of the sampled time-series data."""
        with self._lock:
            return list(self._samples)

    def detect_memory_leak(self, max_mb_per_min: float = 50.0) -> Tuple[bool, float]:
        """
        Analyze RSS trend. Returns (leak_detected: bool, growth_rate_mb_per_min: float).
        Threshold defaults to 50 MB/min per 21.5.2 spec.
        """
        with self._lock:
            samples = list(self._samples)

        if len(samples) < 3:
            return False, 0.0

        first_sample = samples[0]
        last_sample = samples[-1]
        duration_sec = max(1.0, last_sample["timestamp"] - first_sample["timestamp"])
        duration_min = duration_sec / 60.0

        rss_delta_mb = last_sample["process"]["rss_mb"] - first_sample["process"]["rss_mb"]
        growth_rate = rss_delta_mb / duration_min

        leak_detected = growth_rate > max_mb_per_min
        return leak_detected, round(growth_rate, 2)

    def get_summary(self) -> Dict[str, Any]:
        """Aggregate summary metrics across the sampling window."""
        with self._lock:
            samples = list(self._samples)

        if not samples:
            return {
                "sample_count": 0,
                "duration_sec": 0,
                "rss_peak_mb": 0.0,
                "rss_growth_mb": 0.0,
                "pool_peak_utilization_pct": 0.0,
                "memory_leak_detected": False,
                "growth_rate_mb_per_min": 0.0,
            }

        rss_values = [s["process"]["rss_mb"] for s in samples]
        pool_util = [s["db_pool"]["utilization_pct"] for s in samples]
        duration = (self._end_time or time.time()) - (self._start_time or time.time())
        leak_detected, rate = self.detect_memory_leak()

        return {
            "sample_count": len(samples),
            "duration_sec": round(duration, 1),
            "rss_start_mb": rss_values[0],
            "rss_peak_mb": max(rss_values),
            "rss_end_mb": rss_values[-1],
            "rss_growth_mb": round(rss_values[-1] - rss_values[0], 2),
            "pool_peak_utilization_pct": max(pool_util) if pool_util else 0.0,
            "memory_leak_detected": leak_detected,
            "growth_rate_mb_per_min": rate,
        }

    def to_json(self) -> str:
        """Serialize summary and time-series to JSON."""
        return json.dumps({
            "summary": self.get_summary(),
            "time_series": self.get_time_series(),
        }, indent=2)
