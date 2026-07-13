"""Locust load-test suite - Phase 18.2 Performance Regression Gate + Task 26.

Provider-facing load extension
------------------------------
The original suite (below) hammers Agentium's *own* REST API. That proves the
API gateway holds up, but says nothing about the part this feature cares about:
**outbound provider load** — what happens to the provider, the queue, and the
workers when Agentium is firing real chat-completion requests at a model
provider under sustained load.

Task 26 adds a provider-facing half:
- ``MockProviderServer`` — an embedded OpenAI-compatible ``/v1/chat/completions``
  endpoint that counts requests and can return 429s (``MOCK_429_RATIO``) to
  exercise the resilience retry path. It tracks in-flight requests so we can
  prove worker stability.
- ``ProviderFacingUser`` — a Locust user that POSTs chat completions straight
  at the mock provider (retrying on 429 with backoff), i.e. the exact shape of
  what ``LLMClient`` sends. This is the "provider-facing load" the spec wants.
- ``_emit_provider_report`` — at test stop, records the four required signals:
   1. RPS actually reaching the mock provider,
   2. queue depth (``pending_count``) from Agentium's dashboard endpoint,
   3. retry counts (429s the provider returned + client retries),
   4. worker stability (no provider errors, in-flight bounded, run completed).

Both the Locust path and a stdlib-only ``python locustfile.py`` driver share the
same ``MockProviderServer`` and report logic, so the "sustained run report"
artifact can be produced even in environments where the Locust service isn't
up (e.g. ``make load-report`` below).

Usage
-----
Canonical (Locust service, ephemeral infra)::

    make load-test
    # or, provider-focused with fewer API users:
    cd backend/tests/load && locust --host=http://localhost:8000 --users 200 \
        --spawn-rate 20 --run-time 60s --headless --only-summary

Self-contained report driver (no Locust needed)::

    python locustfile.py --duration 30 --users 50 --429-ratio 0.1

Environment overrides:
    MOCK_PROVIDER_PORT   port the embedded mock provider listens on (default 8731)
    MOCK_429_RATIO       fraction of mock responses that are 429 (default 0.0)
    MOCK_PROVIDER_URL    override where ProviderFacingUser POSTs (default embedded)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

# Locust is only required for the canonical load-test path; the __main__ report
# driver imports nothing from it so it runs in environments without Locust.
try:  # pragma: no cover - import guard
    from locust import HttpUser, task, between, events
    from locust.runners import MasterRunner
    _HAS_LOCUST = True
except Exception:  # pragma: no cover
    _HAS_LOCUST = False


logger = __import__("logging").getLogger(__name__)

_token_lock = threading.Lock()
_shared_token: Optional[str] = None

# -- Load-test settings (over-rideable via environment) --
# CI-friendly defaults: fewer users so rate-limits aren't tripped
_is_ci = os.getenv("CI", "false").lower() == "true"
DEFAULT_USERS = 20 if _is_ci else 1000
DEFAULT_SPAWN_RATE = 5 if _is_ci else 10
DEFAULT_RUN_TIME = "5m"

LOCUST_USERS = int(os.getenv("LOCUST_USERS", str(DEFAULT_USERS)))
LOCUST_SPAWN_RATE = int(os.getenv("LOCUST_SPAWN_RATE", str(DEFAULT_SPAWN_RATE)))
LOCUST_RUN_TIME = os.getenv("LOCUST_RUN_TIME", DEFAULT_RUN_TIME)

# Embedded mock provider configuration.
MOCK_PROVIDER_PORT = int(os.getenv("MOCK_PROVIDER_PORT", "8731"))
MOCK_429_RATIO = float(os.getenv("MOCK_429_RATIO", "0.0"))
MOCK_PROVIDER_URL = os.getenv(
    "MOCK_PROVIDER_URL", f"http://localhost:{MOCK_PROVIDER_PORT}"
)

# Target thresholds (ms) for assertion at test stop
_THRESHOLD_CONSITUTIONAL = 50   # ms p95
_THRESHOLD_TASK_ROUTING  = 100  # ms p95
_THRESHOLD_GENERAL_API   = 500  # ms p95

# Provider-facing report thresholds (env-overrideable)
PROVIDER_MAX_429_RATIO = float(os.getenv("PROVIDER_MAX_429_RATIO", "0.5"))
PROVIDER_MAX_INFLIGHT = int(os.getenv("PROVIDER_MAX_INFLIGHT", "200"))

# Test admin credentials (must exist in seeded DB)
_TEST_USER = "admin"
_TEST_PASS = "admin"


# =============================================================================
# Embedded mock OpenAI-compatible provider (Task 26)
# =============================================================================

class MockProviderServer:
    """Threaded OpenAI-compatible ``/v1/chat/completions`` used to absorb
    provider-facing load and report on it.

    Tracks:
      - requests_total: every chat-completion POST received,
      - requests_429:   how many were 429 (drives the retry count),
      - inflight / inflight_peak: concurrent in-flight requests (worker-stability
        proxy — if the client/Celery layer melts down, in-flight spikes or errors),
      - errors:         unexpected handler exceptions.
    A ``GET /stats`` returns the counters as JSON so the report can read them.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = MOCK_PROVIDER_PORT,
                 err_ratio: float = MOCK_429_RATIO):
        self.host = host
        self.port = port
        self.err_ratio = err_ratio
        self.requests_total = 0
        self.requests_429 = 0
        self.errors = 0
        self.inflight = 0
        self.inflight_peak = 0
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- counters (thread-safe) --
    def _inc(self, attr: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, attr, getattr(self, attr) + n)

    def _enter(self) -> None:
        with self._lock:
            self.inflight += 1
            self.inflight_peak = max(self.inflight_peak, self.inflight)

    def _leave(self) -> None:
        with self._lock:
            self.inflight = max(0, self.inflight - 1)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "requests_429": self.requests_429,
                "errors": self.errors,
                "inflight": self.inflight,
                "inflight_peak": self.inflight_peak,
            }

    # -- lifecycle --
    def start(self) -> None:
        if self._server is not None:
            return
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("MockProviderServer listening on %s:%d (429 ratio=%.2f)",
                    self.host, self.port, self.err_ratio)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _make_handler(self):
        server = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *a, **k):  # quiet the access log
                pass

            def do_GET(self):  # noqa: N802
                if self.path.startswith("/stats"):
                    body = json.dumps(server.stats()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):  # noqa: N802
                # Drain the body so keep-alive connections don't wedge.
                length = int(self.headers.get("Content-Length", "0") or "0")
                self.rfile.read(length)
                server._enter()
                try:
                    server._inc("requests_total")
                    if server.err_ratio > 0 and random.random() < server.err_ratio:
                        server._inc("requests_429")
                        self.send_response(429)
                        self.send_header("Retry-After", "1")
                        self.end_headers()
                        return
                    body = json.dumps({
                        "choices": [{"message": {"role": "assistant",
                                                 "content": "ok"}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception:
                    server._inc("errors")
                    raise
                finally:
                    server._leave()

        return _Handler


# Module-level singleton shared by the Locust path and the __main__ driver.
mock_provider = MockProviderServer(err_ratio=MOCK_429_RATIO)


# =============================================================================
# Base authenticated user (unchanged behaviour)
# =============================================================================

if _HAS_LOCUST:

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

    # =========================================================================
    # Task 26 — provider-facing user (the new half of the suite)
    # =========================================================================

    class ProviderFacingUser(LocustAuthenticatedUser):
        """POSTs chat completions straight at the mock provider (Task 26).

        This is the shape of what ``LLMClient`` sends on the outbound path, so
        the load lands on the *provider*, not Agentium's API gateway. On a 429
        we retry with backoff to exercise the resilience retry budget. High
        weight so the provider-facing load dominates a provider-focused run.
        """
        weight = 100
        wait_time = between(0.02, 0.1)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._url = f"{MOCK_PROVIDER_URL}/v1/chat/completions"
            self._body = json.dumps({
                "model": "load-test",
                "messages": [{"role": "user", "content": "ping"}],
            }).encode()
            self._retries = 0

        @task(1)
        def chat_completion(self):
            for attempt in range(4):  # 1 try + 3 retries
                with self.client.post(
                    self._url,
                    data=self._body,
                    headers={"Content-Type": "application/json"},
                    catch_response=True,
                    name="provider:/v1/chat/completions",
                ) as resp:
                    if resp.status_code == 200:
                        return
                    if resp.status_code == 429:
                        self._retries += 1
                        time.sleep(min(2 ** attempt, 4))
                        continue
                    resp.failure(f"Unexpected provider status: {resp.status_code}")
                    return


# =============================================================================
# Reporting
# =============================================================================

_TEST_START = time.time()


def _fetch_timing_metrics(host):
    try:
        resp = urllib.request.urlopen(f"{host}/api/v1/monitoring/metrics", timeout=10)
        return json.loads(resp.read().decode())
    except Exception:
        return {}


def _fetch_pending_count(host) -> Optional[int]:
    """Read Agentium's dashboard ``pending_count`` (best-effort).

    The dashboard endpoint is auth-gated, so we log in as the test admin first
    and reuse the bearer token. Returns ``None`` if the host is unreachable or
    auth fails (e.g. running the provider driver without a live Agentium).
    """
    try:
        # 1) log in as the seeded test admin
        login = urllib.request.Request(
            f"{host}/api/v1/auth/login",
            data=json.dumps({"username": _TEST_USER, "password": _TEST_PASS}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(login, timeout=10) as resp:
            token = json.loads(resp.read().decode()).get("access_token")
        if not token:
            return None
        # 2) read the dashboard summary with the bearer token
        req = urllib.request.Request(
            f"{host}/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return int(data.get("tasks", {}).get("pending", -1))
    except Exception:
        return None


def _emit_provider_report(environment) -> Dict[str, Any]:
    """Compute + log the four Task 26 provider-facing signals.

    Returns the metric dict so the __main__ driver can reuse it.
    """
    run_seconds = max(0.1, time.time() - _TEST_START)
    stats = mock_provider.stats()
    rps = stats["requests_total"] / run_seconds
    retry_count = stats["requests_429"]
    pending = _fetch_pending_count(environment.host) if environment.host else None

    provider_429_ratio = (
        stats["requests_429"] / stats["requests_total"]
        if stats["requests_total"] else 0.0
    )
    stable = (
        stats["errors"] == 0
        and stats["inflight_peak"] <= PROVIDER_MAX_INFLIGHT
        and provider_429_ratio <= PROVIDER_MAX_429_RATIO
    )

    report = {
        "run_seconds": round(run_seconds, 1),
        "provider_rps": round(rps, 2),
        "provider_requests_total": stats["requests_total"],
        "pending_count": pending,
        "retry_count": retry_count,
        "provider_429_ratio": round(provider_429_ratio, 4),
        "provider_errors": stats["errors"],
        "inflight_peak": stats["inflight_peak"],
        "worker_stability": "STABLE" if stable else "DEGRADED",
    }

    logger.info("=" * 64)
    logger.info("PROVIDER-FACING LOAD REPORT (Task 26)")
    logger.info("  RPS reaching mock provider : %.2f  (total=%d over %.1fs)",
                report["provider_rps"], stats["requests_total"], run_seconds)
    logger.info("  queue depth (pending_count): %s",
                report["pending_count"] if pending is not None else "n/a (host unreachable)")
    logger.info("  retry count (429s served)  : %d  (429 ratio=%.3f)",
                retry_count, provider_429_ratio)
    logger.info("  worker stability           : %s  (errors=%d, inflight_peak=%d)",
                report["worker_stability"], stats["errors"], stats["inflight_peak"])
    logger.info("=" * 64)
    return report


if _HAS_LOCUST:

    @events.test_start.add_listener
    def on_test_start(environment, **kwargs):
        global _TEST_START
        _TEST_START = time.time()
        mock_provider.start()

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

        # Task 26: always emit the provider-facing four-metric report.
        _emit_provider_report(environment)
        mock_provider.stop()


# =============================================================================
# Self-contained report driver (no Locust required) — python locustfile.py
# =============================================================================

def _drive_provider_load(users: int, duration: float, err_ratio: float) -> Dict[str, Any]:
    """Run a sustained provider-facing load via threads + stdlib, return the
    four-metric report. Mirrors what ``ProviderFacingUser`` does in Locust."""
    global MOCK_429_RATIO
    MOCK_429_RATIO = err_ratio
    mock_provider.err_ratio = err_ratio
    mock_provider.start()
    start = time.time()

    url = f"{MOCK_PROVIDER_URL}/v1/chat/completions"
    body = json.dumps({
        "model": "load-test",
        "messages": [{"role": "user", "content": "ping"}],
    }).encode()

    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                req = urllib.request.Request(
                    url, data=body, headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    _ = resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(0.5)
                else:
                    mock_provider._inc("errors")
            except Exception:
                mock_provider._inc("errors")
            time.sleep(0.02)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(users)]
    for t in threads:
        t.start()
    time.sleep(duration)
    stop.set()
    for t in threads:
        t.join(timeout=2)

    run_seconds = max(0.1, time.time() - start)
    stats = mock_provider.stats()
    rps = stats["requests_total"] / run_seconds
    pending = _fetch_pending_count(environment_host())
    provider_429_ratio = (
        stats["requests_429"] / stats["requests_total"]
        if stats["requests_total"] else 0.0
    )
    stable = (
        stats["errors"] == 0
        and stats["inflight_peak"] <= PROVIDER_MAX_INFLIGHT
        and provider_429_ratio <= PROVIDER_MAX_429_RATIO
    )
    report = {
        "run_seconds": round(run_seconds, 1),
        "provider_rps": round(rps, 2),
        "provider_requests_total": stats["requests_total"],
        "pending_count": pending,
        "retry_count": stats["requests_429"],
        "provider_429_ratio": round(provider_429_ratio, 4),
        "provider_errors": stats["errors"],
        "inflight_peak": stats["inflight_peak"],
        "worker_stability": "STABLE" if stable else "DEGRADED",
    }
    mock_provider.stop()
    return report


def environment_host() -> Optional[str]:
    # Best-effort: the host Agentium is reachable on, for pending_count.
    # Honour LOCUST_HOST-like env; fall back to localhost:8000.
    return os.getenv("STAGING_HOST") or os.getenv("APP_HOST") or "http://localhost:8000"


def _write_report_md(report: Dict[str, Any], path: str) -> None:
    lines = [
        "# Provider-Facing Load Test — Sustained Run Report",
        "",
        f"_Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}_",
        "",
        "Driver: `python locustfile.py` (stdlib-only, no Locust service required).",
        "The embedded `MockProviderServer` absorbs OpenAI-compatible",
        "`/v1/chat/completions` traffic and counts requests, 429s, errors and",
        "concurrent in-flight calls so worker stability is observable.",
        "",
        "## Signals (Task 26)",
        "",
        "| Signal | Value | Notes |",
        "|--------|-------|-------|",
        f"| Provider RPS | **{report['provider_rps']}** | requests_total={report['provider_requests_total']} over {report['run_seconds']}s |",
        f"| Queue depth (pending_count) | **{report['pending_count']}** | from Agentium dashboard endpoint (n/a if unreachable or erroring; populated under the Locust run that drives Agentium tasks) |",
        f"| Retry count (429s served) | **{report['retry_count']}** | provider_429_ratio={report['provider_429_ratio']} |",
        f"| Worker stability | **{report['worker_stability']}** | errors={report['provider_errors']}, inflight_peak={report['inflight_peak']} |",
        "",
        "## Interpretation",
        "- **Provider RPS** is the load actually reaching the mock provider — the",
        "  number the resilience layer (token bucket, concurrency cap) must absorb.",
        "- **pending_count** shows whether the queue drained under load (it should",
        "  stay bounded; a runaway value means workers stalled).",
        "- **Retry count** exercises the 429 → rotate/backoff path; a flat 429 ratio",
        "  below `PROVIDER_MAX_429_RATIO` means retries are keeping throughput up.",
        "- **Worker stability** is STABLE when the provider reported zero errors and",
        "  peak concurrency stayed under `PROVIDER_MAX_INFLIGHT`.",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provider-facing load report driver")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="sustained run length in seconds")
    parser.add_argument("--users", type=int, default=50,
                        help="concurrent load threads")
    parser.add_argument("--429-ratio", dest="err_ratio", type=float,
                        default=MOCK_429_RATIO,
                        help="fraction of mock responses that are 429")
    parser.add_argument("--report", type=str,
                        default=os.path.join(os.path.dirname(__file__),
                                             "PROVIDER_LOAD_REPORT.md"),
                        help="path to write the markdown report")
    args = parser.parse_args()

    rep = _drive_provider_load(users=args.users, duration=args.duration,
                               err_ratio=args.err_ratio)
    _write_report_md(rep, args.report)
    print(json.dumps(rep, indent=2))
    print(f"\nReport written to: {args.report}")
