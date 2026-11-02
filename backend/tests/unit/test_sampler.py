"""Unit tests for SystemSampler (Phase 21.5.2)."""

import time
import pytest
from backend.tests.load.sampler import SystemSampler


def test_sampler_single_sample():
    """Verify single sample collects process, db_pool, redis, and celery metrics."""
    sampler = SystemSampler(interval_sec=0.1)
    sample = sampler.sample_once()

    assert "timestamp" in sample
    assert "process" in sample
    assert "rss_mb" in sample["process"]
    assert sample["process"]["rss_mb"] > 0
    assert "db_pool" in sample
    assert "checked_out" in sample["db_pool"]
    assert "utilization_pct" in sample["db_pool"]


def test_sampler_background_thread_and_summary():
    """Verify sampler runs in background and generates summary statistics."""
    sampler = SystemSampler(interval_sec=0.05)
    sampler.start()
    time.sleep(0.2)
    sampler.stop()

    summary = sampler.get_summary()
    assert summary["sample_count"] >= 2
    assert summary["duration_sec"] > 0
    assert summary["rss_peak_mb"] >= summary["rss_start_mb"]
    assert "memory_leak_detected" in summary
    assert summary["memory_leak_detected"] is False

    time_series = sampler.get_time_series()
    assert len(time_series) == summary["sample_count"]


def test_sampler_memory_leak_detection():
    """Verify detect_memory_leak correctly flags simulated growth exceeding threshold."""
    sampler = SystemSampler(interval_sec=0.1)
    # Inject fake samples with 100 MB growth over 10 seconds (600 MB/min)
    now = time.time()
    sampler._samples = [
        {"timestamp": now, "process": {"rss_mb": 100.0}, "db_pool": {}},
        {"timestamp": now + 5, "process": {"rss_mb": 150.0}, "db_pool": {}},
        {"timestamp": now + 10, "process": {"rss_mb": 200.0}, "db_pool": {}},
    ]
    leak_detected, rate = sampler.detect_memory_leak(max_mb_per_min=50.0)
    assert leak_detected is True
    assert rate == 600.0  # 100 MB / (10/60) min = 600 MB/min

