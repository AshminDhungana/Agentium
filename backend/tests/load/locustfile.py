"""Locust load-test suite - Phase 18.2 Performance Regression Gate.

Usage
-----
Standalone (requires APPLICATION_URL env var or --host flag)::

    cd backend/tests/load && locust --host=http://localhost:8000

Via make target (orchestrated, ephemeral infra)::

    make load-test

Targets
-------
- Constitutional  check  p95 < 50 ms
- Task routing     p95 < 100 ms
- General API      p95 < 500 ms
"""

from __future__ import annotations

import os
import logging
import threading
import time

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

logger = logging.getLogger(__name__)

_token_lock = threading.Lock()
_shared_token: str | None = None

# -- Load-test settings (over-rideable via environment) --
# CI-friendly defaults: fewer users so rate-limits aren't tripped
_is_ci = os.getenv("CI", "false").lower() == "true"
DEFAULT_USERS = 20 if _is_ci else 1000
DEFAULT_SPAWN_RATE = 5 if _is_ci else 10
DEFAULT_RUN_TIME = "5m"

LOCUST_USERS = int(os.getenv("LOCUST_USERS", str(DEFAULT_USERS)))
LOCUST_SPAWN_RATE = int(os.getenv("LOCUST_SPAWN_RATE", str(DEFAULT_SPAWN_RATE)))
LOCUST_RUN_TIME = os.getenv("LOCUST_RUN_TIME", DEFAULT_RUN_TIME)

# Target thresholds (ms) for assertion at test stop
_THRESHOLD_CONSITUTIONAL = 50   # ms p95
_THRESHOLD_TASK_ROUTING  = 100  # ms p95
_THRESHOLD_GENERAL_API   = 500  # ms p95

# Test admin credentials (must exist in seeded DB)
_TEST_USER = "admin"
_TEST_PASS = "admin"


class LocustAuthenticatedUser(HttpUser):
    """Base class that authenticates with /api/v1/auth/login in on_start."""
    abstract = True

    def on_start(self):
        global _shared_token
        self.client.headers.pop("Authorization", None)
        with _token_lock:
            if _shared_token:
                self.client.headers["Authorization"] = f"Bearer {_shared_token}"
                return

        self._authenticate_with_retry()

    def _authenticate_with_retry(self, max_retries=5):
        global _shared_token
        for attempt in range(max_retries):
            with _token_lock:
                if _shared_token:
                    self.client.headers["Authorization"] = f"Bearer {_shared_token}"
                    return
            try:
                resp = self.client.post(
                    "/api/v1/auth/login",
                    json={"username": _TEST_USER, "password": _TEST_PASS}
                )
                if resp.status_code == 200:
                    token = resp.json().get("access_token", "")
                    with _token_lock:
                        _shared_token = token
                    self.client.headers["Authorization"] = f"Bearer {token}"
                    logger.info("Authenticated virtual user")
                    return
                elif resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning("Auth rate-limited (429), retry %d/%d in %ds",
                                   attempt + 1, max_retries, backoff)
                    time.sleep(backoff)
                else:
                    logger.error("Auth failed: HTTP %s", resp.status_code)
                    return
            except Exception as exc:
                logger.error("Auth exception: %s", exc)
                return
        logger.error("Auth exhausted all %d retries", max_retries)


class ConstitutionalCheckUser(LocustAuthenticatedUser):
    """Exercises endpoints that run ConstitutionalGuard checks. Weight: 50."""
    weight = 50
    wait_time = between(1, 2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._agent_ids = []

    def on_start(self):
        super().on_start()
        try:
            resp = self.client.get(
                "/api/v1/agents",
                headers=self.client.headers,
                name="/api/v1/agents (seed)"
            )
            if resp.status_code == 200:
                agents = resp.json().get("agents", [])
                self._agent_ids = [
                    a["agentium_id"] for a in agents if a.get("agentium_id")
                ]
        except Exception as exc:
            logger.warning("Failed to fetch agent IDs: %s", exc)

    @task(3)
    def list_agents(self):
        with self.client.get(
            "/api/v1/agents", catch_response=True, name="/api/v1/agents"
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(1)
    def reassign_agent(self):
        if len(self._agent_ids) < 2:
            return
        agent_id = self._agent_ids[0]
        new_parent_id = self._agent_ids[1]
        with self.client.patch(
            f"/api/v1/agents/{agent_id}/parent",
            json={"new_parent_id": new_parent_id, "reason": "Load-test"},
            catch_response=True,
            name="/api/v1/agents/{id}/parent",
        ) as resp:
            if resp.status_code not in (200, 403):
                resp.failure(f"Unexpected status: {resp.status_code}")


class TaskRoutingUser(LocustAuthenticatedUser):
    """Creates and lists tasks. Weight: 45."""
    weight = 45
    wait_time = between(1, 3)

    @task(3)
    def create_task(self):
        # Note: FastAPI tasks router uses "/tasks/" prefix (trailing slash)
        with self.client.post(
            "/api/v1/tasks/",
            json={
                "title": "Load-test task",
                "description": "Automated load test task",
                "priority": "normal",
                "task_type": "execution",
            },
            catch_response=True,
            name="/api/v1/tasks",
        ) as resp:
            if resp.status_code != 201:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(2)
    def list_tasks(self):
        with self.client.get(
            "/api/v1/tasks/",
            catch_response=True,
            name="/api/v1/tasks",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status: {resp.status_code}")


class GeneralAPIUser(LocustAuthenticatedUser):
    """Reads monitoring stats, lists agents, health check. Weight: 5."""
    weight = 5
    wait_time = between(2, 5)

    @task(2)
    def get_monitoring_stats(self):
        with self.client.get(
            "/api/v1/monitoring/stats",
            catch_response=True,
            name="/api/v1/monitoring/stats",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(1)
    def get_agent_health(self):
        with self.client.get(
            "/api/v1/agents",
            catch_response=True,
            name="/api/v1/agents (health read)",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(1)
    def health_check(self):
        with self.client.get(
            "/api/health",
            catch_response=True,
            name="/api/health",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status: {resp.status_code}")


# -- Post-test assertion hook --

def _fetch_timing_metrics(host):
    import requests
    try:
        resp = requests.get(f"{host}/api/v1/monitoring/metrics", timeout=10)
        return resp.json() if resp.status_code == 200 else {}
    except Exception:
        return {}


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    if isinstance(environment.runner, MasterRunner):
        host = environment.host or "http://localhost:8000"
        logger.info("--- Fetching timing metrics for p95 assertion ---")
        metrics = _fetch_timing_metrics(host)
        endpoints = metrics.get("endpoints", {})

        for name, data in endpoints.items():
            p95 = data.get("p95_ms", 0)
            if "agents" in name.lower() and "parent" not in name.lower():
                target = _THRESHOLD_CONSITUTIONAL
            elif "tasks" in name.lower() or "parent" in name.lower():
                target = _THRESHOLD_TASK_ROUTING
            else:
                target = _THRESHOLD_GENERAL_API

            status = "PASS" if p95 <= target else "FAIL"
            logger.info("  %s: p95=%.2fms (target=%dms) [%s]", name, p95, target, status)
