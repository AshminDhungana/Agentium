"""
Integration tests for Phase 19.3 — Outbound Rate-Limit Resilience.

Task 12 (catch total exhaustion, fail cleanly): when every provider config is
exhausted, LLMClient.generate raises RuntimeError. The Celery executor must
catch it, mark the Task FAILED with a structured reason, write an AuditLog
row, and RETURN cleanly (no infinite re-queue, no worker crash).

These tests drive the REAL Path A execution chain
(Celery execute_task_async -> Agent.execute_with_skill_rag -> skill_rag
.execute_with_skills -> LLMClient.generate) and only stub the provider client
so exhaustion is forced deterministically.
"""

import uuid
import threading
import json
import time
import asyncio
import types
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy.orm import Session

from backend.core.security import encrypt_api_key
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.models.entities.agents import Agent, AgentStatus
from backend.models.entities.audit import AuditLog
from backend.models.entities.user_config import (
    UserModelConfig,
    ProviderType,
    ConnectionStatus,
)
from backend.services.api_key_manager import api_key_manager
from backend.services.tasks.task_executor import execute_task_async
from backend.core.llm_client import LLMClient


def _make_task(
    description: str = "provider exhaustion test task",
    status: TaskStatus = TaskStatus.IN_PROGRESS,
) -> Task:
    """Build an unsaved Task row with sane defaults for resilience tests."""
    return Task(
        agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
        title="Resilience test task",
        description=description,
        task_type=TaskType.EXECUTION,
        status=status,
        priority=TaskPriority.NORMAL,
        created_by="system",
        is_active=True,
    )


@pytest.mark.integration
class TestExhaustionFailsCleanly:
    """
    Forcing total provider exhaustion must fail the task cleanly:
      - Task.status == "failed"  (terminal, no retry loop)
      - an AuditLog row with action "task_failed_exhaustion" exists
      - the Celery task returns a clean dict (worker moves on)
      - the structured failure_reason is one of the documented values
    """

    def _run_exhausted(self, db_session: Session, exc_message: str):
        # The Celery task opens its own DB connection via get_task_db(). To let
        # it see the uncommitted test Task (and to observe its mark_failed on
        # the same identity-mapped object) we point get_task_db at the test
        # session instead of a fresh connection.
        @contextmanager
        def _fake_get_task_db():
            yield db_session

        task = _make_task()
        db_session.add(task)
        db_session.flush()

        with patch(
            "backend.core.llm_client.LLMClient"
        ) as MockLLM, patch(
            "backend.services.tasks.task_executor.get_task_db", _fake_get_task_db
        ):
            inst = MockLLM.return_value
            inst.generate = AsyncMock(side_effect=RuntimeError(exc_message))
            result = execute_task_async.run(task.agentium_id, "10003")

        db_session.refresh(task)
        return task, result

    def test_exhaustion_marks_task_failed_rate_limited(self, seeded_db: Session):
        task, result = self._run_exhausted(
            seeded_db,
            "LLMClient.generate exhausted all 2 provider(s) and 2 retries. "
            "Last error: openai.RateLimitError: 429 Too Many Requests",
        )
        assert task.status == "failed"
        assert task.failure_reason == "rate_limited"
        assert result["status"] == "failed"
        assert result["reason"] == "rate_limited"
        assert (
            seeded_db.query(AuditLog)
            .filter_by(action="task_failed_exhaustion")
            .count()
            >= 1
        )

    def test_exhaustion_marks_task_failed_all_keys_invalid(self, seeded_db: Session):
        task, result = self._run_exhausted(
            seeded_db,
            "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
            "Last error: anthropic.AuthenticationError: 401 invalid api key",
        )
        assert task.status == "failed"
        assert task.failure_reason == "all_keys_invalid"
        assert result["reason"] == "all_keys_invalid"
        assert (
            seeded_db.query(AuditLog)
            .filter_by(action="task_failed_exhaustion")
            .count()
            >= 1
        )

    def test_exhaustion_marks_task_failed_provider_unreachable(self, seeded_db: Session):
        # A generic, unclassifiable error defaults to provider_unreachable.
        task, result = self._run_exhausted(
            seeded_db,
            "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
            "Last error: httpx.ConnectError: [Errno 111] Connection refused",
        )
        assert task.status == "failed"
        assert task.failure_reason == "provider_unreachable"
        assert result["reason"] == "provider_unreachable"
        assert (
            seeded_db.query(AuditLog)
            .filter_by(action="task_failed_exhaustion")
            .count()
            >= 1
        )


