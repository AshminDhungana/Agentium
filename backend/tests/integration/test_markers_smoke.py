"""Smoke test verifying custom pytest markers work."""
import pytest


@pytest.mark.requires_redis
def test_requires_redis_marker_exists():
    """Marker should be recognized by pytest."""
    pass


@pytest.mark.requires_docker
def test_requires_docker_marker_exists():
    pass


@pytest.mark.requires_alembic_head
def test_requires_alembic_head_marker_exists():
    pass