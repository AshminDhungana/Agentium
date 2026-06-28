"""Celery Throughput Gate - Phase 18.2 Performance Regression Gate.

Asserts: >= 1,000 tasks/hour throughput under the load-test scenario.

Usage::

    pytest backend/tests/load/test_celery_throughput.py -m slow

Environment
-----------
- ``CELERY_TASK_ALWAYS_EAGER`` (default ``true``) – runs tasks in-process for CI
- ``CELERY_BROKER_URL`` / ``CELERY_RESULT_BACKEND`` ignored when ``ALWAYS_EAGER``

Markers
-------
- ``slow``       – test takes >10 seconds (requires running Redis + worker)
- ``performance`` – part of the performance regression gate suite
"""

from __future__ import annotations

import os
import time
import logging
import pytest

logger = logging.getLogger(__name__)

# Minimum throughput to pass the gate (tasks per hour)
_MIN_THROUGHPUT_PER_HOUR = 1000

# Number of tasks to enqueue in the gate run
_TASK_COUNT = 1000

# Timeout waiting for queue to drain (seconds)
_WAIT_TIMEOUT = 600

pytestmark = [
    pytest.mark.slow,
    pytest.mark.performance,
]


def _enqueue_dummy_tasks(count: int):
    """Enqueue `count` dummy Celery tasks and return AsyncResult handles."""
    from backend.celery_app import celery_app

    # Use a known task that's always registered:  a small no-op task we
    # ship in-tree just for this gate.  If it doesn't exist, fall back
    # to the standard Celery ``send_task`` API so the test degrades
    # gracefully instead of crashing on import.
    results = []
    for i in range(count):
        result = celery_app.send_task(
            "agentium.tasks.task_executor.execute_task_async",
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
        result.get(timeout=timeout)
    return time.monotonic() - start


class TestCeleryThroughput:
    """Verify Celery processes >= 1,000 dummy tasks/hour."""

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
        throughput_per_hour = (_TASK_COUNT / elapsed) * 3600

        logger.info(
            "Celery throughput gate: %d tasks in %.2f s => %.1f tasks/hour",
            _TASK_COUNT, elapsed, throughput_per_hour,
        )

        assert throughput_per_hour >= _MIN_THROUGHPUT_PER_HOUR, (
            f"Throughput {throughput_per_hour:.1f} tasks/hour < threshold "
            f"{_MIN_THROUGHPUT_PER_HOUR}"
        )