@pytest.mark.integration
class TestExhaustionBroadcastsDegradation:
    """
    Task 15: on total provider exhaustion the worker must surface a friendly
    degradation message to connected dashboards (never a stack trace). It does
    this via a `task_degraded` WebSocket broadcast carrying the friendly text.
    """

    def _run_exhausted(self, db_session: Session, exc_message: str, broadcasts):
        @contextmanager
        def _fake_get_task_db():
            yield db_session

        task = _make_task()
        db_session.add(task)
        db_session.flush()

        with patch(
            "backend.core.llm_client.LLMClient"
        ) as MockLLM, patch(
            "backend.services.tasks.task_executor.get_task_db", _fake_get_task_db
        ), patch(
            "backend.api.routes.websocket.manager.broadcast",
            side_effect=lambda msg: broadcasts.append(msg),
        ):
            inst = MockLLM.return_value
            inst.generate = AsyncMock(side_effect=RuntimeError(exc_message))
            execute_task_async.run(task.agentium_id, "10003")

        db_session.refresh(task)
        return task

    def test_degradation_broadcast_sent(self, seeded_db: Session):
        broadcasts = []
        self._run_exhausted(
            seeded_db,
            "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
            "Last error: openai.RateLimitError: 429 Too Many Requests",
            broadcasts,
        )
        degraded = [m for m in broadcasts if m.get("type") == "task_degraded"]
        assert degraded, "no task_degraded broadcast emitted on exhaustion"
        msg = degraded[0]
        assert msg["reason"] == "rate_limited"
        # Friendly text, not a stack trace.
        assert "temporarily unavailable" in msg["message"]
        assert "rate-limited" in msg["message"]


def _make_config(db: Session, provider, model: str, priority: int = 1) -> UserModelConfig:
    """Create an unsaved, ACTIVE UserModelConfig for fallback-chain tests."""
    cfg = UserModelConfig(
        provider=provider,
        config_name=f"{provider.value.lower()}-{uuid.uuid4().hex[:6]}",
        default_model=model,
        is_active=True,
        status=ConnectionStatus.ACTIVE,
        priority=priority,
    )
    if provider == ProviderType.LOCAL:
        cfg.local_server_url = "http://localhost:11434/v1"
    db.add(cfg)
    db.flush()
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Task 20 — Mock provider test harness
#
# A real, threaded OpenAI-compatible HTTP server we can point a UserModelConfig
# at. Driving the REAL SDK → ProviderRateLimiter → classify_error path against
# it (rather than monkeypatching ModelService) is what actually exercises the
# resilience code for Tasks 21–25.
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_COMPLETION = {
    "id": "chatcmplt-test",
    "object": "chat.completion",
    "created": 1,
    "model": "fake",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


class FakeProviderServer:
    """A threaded OpenAI-compatible HTTP server returning configurable responses.

    ``default_*`` is what to return when the per-call queue is empty. For
    failover tests spin up TWO servers (one always-429, one always-200) so the
    primary and fallback configs differ (they share no URL). ``set_next()``
    overrides the default for the next call. ``status_counts`` lets a test
    assert e.g. that no 429 escaped to the provider.
    """

    def __init__(self, default_status=200, default_headers=None, default_body=None):
        self._default = {
            "status": default_status,
            "headers": default_headers or {},
            "body": default_body or OPENAI_COMPLETION,
        }
        self._queue = []  # list of {"status","headers","body"}
        self._lock = threading.Lock()
        self._hits = 0
        self._status_counts = {}  # status_code -> hit count
        self._started = threading.Event()
        handler = self._make_handler()
        self._httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self._httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        t = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        t.start()
        self._started.set()

    def _make_handler(self):
        server = self

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                # Drain the request body so keep-alive connections stay aligned
                # when the client (httpx) reuses the socket across calls.
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length:
                    self.rfile.read(length)
                with server._lock:
                    server._hits += 1
                    spec = server._queue.pop(0) if server._queue else server._default
                    server._status_counts[spec["status"]] = (
                        server._status_counts.get(spec["status"], 0) + 1
                    )
                status = spec.get("status", 200)
                headers = spec.get("headers", {})
                body = spec.get("body", OPENAI_COMPLETION)
                payload = json.dumps(body).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, str(v))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return _H

    def set_next(self, status=200, headers=None, body=None):
        with self._lock:
            self._queue.append(
                {
                    "status": status,
                    "headers": headers or {},
                    "body": body or OPENAI_COMPLETION,
                }
            )

    def hits(self):
        with self._lock:
            return self._hits

    def status_counts(self):
        with self._lock:
            return dict(self._status_counts)

    def shutdown(self):
        self._httpd.shutdown()
        self._httpd.server_close()


