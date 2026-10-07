# backend/tests/unit/test_config_alert_dedup.py
"""
Test alert deduplication configuration values.
"""
from backend.core.config import settings

def test_alert_dedup_default_window():
    """Default deduplication window should be 300 seconds (5 min)."""
    assert hasattr(settings, 'ALERT_DEDUP_WINDOW_SECONDS')
    assert settings.ALERT_DEDUP_WINDOW_SECONDS == 300

def test_alert_dedup_windows_dict():
    """Per-alert-type windows dict should exist."""
    assert hasattr(settings, 'ALERT_DEDUP_WINDOWS')
    assert isinstance(settings.ALERT_DEDUP_WINDOWS, dict)