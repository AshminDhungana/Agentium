"""Unit tests for UnifiedReportGenerator (Phase 21.5.2)."""

import os
import tempfile
import pytest
from backend.tests.load.report import UnifiedReportGenerator


def test_unified_report_generator_quick_mode_pass():
    """Verify quick mode evaluates pass criteria when all thresholds are met."""
    generator = UnifiedReportGenerator(mode="quick")
    locust_stats = {
        "total_rps": 800.0,
        "p95_ms": 250.0,
        "error_rate": 0.002,
        "celery_tasks_per_hr": 1600.0,
        "ws_error_rate": 0.001,
        "ws_ping_p95_ms": 30.0,
    }
    sampler_summary = {
        "pool_peak_utilization_pct": 60.0,
        "memory_leak_detected": False,
        "growth_rate_mb_per_min": 5.0,
        "rss_peak_mb": 150.0,
    }

    report = generator.generate(locust_stats=locust_stats, sampler_summary=sampler_summary)

    assert report["overall_pass"] is True
    assert report["components"]["api"]["passed"] is True
    assert report["components"]["db_pool"]["passed"] is True
    assert report["components"]["celery"]["passed"] is True
    assert report["components"]["websocket"]["passed"] is True
    assert report["components"]["memory"]["passed"] is True


def test_unified_report_generator_full_mode_fail():
    """Verify full mode fails if API RPS falls below 2x target (1,000 RPS)."""
    generator = UnifiedReportGenerator(mode="full")
    locust_stats = {
        "total_rps": 850.0,  # Below 1,000 RPS target for full mode
        "p95_ms": 250.0,
        "error_rate": 0.0,
        "celery_tasks_per_hr": 2200.0,
        "ws_error_rate": 0.0,
        "ws_ping_p95_ms": 40.0,
    }
    sampler_summary = {
        "pool_peak_utilization_pct": 70.0,
        "memory_leak_detected": False,
        "growth_rate_mb_per_min": 10.0,
    }

    report = generator.generate(locust_stats=locust_stats, sampler_summary=sampler_summary)
    assert report["overall_pass"] is False
    assert report["components"]["api"]["passed"] is False
    assert report["components"]["celery"]["passed"] is True


def test_unified_report_html_and_json_rendering():
    """Verify HTML and JSON export works and creates readable files."""
    generator = UnifiedReportGenerator(mode="quick")
    report = generator.generate()

    with tempfile.TemporaryDirectory() as tmp_dir:
        html_path = os.path.join(tmp_dir, "report.html")
        json_path = os.path.join(tmp_dir, "report.json")

        generator.render_html(report, html_path)
        generator.save_json(report, json_path)

        assert os.path.exists(html_path)
        assert os.path.exists(json_path)

        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Agentium 2× Peak Load & Stress Test Report" in content
            assert "metricsChart" in content

