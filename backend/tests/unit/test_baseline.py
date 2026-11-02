"""Unit tests for BaselineMeasurer (Phase 21.5.2)."""

import os
import tempfile
import pytest
from backend.tests.load.baseline import BaselineMeasurer


def test_baseline_capture_and_serialization():
    """Verify BaselineMeasurer captures metrics and serializes to JSON."""
    measurer = BaselineMeasurer()
    data = measurer.capture()

    assert "timestamp" in data
    assert "db_latency" in data
    assert "process_rss_mb" in data
    assert data["process_rss_mb"] > 0
    assert "expected_targets" in data
    assert data["expected_targets"]["target_rps"] == 1000.0
    assert data["expected_targets"]["target_tasks_per_hr"] == 2000.0

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        saved_path = measurer.save(tmp_path)
        assert os.path.exists(saved_path)
        loaded = BaselineMeasurer.load(saved_path)
        assert loaded is not None
        assert loaded["process_rss_mb"] == data["process_rss_mb"]
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_baseline_comparison():
    """Verify compare_against_baseline evaluates degradation tolerances."""
    baseline = {
        "db_latency": {"p95_ms": 10.0},
        "api_latency": {"p95_ms": 100.0},
    }

    # Within tolerance (1.5x)
    current_ok = {
        "db_latency_p95_ms": 14.0,
        "api_latency_p95_ms": 120.0,
    }
    verdicts_ok = BaselineMeasurer.compare_against_baseline(current_ok, baseline, tolerance_multiplier=1.5)
    assert verdicts_ok["db_latency"]["passed"] is True
    assert verdicts_ok["api_latency"]["passed"] is True

    # Degradation exceeding tolerance
    current_bad = {
        "db_latency_p95_ms": 25.0,  # > 15.0 limit
        "api_latency_p95_ms": 600.0,  # > 500.0 limit
    }
    verdicts_bad = BaselineMeasurer.compare_against_baseline(current_bad, baseline, tolerance_multiplier=1.5)
    assert verdicts_bad["db_latency"]["passed"] is False
    assert verdicts_bad["api_latency"]["passed"] is False

