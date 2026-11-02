"""BaselineMeasurer - Establish pre-load baselines across 4 dimensions (Phase 21.5.2).

Captures pre-load metrics (API latency, DB single-query latency, baseline process RSS)
across warm-up and sample windows, saving results to `baseline.json` for regression gating.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import statistics
import time
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
from urllib.parse import urlparse

import psutil
from sqlalchemy import text

try:
    from backend.models.database import get_db_context
except Exception:  # pragma: no cover
    get_db_context = None

logger = logging.getLogger(__name__)


class BaselineMeasurer:
    """Measures and records pre-load system baseline performance."""

    def __init__(self, host: str = "http://localhost:8000"):
        self.host = host.rstrip("/")
        self._baseline_data: Optional[Dict[str, Any]] = None

    def _is_host_reachable(self) -> bool:
        """Quick 20ms socket check to avoid blocking on unreachable host."""
        try:
            parsed = urlparse(self.host)
            h = parsed.hostname or "localhost"
            p = parsed.port or 8000
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.02)
            res = s.connect_ex((h, p))
            s.close()
            return res == 0
        except Exception:
            return False

    def measure_db_latency(self, iterations: int = 10) -> Dict[str, float]:
        """Measure single SELECT 1 query latency in ms."""
        latencies: List[float] = []
        if get_db_context is None:
            return {"avg_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

        for _ in range(iterations):
            t0 = time.perf_counter()
            try:
                with get_db_context() as db:
                    db.execute(text("SELECT 1"))
                latencies.append((time.perf_counter() - t0) * 1000.0)
            except Exception as e:
                logger.debug("Baseline DB query error: %s", e)
                # If DB is not reachable on first attempt, do not retry 10 times
                break

        if not latencies:
            return {"avg_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

        latencies.sort()
        p95_idx = min(int(len(latencies) * 0.95), len(latencies) - 1)
        return {
            "avg_ms": round(statistics.mean(latencies), 2),
            "p95_ms": round(latencies[p95_idx], 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
        }

    def measure_api_latency(self, endpoint: str = "/healthz", iterations: int = 5) -> Dict[str, float]:
        """Measure API probe latency in ms (best-effort if host alive)."""
        if not self._is_host_reachable():
            return {"avg_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

        latencies: List[float] = []
        url = f"{self.host}{endpoint}"

        for _ in range(iterations):
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AgentiumBaseline/1.0"})
                with urllib.request.urlopen(req, timeout=0.5) as resp:
                    if resp.status == 200:
                        latencies.append((time.perf_counter() - t0) * 1000.0)
            except Exception:
                pass

        if not latencies:
            return {"avg_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

        latencies.sort()
        p95_idx = min(int(len(latencies) * 0.95), len(latencies) - 1)
        return {
            "avg_ms": round(statistics.mean(latencies), 2),
            "p95_ms": round(latencies[p95_idx], 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
        }

    def measure_process_rss(self) -> float:
        """Measure baseline RSS memory in MB."""
        try:
            return round(psutil.Process().memory_info().rss / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def capture(self) -> Dict[str, Any]:
        """Execute full baseline measurement across all dimensions."""
        logger.info("Capturing baseline measurements...")
        db_stats = self.measure_db_latency(iterations=10)
        api_stats = self.measure_api_latency(iterations=5)
        rss_mb = self.measure_process_rss()

        self._baseline_data = {
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "host": self.host,
            "db_latency": db_stats,
            "api_latency": api_stats,
            "process_rss_mb": rss_mb,
            "expected_targets": {
                "max_api_p95_ms": 500.0,
                "target_rps": 1000.0,
                "target_tasks_per_hr": 2000.0,
                "target_ws_concurrency": 500,
                "max_memory_growth_mb_per_min": 50.0,
            },
        }
        return self._baseline_data

    def save(self, path: str = "baseline.json") -> str:
        """Save baseline data to JSON file."""
        if self._baseline_data is None:
            self.capture()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._baseline_data, f, indent=2)
        logger.info("Saved baseline metrics to %s", path)
        return path

    @staticmethod
    def load(path: str = "baseline.json") -> Optional[Dict[str, Any]]:
        """Load baseline data from JSON file."""
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def compare_against_baseline(
        current_metrics: Dict[str, Any],
        baseline: Dict[str, Any],
        tolerance_multiplier: float = 1.5,
    ) -> Dict[str, Any]:
        """
        Compare current metrics to baseline with tolerance multiplier.
        E.g. p95 latency should not degrade beyond 1.5x baseline.
        """
        verdicts: Dict[str, Any] = {}

        # DB latency check
        base_db = baseline.get("db_latency", {}).get("p95_ms", 0.0)
        curr_db = current_metrics.get("db_latency_p95_ms", 0.0)
        if base_db > 0 and curr_db > 0:
            limit = base_db * tolerance_multiplier
            verdicts["db_latency"] = {
                "baseline_ms": base_db,
                "current_ms": curr_db,
                "threshold_ms": round(limit, 2),
                "passed": curr_db <= limit,
            }

        # API latency check
        base_api = baseline.get("api_latency", {}).get("p95_ms", 0.0)
        curr_api = current_metrics.get("api_latency_p95_ms", 0.0)
        if base_api > 0 and curr_api > 0:
            limit = max(500.0, base_api * tolerance_multiplier)
            verdicts["api_latency"] = {
                "baseline_ms": base_api,
                "current_ms": curr_api,
                "threshold_ms": round(limit, 2),
                "passed": curr_api <= limit,
            }

        return verdicts
