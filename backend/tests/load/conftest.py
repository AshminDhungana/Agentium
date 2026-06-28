"""Conftest for load / throughput tests.

Configures Celery to run in eager (in-process) mode so that
``test_celery_throughput.py`` works without a running Redis broker or
Celery worker — matching the ``CELERY_TASK_ALWAYS_EAGER=true`` env var
set in CI.
"""

from __future__ import annotations

import os
import pytest

# Ensure eager mode env var is set before any Celery import
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")


@pytest.fixture(autouse=True)
def celery_eager():
    """Configure Celery to run tasks synchronously in-process."""
    from backend.celery_app import celery_app

    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    yield celery_app