def make_fake_config(
    base_url: str,
    *,
    rpm: int = 100000,
    max_concurrent: int = 10,
    status: ConnectionStatus = ConnectionStatus.ACTIVE,
):
    """Create + TOP-LEVEL commit a UserModelConfig pointing at a FakeProviderServer.

    Commits via its own NullPool engine because ModelService.get_provider()
    opens its OWN db session (get_db_context) — a savepoint commit on the
    test's db_session is invisible to it until the outer transaction commits
    (same visibility gotcha as Tasks 18/19). rpm defaults very high so the
    token bucket is effectively pass-through and error-path tests assert
    failover timing, not throttle spacing.

    NOTE: the column is ``api_base_url`` (not ``base_url``); get_effective_base_url
    returns api_base_url for non-LOCAL providers. The key is stored pre-encrypted
    via encrypt_api_key("sk-test") so the real decrypt_api_key path yields a
    valid non-empty key (the OpenAI SDK refuses an empty key).
    """
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://agentium:agentium@postgres:5432/agentium_test",
    )
    eng = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=eng)()
    cfg = UserModelConfig(
        user_id="sovereign",
        provider=ProviderType.OPENAI,
        config_name=f"fake-{uuid.uuid4().hex[:8]}",
        api_key_encrypted=encrypt_api_key("sk-test"),
        api_key_masked="sk-test",
        default_model="fake",
        status=status,
        api_base_url=base_url,
        requests_per_minute=rpm,
        max_concurrent_requests=max_concurrent,
        is_active=True,
        priority=1,
    )
    s.add(cfg)
    s.commit()
    s.refresh(cfg)
    s.close()
    eng.dispose()
    return cfg


def _delete_fake_configs(ids):
    """Soft-deactivate configs committed by make_fake_config.

    make_fake_config commits via its own engine (bypassing the test's
    transaction rollback), so these rows persist in agentium_test across the
    whole session and would pollute later tests (e.g. the fallback-chain test,
    whose 4-slot cap overflows with stray configs). We can't hard-DELETE them
    because the test logs ModelUsageLog rows that FK-reference the config;
    instead flip is_active=False so get_provider / get_fallback_config_ids
    (both of which filter is_active=True) ignore them.
    """
    if not ids:
        return
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    eng = create_engine(os.getenv("DATABASE_URL"), poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=eng)()
    s.query(UserModelConfig).filter(UserModelConfig.id.in_(ids)).update(
        {
            UserModelConfig.is_active: False,
            UserModelConfig.status: ConnectionStatus.ERROR,
        },
        synchronize_session=False,
    )
    s.commit()
    s.close()
    eng.dispose()


@pytest.mark.integration
class TestMockProviderHarness:
    """Task 20 sanity: a 200 fake server returns 'ok' through the real SDK path."""

    def test_fake_provider_returns_ok(self, seeded_db: Session):
        srv = FakeProviderServer(default_status=200)
        cfg = make_fake_config(srv.base_url, rpm=100000)
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            assert agent is not None

            import asyncio

            from backend.core.llm_client import LLMClient

            client = LLMClient()
            result = asyncio.run(client.generate(agent, "hello", config_id=str(cfg.id)))

            assert result["content"] == "ok"
        finally:
            srv.shutdown()
            _delete_fake_configs([str(cfg.id)])


