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
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")


@pytest.fixture(autouse=True)
def celery_eager():
    """Configure Celery to run tasks synchronously in-process."""
    from backend.celery_app import celery_app
    import backend.services.tasks.task_executor  # Ensure task registration

    celery_app.backend_cls = "cache+memory://"
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    # Reset cached backend to guarantee cache+memory is used in-process
    celery_app._backend_cache = None
    if hasattr(celery_app._local, "backend"):
        delattr(celery_app._local, "backend")
    celery_app._backend = celery_app._get_backend()

    task = celery_app.tasks.get("agentium.tasks.noop_perf_task")
    if task:
        task._backend = None

    yield celery_app
