"""Tests for UserModelConfig rate-limit columns (Task 6)."""
from backend.models.entities.user_config import UserModelConfig


def test_rate_limit_columns_exist():
    cols = {c.name for c in UserModelConfig.__table__.columns}
    assert "requests_per_minute" in cols
    assert "tokens_per_minute" in cols
    assert "max_concurrent_requests" in cols
    assert "rate_limit" not in cols  # renamed away