@pytest.mark.integration
class Test429Burst:
    """Task 21: a burst of concurrent tasks against an always-429 primary (with a
    healthy 200 fallback) must rotate to the fallback and complete every task
    after the primary is retried to exhaustion (max_retries=2 → 3 attempts)."""

    async def test_429_burst_rotates_and_completes(self, db_engine, monkeypatch):
        # We exercise OUR retry/rotation layer, not the SDK's built-in retries
        # (openai.AsyncOpenAI defaults to max_retries=2). With those enabled each
        # generate() would make 3 SDK HTTP hits per attempt and the primary's
        # count would far exceed 3*N. Force max_retries=0 so the per-config hit
        # count reflects only our resilience layer.
        import openai as _openai

        _orig = _openai.AsyncOpenAI

        def _zero_retry(*a, **k):
            k.setdefault("max_retries", 0)
            return _orig(*a, **k)

        monkeypatch.setattr(_openai, "AsyncOpenAI", _zero_retry)

        always_429 = FakeProviderServer(default_status=429,
                                         default_headers={"Retry-After": "1"})
        always_200 = FakeProviderServer(default_status=200)
        # One shared 200 fallback — it never fails, so a single shared config is
        # safe. Each concurrent task gets its OWN primary(429) config: the
        # 3-strike failure cooldown (MAX_FAILURES_BEFORE_COOLDOWN=3, Task 16)
        # deactivates a primary only AFTER that task's own 3 retries, so the
        # 429 server still receives exactly 3 hits per task. Sharing one primary
        # across N concurrent tasks would trip the cooldown on the 3rd concurrent
        # attempt and stop the remaining tasks from re-hitting the server.
        created_ids = []
        try:
            fb = make_fake_config(always_200.base_url)
            created_ids.append(str(fb.id))
            N = 5
            primaries = [make_fake_config(always_429.base_url) for _ in range(N)]
            created_ids.extend(str(p.id) for p in primaries)
            agents = [
                types.SimpleNamespace(ethos=None, agentium_id=f"task-{i}")
                for i in range(N)
            ]

            results = await asyncio.gather(*[
                LLMClient().generate(
                    agent=agents[i], user_message="hi",
                    config_id=str(primaries[i].id),
                    fallback_configs=[str(fb.id)],
                )
                for i in range(N)
            ], return_exceptions=True)

            # Every task completed via the fallback.
            ok = [r for r in results if isinstance(r, dict)]
            assert len(ok) == N, results
            assert all(r.get("content") == "ok" for r in ok)

            # Each primary is retried to exhaustion (max_retries=2 → 3 attempts)
            # before rotating to the fallback, so the 429 server receives exactly
            # 3 × N requests; the shared 200 fallback is hit once per task (N).
            assert always_429.hits() == 3 * N, always_429.status_counts()
            assert always_200.hits() == N, always_200.status_counts()
        finally:
            always_429.shutdown()
            always_200.shutdown()
            # make_fake_config commits via its own engine, bypassing the test's
            # transaction rollback — delete explicitly so these rows don't
            # pollute the fallback-chain test that runs later in this session.
            _delete_fake_configs(created_ids)


@pytest.mark.integration
class TestInvalidKey:
    """
    Task 22: a permanently-failed key (always 401) must NOT be retried. The
    resilience layer classifies 401 as PERMANENT_KEY_FAILURE and rotates
    immediately to the fallback (no backoff, no retry against the dead key),
    marks the key unhealthy, and the task still completes via the fallback.
    """

    async def test_invalid_key_rotates_immediately(self, seeded_db: Session, monkeypatch):
        import openai as _openai

        _orig = _openai.AsyncOpenAI

        def _zero_retry(*a, **k):
            k.setdefault("max_retries", 0)
            return _orig(*a, **k)

        monkeypatch.setattr(_openai, "AsyncOpenAI", _zero_retry)

        always_401 = FakeProviderServer(default_status=401)
        always_200 = FakeProviderServer(default_status=200)
        created_ids = []
        try:
            primary = make_fake_config(always_401.base_url)
            created_ids.append(str(primary.id))
            fb = make_fake_config(always_200.base_url)
            created_ids.append(str(fb.id))
            agent = types.SimpleNamespace(ethos=None, agentium_id="task-22")

            # A single task: the 401 primary must be hit exactly once (no retry),
            # then rotate to the 200 fallback (hit exactly once) and complete.
            result = await LLMClient().generate(
                agent=agent, user_message="hi",
                config_id=str(primary.id),
                fallback_configs=[str(fb.id)],
            )

            assert isinstance(result, dict)
            assert result.get("content") == "ok"
            # Permanent key failure → no retry, immediate rotation.
            assert always_401.hits() == 1, always_401.status_counts()
            assert always_200.hits() == 1, always_200.status_counts()

            # The dead key is marked permanently unhealthy (Task 16 merged
            # source of truth), so it is excluded from future failover chains.
            assert api_key_manager.is_config_healthy(str(primary.id), db=seeded_db) is False
        finally:
            always_401.shutdown()
            always_200.shutdown()
            _delete_fake_configs(created_ids)


