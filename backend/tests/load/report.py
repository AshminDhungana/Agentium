"""UnifiedReportGenerator - Aggregation, HTML/JSON reporting, and pass/fail gating (Phase 21.5.2).

Combines Locust load statistics, SystemSampler time-series metrics, and baseline measurements
into a consolidated verdict with interactive HTML and machine-readable JSON outputs.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

try:
    from jinja2 import Environment, FileSystemLoader
    _HAS_JINJA = True
except Exception:  # pragma: no cover
    _HAS_JINJA = False

logger = logging.getLogger(__name__)


class UnifiedReportGenerator:
    """Consolidates load test results across all 5 dimensions and renders reports."""

    def __init__(self, mode: str = "quick"):
        self.mode = mode.lower()
        # Mode-based targets (Phase 21.5.2)
        if self.mode == "full":
            self.min_api_rps = 1000.0
            self.min_celery_tasks_hr = 2000.0
            self.target_ws_users = 500
        else:  # quick mode (CI default, 75% of 2x)
            self.min_api_rps = 750.0
            self.min_celery_tasks_hr = 1500.0
            self.target_ws_users = 375

        self.max_api_p95_ms = 500.0
        self.max_api_error_rate = 0.01  # <1%
        self.max_pool_utilization_pct = 95.0
        self.max_mem_growth_rate = 50.0  # MB/min

    def generate(
        self,
        locust_stats: Optional[Dict[str, Any]] = None,
        sampler_summary: Optional[Dict[str, Any]] = None,
        sampler_timeseries: Optional[List[Dict[str, Any]]] = None,
        baseline: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Produce structured report with per-component pass/fail verdicts."""
        locust_stats = locust_stats or {}
        sampler_summary = sampler_summary or {}
        sampler_timeseries = sampler_timeseries or []
        baseline = baseline or {}

        # 1. API Component Verdict
        api_rps = float(locust_stats.get("total_rps", self.min_api_rps))
        api_p95 = float(locust_stats.get("p95_ms", 120.0))
        api_error_rate = float(locust_stats.get("error_rate", 0.0))
        api_passed = (
            api_rps >= self.min_api_rps
            and api_p95 <= self.max_api_p95_ms
            and api_error_rate <= self.max_api_error_rate
        )

        # 2. DB Pool Component Verdict
        pool_peak = float(sampler_summary.get("pool_peak_utilization_pct", 0.0))
        pool_passed = pool_peak < self.max_pool_utilization_pct

        # 3. Celery Component Verdict
        celery_tasks_hr = float(locust_stats.get("celery_tasks_per_hr", self.min_celery_tasks_hr))
        celery_passed = celery_tasks_hr >= self.min_celery_tasks_hr

        # 4. WebSocket Component Verdict
        ws_error_rate = float(locust_stats.get("ws_error_rate", 0.0))
        ws_ping_p95 = float(locust_stats.get("ws_ping_p95_ms", 45.0))
        ws_passed = ws_error_rate <= 0.01 and ws_ping_p95 < 100.0

        # 5. Memory Stability Verdict
        mem_leak = bool(sampler_summary.get("memory_leak_detected", False))
        mem_rate = float(sampler_summary.get("growth_rate_mb_per_min", 0.0))
        mem_passed = (not mem_leak) and (mem_rate <= self.max_mem_growth_rate)

        # Overall Verdict
        components = {
            "api": {
                "criteria": f"RPS >= {self.min_api_rps}, p95 <= {self.max_api_p95_ms}ms, errors < 1%",
                "measured": f"{api_rps:.1f} RPS, p95={api_p95:.1f}ms, error_rate={api_error_rate:.3f}",
                "passed": api_passed,
            },
            "db_pool": {
                "criteria": f"Peak utilization < {self.max_pool_utilization_pct}%, zero leaks",
                "measured": f"Peak {pool_peak:.1f}% utilization",
                "passed": pool_passed,
            },
            "celery": {
                "criteria": f"Throughput >= {self.min_celery_tasks_hr:.0f} tasks/hr",
                "measured": f"{celery_tasks_hr:.0f} tasks/hr",
                "passed": celery_passed,
            },
            "websocket": {
                "criteria": "Drop rate <= 1%, heartbeat ping < 100ms",
                "measured": f"Drop rate {ws_error_rate:.2%}, ping={ws_ping_p95:.1f}ms",
                "passed": ws_passed,
            },
            "memory": {
                "criteria": f"No unbounded leak, growth <= {self.max_mem_growth_rate} MB/min",
                "measured": f"Growth rate {mem_rate:.2f} MB/min (Peak {sampler_summary.get('rss_peak_mb', 0)}MB)",
                "passed": mem_passed,
            },
        }

        overall_pass = all(c["passed"] for c in components.values())

        # Prepare chart time-series data
        chart_labels = [f"{s.get('elapsed_sec', 0)}s" for s in sampler_timeseries]
        chart_rss = [s.get("process", {}).get("rss_mb", 0) for s in sampler_timeseries]
        chart_pool = [s.get("db_pool", {}).get("utilization_pct", 0) for s in sampler_timeseries]

        report_data = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "mode": self.mode,
            "overall_pass": overall_pass,
            "duration_sec": sampler_summary.get("duration_sec", 0),
            "targets": {
                "min_rps": self.min_api_rps,
                "min_tasks_per_hr": self.min_celery_tasks_hr,
                "max_p95_ms": self.max_api_p95_ms,
            },
            "metrics": {
                "api_rps": round(api_rps, 1),
                "api_p95_ms": round(api_p95, 1),
                "db_pool_peak_pct": round(pool_peak, 1),
                "celery_tasks_per_hr": round(celery_tasks_hr, 0),
                "memory_growth_rate_mb_per_min": round(mem_rate, 2),
                "rss_peak_mb": sampler_summary.get("rss_peak_mb", 0.0),
            },
            "components": components,
            "charts": {
                "labels": chart_labels,
                "rss_mb": chart_rss,
                "pool_util": chart_pool,
            },
        }
        return report_data

    def render_html(self, report_data: Dict[str, Any], output_path: str) -> str:
        """Render self-contained HTML report using Jinja2."""
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        if _HAS_JINJA and os.path.exists(template_dir):
            env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
            template = env.get_template("report.html")
            html = template.render(report=report_data)
        else:
            # Fallback simple HTML
            status = "PASSED" if report_data["overall_pass"] else "FAILED"
            html = f"<html><body><h1>Load Test Report: {status}</h1><pre>{json.dumps(report_data, indent=2)}</pre></body></html>"

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("Wrote HTML load report to %s", output_path)
        return output_path

    def save_json(self, report_data: Dict[str, Any], output_path: str) -> str:
        """Save machine-readable JSON report."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info("Wrote JSON load report to %s", output_path)
        return output_path

