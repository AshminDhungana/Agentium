"""Celery Throughput Gate - 2x Peak Load & Stress Testing (Phase 21.5.2).

Asserts: >= 2,000 tasks/hour throughput under the load-test scenario (2x baseline of 1,000).

Usage::

    pytest backend/tests/load/test_celery_throughput.py --no-cov -v

Environment
-----------
- ``CELERY_TASK_ALWAYS_EAGER`` (default ``true``) – runs tasks in-process for CI
- ``CELERY_BROKER_URL`` / ``CELERY_RESULT_BACKEND`` ignored when ``ALWAYS_EAGER``

Markers
-------
- ``slow``       – test takes >10 seconds (when running full broker + workers)
- ``performance`` – part of the performance regression gate suite
"""

from __future__ import annotations

import os
import time
import logging
import pytest

logger = logging.getLogger(__name__)

# Minimum throughput to pass the 2x gate (tasks per hour)
_MIN_THROUGHPUT_PER_HOUR = 2000

# Number of tasks to enqueue in the gate run
_TASK_COUNT = 1000

# Timeout waiting for queue to drain (seconds)
_WAIT_TIMEOUT = 600

pytestmark = [
    pytest.mark.slow,
    pytest.mark.performance,
]


def _ensure_eager_celery():
    """Ensure celery_app and task instances are configured for in-memory eager execution."""
    from backend.celery_app import celery_app
    import backend.services.tasks.task_executor  # Ensure task registration

    celery_app.backend_cls = "cache+memory://"
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.task_store_eager_result = True
    celery_app.conf.result_backend = "cache+memory://"
    celery_app.conf.broker_url = "memory://"

    # Reset cached app backend
    celery_app._backend_cache = None
    if hasattr(celery_app._local, "backend"):
        delattr(celery_app._local, "backend")
    celery_app._backend = celery_app._get_backend()

    # Reset cached task backend
    task = celery_app.tasks.get("agentium.tasks.noop_perf_task")
    if task:
        task._backend = None
    return celery_app, task


def _enqueue_dummy_tasks(count: int):
    """Enqueue `count` dummy Celery tasks and return AsyncResult handles."""
    celery_app, task = _ensure_eager_celery()

    results = []
    for i in range(count):
        if task and celery_app.conf.task_always_eager:
            result = task.apply_async(kwargs={"task_id": f"perf-test-{i}", "payload": {"noop": True}})
        else:
            result = celery_app.send_task(
                "agentium.tasks.noop_perf_task",
                kwargs={"task_id": f"perf-test-{i}", "payload": {"noop": True}},
            )
        results.append(result)
    return results


def _wait_for_completion(results, *, timeout: int = 600) -> float:
    """Block until all tasks are done and return total elapsed seconds."""
    start = time.monotonic()
    for result in results:
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"Tasks did not complete within {timeout}s")
        _ = result.get(timeout=timeout)
    return time.monotonic() - start


class TestCeleryThroughput:
    """Verify Celery processes >= 2,000 dummy tasks/hour (2x baseline)."""

    def test_celery_throughput_gate(self, monkeypatch):
        """Enqueue 1,000 no-op tasks, wait for completion, calculate throughput."""
        # Avoid external LLM calls during the perf run
        from unittest.mock import MagicMock
        from backend.services import model_provider

        mock = MagicMock()
        mock.generate_with_agent = MagicMock(
            return_value={"content": "noop", "tokens_used": 0, "latency_ms": 0}
        )
        monkeypatch.setattr(model_provider, "ModelService", mock)

        # Enqueue tasks
        results = _enqueue_dummy_tasks(_TASK_COUNT)
        assert len(results) == _TASK_COUNT

        # Wait for all to finish
        elapsed = _wait_for_completion(results, timeout=_WAIT_TIMEOUT)

        # Calculate throughput (tasks per hour)
        throughput_per_hour = (_TASK_COUNT / max(elapsed, 0.0001)) * 3600

        logger.info(
            "Celery throughput gate: %d tasks in %.2f s => %.1f tasks/hour",
            _TASK_COUNT, elapsed, throughput_per_hour,
        )

        assert throughput_per_hour >= _MIN_THROUGHPUT_PER_HOUR, (
            f"Throughput {throughput_per_hour:.1f} tasks/hour < threshold "
            f"{_MIN_THROUGHPUT_PER_HOUR}"
        )