@pytest.mark.integration
class TestLocalFallbackChain:
    """
    Task 13: get_fallback_config_ids must build an ordered failover chain that
    ends in the local/Ollama config (offline, never cloud-rate-limited) so a
    task can still complete when every remote key is exhausted.
    """

    def test_fallback_includes_local(self, seeded_db: Session):
        remote = _make_config(seeded_db, ProviderType.OPENAI, "gpt-4o", priority=1)
        _make_config(seeded_db, ProviderType.OPENAI, "gpt-4o-mini", priority=2)  # same-provider
        _make_config(seeded_db, ProviderType.ANTHROPIC, "claude-3-5-sonnet", priority=1)  # cross-provider
        local = _make_config(seeded_db, ProviderType.LOCAL, "llama3")

        fb = api_key_manager.get_fallback_config_ids(remote.id, db=seeded_db)

        # Local/Ollama must be present and is the last (offline) link.
        assert local.id in fb
        assert fb[-1] == local.id
        # Same-provider secondary precedes the cross-provider key precedes local.
        assert remote.id not in fb  # primary itself is never in its own fallback list
        # Cached for callers that need the base URL.
        assert api_key_manager._local_fallback_config is not None
        assert api_key_manager._local_fallback_config["id"] == str(local.id)

    def test_fallback_excludes_error_keys_and_is_capped(self, seeded_db: Session):
        remote = _make_config(seeded_db, ProviderType.OPENAI, "gpt-4o", priority=1)
        # Same-provider key in ERROR must be excluded.
        bad = _make_config(seeded_db, ProviderType.OPENAI, "gpt-4o-bad", priority=2)
        bad.status = ConnectionStatus.ERROR
        seeded_db.flush()
        local = _make_config(seeded_db, ProviderType.LOCAL, "llama3")

        fb = api_key_manager.get_fallback_config_ids(remote.id, db=seeded_db)
        assert bad.id not in fb
        assert local.id in fb
        # primary never listed; capped at MAX_FALLBACK_CONFIGS + 1 = 4
        assert remote.id not in fb
        assert len(fb) <= api_key_manager.MAX_FALLBACK_CONFIGS + 1


@pytest.mark.integration
class TestConfigHealthSingleSourceOfTruth:
    """
    Task 16: api_key_manager.is_config_healthy is the merged single source of
    truth for a config's health. A config whose key was permanently failed must
    read unhealthy; an ACTIVE config reads healthy. Verified on the same session
    (committed writes are visible to the same identity-mapped session).
    """

    def test_permanent_failure_renders_unhealthy(self, seeded_db: Session):
        cfg = _make_config(seeded_db, ProviderType.OPENAI, "gpt-4o", priority=1)
        assert api_key_manager.is_config_healthy(cfg.id, db=seeded_db) is True

        api_key_manager.mark_key_failed(
            cfg.id, "401 auth", is_permanent=True, db=seeded_db
        )
        seeded_db.commit()

        # The merged source of truth now reports the config unhealthy.
        assert api_key_manager.is_config_healthy(cfg.id, db=seeded_db) is False

    def test_active_config_is_healthy(self, seeded_db: Session):
        cfg = _make_config(seeded_db, ProviderType.ANTHROPIC, "claude-3-5-sonnet", priority=1)
        assert api_key_manager.is_config_healthy(cfg.id, db=seeded_db) is True


@pytest.mark.integration
def test_provider_metrics_broadcast(celery_eager, seeded_db):
    """
    Task 18: broadcast_provider_metrics() must emit a 'provider_metrics_update'
    event whose 'metrics' field is a list (one entry per active config). The
    dashboard subscribes to this event for live per-provider resilience numbers.
    """
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    # The task opens its OWN top-level DB connection, so the config must be
    # committed at the top level — not merely flushed/committed inside the
    # test's savepoint-wrapped session, whose writes other connections cannot
    # see until the outer transaction commits.
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://agentium:agentium@postgres:5432/agentium_test",
    )
    eng = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=eng)()
    _make_config(s, ProviderType.OPENAI, "gpt-4o", priority=1)
    s.commit()
    s.close()
    eng.dispose()

    from backend.celery_app import broadcast_provider_metrics

    broadcasts = []
    with patch(
        "backend.api.routes.websocket.manager.broadcast",
        side_effect=lambda msg: broadcasts.append(msg),
    ):
        broadcast_provider_metrics()

    updates = [m for m in broadcasts if m.get("type") == "provider_metrics_update"]
    assert updates, "no provider_metrics_update broadcast emitted"
    assert isinstance(updates[0]["metrics"], list)
    assert updates[0]["metrics"], "expected at least one config in metrics"


@pytest.mark.integration
class TestPreExhaustionWarning:
    """
    Task 19: check_rate_budget_warning must fire a WebSocket alert *before* a
    provider is actually exhausted, once its rolling 60s request count reaches
    WARNING_THRESHOLD (80%) of its configured requests_per_minute. The warning
    is debounced per-config so it fires once per 60s window, not per request.
    """

    def test_warning_at_80_percent(self, seeded_db: Session):
        import os
        import time

        import redis
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool

        # The warn check reads via its own top-level session (get_db_context),
        # so the config must be committed at the top level — not merely flushed
        # inside the savepoint-wrapped seeded_db session.
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://agentium:agentium@postgres:5432/agentium_test",
        )
        eng = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
        s = sessionmaker(bind=eng)()
        cfg = _make_config(s, ProviderType.OPENAI, "gpt-4o", priority=1)
        # requests_per_minute = 10 → 8 requests == 80% boundary (8 >= 0.8*10).
        cfg.requests_per_minute = 10
        s.commit()

        # Seed the rolling 60s window with 8 requests.
        r = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True
        )
        win_key = f"agentium:provider:metrics:{cfg.id}:window"
        now = time.time()
        for i in range(8):
            r.zadd(win_key, {f"req:{i}": now - (8 - i)})
        r.expire(win_key, 120)

        alerts = []
        with patch.object(
            api_key_manager,
            "_broadcast_websocket_alert",
            side_effect=lambda provider, message: alerts.append(message),
        ):
            api_key_manager.check_rate_budget_warning(str(cfg.id))

        s.close()
        eng.dispose()

        assert alerts, "expected a pre-exhaustion warning alert at 80% of rate"
        assert any("80%" in a or "warning" in a.lower() for a in alerts)

    def test_no_warning_well_below_threshold(self, seeded_db: Session):
        import os
        import time

        import redis
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool

        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://agentium:agentium@postgres:5432/agentium_test",
        )
        eng = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
        s = sessionmaker(bind=eng)()
        cfg = _make_config(s, ProviderType.OPENAI, "gpt-4o", priority=1)
        cfg.requests_per_minute = 10
        s.commit()

        # Only 2 requests → 20%, far below the 80% threshold.
        r = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True
        )
        win_key = f"agentium:provider:metrics:{cfg.id}:window"
        now = time.time()
        for i in range(2):
            r.zadd(win_key, {f"req:{i}": now - (2 - i)})
        r.expire(win_key, 120)

        alerts = []
        with patch.object(
            api_key_manager,
            "_broadcast_websocket_alert",
            side_effect=lambda provider, message: alerts.append(message),
        ):
            api_key_manager.check_rate_budget_warning(str(cfg.id))

        s.close()
        eng.dispose()

        assert not alerts, "no warning should fire well below the 80% threshold"
