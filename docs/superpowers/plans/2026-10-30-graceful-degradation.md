# Graceful Degradation & Component Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify resilience mechanisms (circuit breakers, cached fallbacks, degraded operation indicators) when LLMs, DB, or search providers fail through comprehensive integration tests and a health degradation endpoint.

**Architecture:** Build test infrastructure (FailureSimulator, inspectors, WebSocket capture) first, then write 8 integration tests covering LLM circuit breaker transitions, failover chains, Retry-After parsing, storage/vector fallbacks, DB pool exhaustion, and health monitor alerts. Add `/api/v1/health/degradation` endpoint for operational observability.

**Tech Stack:** pytest, pytest-asyncio, httpx, sqlalchemy, chromadb, boto3, unittest.mock, FastAPI

## Global Constraints

- All tests must be integration-style (exercise public interfaces, assert observable outcomes)
- No changes to production circuit breaker logic — tests verify existing behavior only
- WebSocket capture via monkey-patch, no test-only code paths in production
- Health endpoint read-only, behind existing auth, exposes no sensitive data
- Follow existing patterns in `tests/conftest.py` for fixtures
- Use `tests/utils/failure_simulator.py` as single source of truth for injection patterns
- All new files under `tests/integration/` and `backend/api/routes/health.py`
- TDD: write failing test first, then minimal implementation, commit per task

---

## File Structure Map

```
backend/
├── api/routes/
│   └── health.py                 # NEW: /health/degradation endpoint (Task 11)
├── services/monitoring/
│   └── health_checks.py          # MODIFIED: enhanced run_health_check (Task 12)
tests/
├── conftest.py                   # MODIFIED: fixtures for FailureSimulator, inspectors, WS capture (Task 1)
├── utils/
│   └── failure_simulator.py      # NEW: Failure injection context managers (Task 1)
├── integration/
│   ├── test_llm_circuit_breaker.py        # Task 2, 3
│   ├── test_llm_failover.py               # Task 4
│   ├── test_llm_retry_after.py            # Task 5
│   ├── test_task_degraded_broadcast.py    # Task 6
│   ├── test_storage_fallback.py           # Task 7
│   ├── test_vector_store_fallback.py      # Task 8
│   ├── test_db_pool_exhaustion.py         # Task 9
│   └── test_health_monitor_alerts.py      # Task 10
```

---

### Task 1: Test Infrastructure — FailureSimulator & Fixtures

**Files:**
- Create: `tests/utils/failure_simulator.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: None (foundational)
- Produces:
  - `failure_simulator` fixture → `FailureSimulator` instance with `.patch_http()`, `.patch_db()`, `.patch_chroma()`, `.patch_s3()` context managers
  - `circuit_breaker_inspector` fixture → `CircuitBreakerInspector` with `.get_state(provider_name)`, `.get_failure_count(provider_name)`, `.get_last_failure(provider_name)`, `.get_half_open_successes(provider_name)`
  - `ws_capture` fixture → `WebSocketEventCapture` with `.captured_events` list, `.wait_for_event(event_type, timeout=5)`, `.clear()`
  - `health_client` fixture → `HealthEndpointClient` with `.get_degradation()` returning parsed JSON

---

- [ ] **Step 1: Write failing tests for FailureSimulator context managers**

```python
# tests/utils/test_failure_simulator.py
import pytest
from tests.utils.failure_simulator import FailureSimulator


class TestFailureSimulator:
    def test_patch_http_restores_on_exit(self):
        import httpx
        original = httpx.AsyncClient.request
        sim = FailureSimulator()
        with sim.patch_http(return_value=httpx.Response(500)):
            assert httpx.AsyncClient.request is not original
        assert httpx.AsyncClient.request is original

    def test_patch_db_restores_on_exit(self):
        from sqlalchemy import Engine
        original = Engine.connect
        sim = FailureSimulator()
        with sim.patch_db(side_effect=Exception("DB down")):
            assert Engine.connect is not original
        assert Engine.connect is original

    def test_patch_chroma_restores_on_exit(self):
        import chromadb
        original = chromadb.HttpClient.__init__
        sim = FailureSimulator()
        with sim.patch_chroma(side_effect=Exception("Chroma down")):
            assert chromadb.HttpClient.__init__ is not original
        assert chromadb.HttpClient.__init__ is original

    def test_patch_s3_restores_on_exit(self):
        import boto3
        original = boto3.client
        sim = FailureSimulator()
        with sim.patch_s3(side_effect=Exception("S3 down")):
            assert boto3.client is not original
        assert boto3.client is original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/utils/test_failure_simulator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.utils.failure_simulator'`

- [ ] **Step 3: Implement FailureSimulator**

```python
# tests/utils/failure_simulator.py
"""Failure injection utilities for integration tests."""
import contextlib
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


class FailureSimulator:
    """Context managers to inject failures at key seams."""

    @contextlib.contextmanager
    def patch_http(
        self,
        *,
        return_value: Optional[httpx.Response] = None,
        side_effect: Optional[Exception] = None,
        status_code: Optional[int] = None,
    ):
        """Patch httpx.AsyncClient.request to return a canned response or raise."""
        if return_value is None and side_effect is None and status_code is not None:
            return_value = httpx.Response(status_code, request=httpx.Request("GET", "http://test"))
        if return_value is None and side_effect is None:
            return_value = httpx.Response(500, request=httpx.Request("GET", "http://test"))

        mock = AsyncMock(return_value=return_value)
        if side_effect:
            mock.side_effect = side_effect

        with patch("httpx.AsyncClient.request", mock):
            yield mock

    @contextlib.contextmanager
    def patch_db(self, *, side_effect: Optional[Exception] = None):
        """Patch sqlalchemy.Engine.connect to raise or return a mock connection."""
        mock = MagicMock()
        if side_effect:
            mock.side_effect = side_effect

        with patch("sqlalchemy.engine.Engine.connect", mock):
            yield mock

    @contextlib.contextmanager
    def patch_chroma(self, *, side_effect: Optional[Exception] = None, return_value: Any = None):
        """Patch chromadb.HttpClient.__init__ to simulate connection failure."""
        mock = MagicMock()
        if side_effect:
            mock.side_effect = side_effect
        elif return_value is not None:
            mock.return_value = return_value

        with patch("chromadb.HttpClient.__init__", mock):
            yield mock

    @contextlib.contextmanager
    def patch_s3(self, *, side_effect: Optional[Exception] = None, return_value: Any = None):
        """Patch boto3.client('s3') to simulate S3 failures."""
        mock_client = MagicMock()
        if side_effect:
            mock_client.side_effect = side_effect
        elif return_value is not None:
            mock_client.return_value = return_value

        def client_factory(service_name, **kwargs):
            if service_name == "s3":
                return mock_client
            import boto3
            return boto3.client(service_name, **kwargs)

        with patch("boto3.client", side_effect=client_factory):
            yield mock_client


class CircuitBreakerInspector:
    """Read-only access to ProviderCircuitBreaker internal state for test assertions."""

    def __init__(self):
        self._breakers = {}

    def register(self, provider_name: str, breaker: Any):
        self._breakers[provider_name] = breaker

    def get_state(self, provider_name: str) -> str:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return breaker.state

    def get_failure_count(self, provider_name: str) -> int:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return breaker.failure_count

    def get_last_failure(self, provider_name: str) -> Optional[float]:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return getattr(breaker, "last_failure_time", None)

    def get_half_open_successes(self, provider_name: str) -> int:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return getattr(breaker, "success_count_in_half_open", 0)


class WebSocketEventCapture:
    """Captures WebSocketManager.broadcast calls for assertion."""

    def __init__(self):
        self.captured_events = []
        self._original_broadcast = None

    def start(self):
        from backend.api.routes.websocket import WebSocketManager
        self._original_broadcast = WebSocketManager.broadcast
        WebSocketManager.broadcast = self._capture_broadcast

    def stop(self):
        if self._original_broadcast:
            from backend.api.routes.websocket import WebSocketManager
            WebSocketManager.broadcast = self._original_broadcast

    async def _capture_broadcast(self, payload: dict):
        self.captured_events.append(payload)
        if self._original_broadcast:
            await self._original_broadcast(payload)

    def wait_for_event(self, event_type: str, timeout: float = 5.0) -> dict:
        import asyncio
        async def _wait():
            import time
            start = time.time()
            while time.time() - start < timeout:
                for event in self.captured_events:
                    if event.get("type") == event_type:
                        return event
                await asyncio.sleep(0.05)
            raise TimeoutError(f"Event {event_type} not captured within {timeout}s")
        return asyncio.run(_wait())

    def clear(self):
        self.captured_events.clear()


class HealthEndpointClient:
    """Test helper to call the degradation health endpoint."""

    def __init__(self, base_url: str = "http://testserver"):
        self.base_url = base_url
        self._client = None

    async def __aenter__(self):
        import httpx
        self._client = httpx.AsyncClient(base_url=self.base_url)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def get_degradation(self) -> dict:
        resp = await self._client.get("/api/v1/health/degradation")
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/utils/test_failure_simulator.py -v`
Expected: PASS

- [ ] **Step 5: Add fixtures to conftest.py**

```python
# tests/conftest.py — ADD to existing file
import pytest
from tests.utils.failure_simulator import (
    FailureSimulator,
    CircuitBreakerInspector,
    WebSocketEventCapture,
    HealthEndpointClient,
)


@pytest.fixture
def failure_simulator():
    return FailureSimulator()


@pytest.fixture
def circuit_breaker_inspector():
    inspector = CircuitBreakerInspector()
    # Auto-register known breakers from llm_client
    try:
        from backend.core.llm_client import llm_client
        for name, breaker in llm_client._circuit_breakers.items():
            inspector.register(name, breaker)
    except Exception:
        pass  # llm_client may not be initialized in all test contexts
    return inspector


@pytest.fixture
def ws_capture():
    capture = WebSocketEventCapture()
    capture.start()
    yield capture
    capture.stop()
    capture.clear()


@pytest.fixture
async def health_client():
    async with HealthEndpointClient() as client:
        yield client
```

- [ ] **Step 6: Run fixture validation test**

```python
# tests/conftest_fixtures_test.py
import pytest


def test_failure_simulator_fixture(failure_simulator):
    assert failure_simulator is not None
    assert hasattr(failure_simulator, "patch_http")
    assert hasattr(failure_simulator, "patch_db")


def test_circuit_breaker_inspector_fixture(circuit_breaker_inspector):
    assert circuit_breaker_inspector is not None
    assert hasattr(circuit_breaker_inspector, "get_state")


def test_ws_capture_fixture(ws_capture):
    assert ws_capture is not None
    assert hasattr(ws_capture, "captured_events")


@pytest.mark.asyncio
async def test_health_client_fixture(health_client):
    assert health_client is not None
    assert hasattr(health_client, "get_degradation")
```

Run: `pytest tests/conftest_fixtures_test.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/utils/failure_simulator.py tests/utils/test_failure_simulator.py tests/conftest.py tests/conftest_fixtures_test.py
git commit -m "test: add FailureSimulator, CircuitBreakerInspector, WebSocketEventCapture, HealthEndpointClient and fixtures"
```

---

### Task 2: LLM Circuit Breaker — CLOSED → OPEN Transition Test

**Files:**
- Create: `tests/integration/test_llm_circuit_breaker.py`

**Interfaces:**
- Consumes: `failure_simulator`, `circuit_breaker_inspector` fixtures (Task 1)
- Produces: Test verifying circuit breaker opens after 5 failures

---

- [ ] **Step 1: Write failing test for CLOSED → OPEN transition**

```python
# tests/integration/test_llm_circuit_breaker.py
import pytest
from backend.core.llm_client import ProviderCircuitBreaker, CircuitOpenError


class TestCircuitBreakerClosedToOpen:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_5_failures(self, failure_simulator, circuit_breaker_inspector):
        """After 5 consecutive failures, circuit should transition to OPEN."""
        from backend.core.llm_client import llm_client
        
        # Get a circuit breaker for a test provider
        breaker = llm_client._circuit_breakers.get("test_provider")
        if not breaker:
            # Create a test breaker with known threshold
            breaker = ProviderCircuitBreaker(failure_threshold=5, recovery_timeout=30)
            llm_client._circuit_breakers["test_provider"] = breaker
            circuit_breaker_inspector.register("test_provider", breaker)
        
        # Reset to known state
        breaker.state = "closed"
        breaker.failure_count = 0
        
        # Simulate 5 failures
        with failure_simulator.patch_http(status_code=500):
            for i in range(5):
                try:
                    await llm_client.generate("test prompt", model="test_provider")
                except Exception:
                    pass
        
        # Assert circuit is OPEN
        assert circuit_breaker_inspector.get_state("test_provider") == "open"
        assert circuit_breaker_inspector.get_failure_count("test_provider") == 5
        
        # Next call should raise CircuitOpenError immediately (no HTTP call)
        with pytest.raises(CircuitOpenError):
            await llm_client.generate("test prompt", model="test_provider")

    @pytest.mark.asyncio
    async def test_circuit_rejects_fast_when_open(self, failure_simulator, circuit_breaker_inspector):
        """When OPEN, calls should fail immediately without HTTP request."""
        from backend.core.llm_client import llm_client
        
        breaker = llm_client._circuit_breakers.get("test_provider")
        breaker.state = "open"
        breaker.failure_count = 5
        
        call_count = 0
        async def counting_mock(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Should not be called")
        
        with failure_simulator.patch_http(side_effect=counting_mock):
            with pytest.raises(CircuitOpenError):
                await llm_client.generate("test", model="test_provider")
        
        assert call_count == 0, "HTTP should not be called when circuit is OPEN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_llm_circuit_breaker.py::TestCircuitBreakerClosedToOpen::test_circuit_opens_after_5_failures -v`
Expected: FAIL — test file doesn't exist or assertions fail

- [ ] **Step 3: Verify implementation exists (should already be in llm_client.py)**

The `ProviderCircuitBreaker` class in `backend/core/llm_client.py` should already have this logic. This test verifies existing behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_llm_circuit_breaker.py::TestCircuitBreakerClosedToOpen -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_llm_circuit_breaker.py
git commit -m "test: add circuit breaker CLOSED to OPEN transition test"
```

---

### Task 3: LLM Circuit Breaker — HALF_OPEN → CLOSED Transition Test

**Files:**
- Modify: `tests/integration/test_llm_circuit_breaker.py`

**Interfaces:**
- Consumes: `failure_simulator`, `circuit_breaker_inspector` fixtures (Task 1)
- Produces: Test verifying HALF_OPEN → CLOSED after 2 successes, HALF_OPEN → OPEN after 1 failure

---

- [ ] **Step 1: Add failing tests for HALF_OPEN transitions**

```python
# ADD to tests/integration/test_llm_circuit_breaker.py
import pytest
import time
from backend.core.llm_client import ProviderCircuitBreaker, CircuitOpenError


class TestCircuitBreakerHalfOpen:
    @pytest.mark.asyncio
    async def test_half_open_to_closed_after_2_successes(self, failure_simulator, circuit_breaker_inspector):
        """After recovery_timeout, circuit enters HALF_OPEN; 2 successes → CLOSED."""
        from backend.core.llm_client import llm_client
        
        breaker = llm_client._circuit_breakers.get("test_provider")
        breaker.state = "open"
        breaker.failure_count = 5
        breaker.last_failure_time = time.time() - 31  # Past recovery_timeout (30s)
        
        # First call should succeed and move to HALF_OPEN
        with failure_simulator.patch_http(status_code=200, return_value=httpx.Response(200, json={"content": "ok"})):
            await llm_client.generate("test", model="test_provider")
        
        assert circuit_breaker_inspector.get_state("test_provider") == "half_open"
        assert circuit_breaker_inspector.get_half_open_successes("test_provider") == 1
        
        # Second success → CLOSED
        with failure_simulator.patch_http(status_code=200, return_value=httpx.Response(200, json={"content": "ok"})):
            await llm_client.generate("test", model="test_provider")
        
        assert circuit_breaker_inspector.get_state("test_provider") == "closed"
        assert circuit_breaker_inspector.get_failure_count("test_provider") == 0
        assert circuit_breaker_inspector.get_half_open_successes("test_provider") == 0

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self, failure_simulator, circuit_breaker_inspector):
        """Failure in HALF_OPEN immediately returns to OPEN."""
        from backend.core.llm_client import llm_client
        
        breaker = llm_client._circuit_breakers.get("test_provider")
        breaker.state = "open"
        breaker.failure_count = 5
        breaker.last_failure_time = time.time() - 31
        
        # First call succeeds → HALF_OPEN
        with failure_simulator.patch_http(status_code=200, return_value=httpx.Response(200, json={"content": "ok"})):
            await llm_client.generate("test", model="test_provider")
        
        assert circuit_breaker_inspector.get_state("test_provider") == "half_open"
        
        # Second call fails → back to OPEN
        with failure_simulator.patch_http(status_code=500):
            with pytest.raises(Exception):
                await llm_client.generate("test", model="test_provider")
        
        assert circuit_breaker_inspector.get_state("test_provider") == "open"
        assert circuit_breaker_inspector.get_failure_count("test_provider") == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_llm_circuit_breaker.py::TestCircuitBreakerHalfOpen -v`
Expected: FAIL

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/integration/test_llm_circuit_breaker.py::TestCircuitBreakerHalfOpen -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_llm_circuit_breaker.py
git commit -m "test: add circuit breaker HALF_OPEN transitions (to CLOSED and back to OPEN)"
```

---

### Task 4: LLM Failover Chain — Primary Exhausted → Fallback Used

**Files:**
- Create: `tests/integration/test_llm_failover.py`

**Interfaces:**
- Consumes: `failure_simulator`, `ws_capture` fixtures (Task 1)
- Produces: Test verifying fallback chain exhausted → task_degraded broadcast

---

- [ ] **Step 1: Write failing test for failover chain exhaustion**

```python
# tests/integration/test_llm_failover.py
import pytest
from backend.services.tasks.task_executor import execute_task
from backend.models.entities.task import Task, TaskStatus, TaskType
from backend.models.entities.agents import Agent, AgentStatus


class TestLLMFailoverChain:
    @pytest.mark.asyncio
    async def test_all_fallbacks_exhausted_emits_task_degraded(self, failure_simulator, ws_capture, db_session):
        """When all 3 fallback providers return 429, task_degraded broadcast fires."""
        # Create test agent
        agent = Agent(
            agentium_id="test-agent-failover",
            name="Test Agent",
            status=AgentStatus.ACTIVE,
            config={"model": "primary", "fallbacks": ["fallback1", "fallback2", "fallback3"]}
        )
        db_session.add(agent)
        
        # Create test task
        task = Task(
            title="Failover Test",
            description="Test task for failover",
            task_type=TaskType.CHAT,
            assigned_agent_id=agent.agentium_id,
            status=TaskStatus.PENDING,
            execution_context={"model": "primary"}
        )
        db_session.add(task)
        db_session.commit()
        
        # Simulate all providers returning 429 (rate limited)
        with failure_simulator.patch_http(status_code=429):
            result = await execute_task(task.id, db_session)
        
        # Verify task marked failed with rate_limited reason
        assert result["status"] == "failed"
        assert result["reason"] == "rate_limited"
        
        # Verify task_degraded broadcast
        degraded_event = ws_capture.wait_for_event("task_degraded", timeout=3)
        assert degraded_event["task_id"] == task.id
        assert degraded_event["reason"] == "rate_limited"
        assert "temporarily unavailable" in degraded_event["message"]

    @pytest.mark.asyncio
    async def test_fallback_success_prevents_degraded(self, failure_simulator, ws_capture, db_session):
        """If fallback succeeds, task completes normally without degraded broadcast."""
        agent = Agent(
            agentium_id="test-agent-fallback-success",
            name="Test Agent",
            status=AgentStatus.ACTIVE,
            config={"model": "primary", "fallbacks": ["fallback1"]}
        )
        db_session.add(agent)
        
        task = Task(
            title="Fallback Success Test",
            description="Test task",
            task_type=TaskType.CHAT,
            assigned_agent_id=agent.agentium_id,
            status=TaskStatus.PENDING,
            execution_context={"model": "primary"}
        )
        db_session.add(task)
        db_session.commit()
        
        # Primary fails, fallback succeeds
        call_count = 0
        async def selective_mock(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 rate limited")
            return httpx.Response(200, json={"content": "fallback worked"})
        
        with failure_simulator.patch_http(side_effect=selective_mock):
            result = await execute_task(task.id, db_session)
        
        assert result["status"] == "completed"
        # No task_degraded event should be captured
        degraded_events = [e for e in ws_capture.captured_events if e.get("type") == "task_degraded"]
        assert len(degraded_events) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_llm_failover.py -v`
Expected: FAIL — test file doesn't exist

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/integration/test_llm_failover.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_llm_failover.py
git commit -m "test: add LLM failover chain exhaustion and success tests"
```

---

### Task 5: LLM Retry-After Header Parsing

**Files:**
- Create: `tests/integration/test_llm_retry_after.py`

**Interfaces:**
- Consumes: `failure_simulator` fixture (Task 1)
- Produces: Test verifying client respects Retry-After header with jitter

---

- [ ] **Step 1: Write failing test for Retry-After parsing**

```python
# tests/integration/test_llm_retry_after.py
import pytest
import time
import httpx
from unittest.mock import AsyncMock, patch


class TestRetryAfterParsing:
    @pytest.mark.asyncio
    async def test_retry_after_header_respected_with_jitter(self, failure_simulator):
        """When server returns Retry-After: 2, client waits ~2s + jitter before retry."""
        from backend.core.llm_client import llm_client
        
        call_times = []
        call_count = 0
        
        async def mock_with_retry_after(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            call_times.append(time.time())
            
            if call_count == 1:
                # First call returns 429 with Retry-After: 2
                resp = httpx.Response(429, headers={"Retry-After": "2"})
                resp.request = httpx.Request("POST", "http://test")
                return resp
            # Second call succeeds
            resp = httpx.Response(200, json={"content": "success"})
            resp.request = httpx.Request("POST", "http://test")
            return resp
        
        with patch("httpx.AsyncClient.request", side_effect=mock_with_retry_after):
            result = await llm_client.generate("test prompt", model="test_retry")
        
        assert result["content"] == "success"
        assert call_count == 2
        
        # Verify wait time: ~2 seconds + jitter (0-0.5s typically)
        elapsed = call_times[1] - call_times[0]
        assert 1.8 <= elapsed <= 3.0, f"Expected wait ~2s + jitter, got {elapsed}s"

    @pytest.mark.asyncio
    async def test_retry_after_seconds_parsed_correctly(self, failure_simulator):
        """Retry-After value in seconds is parsed correctly."""
        from backend.core.llm_client import llm_client
        
        call_times = []
        
        async def mock_with_retry_after_5(*args, **kwargs):
            call_times.append(time.time())
            if len(call_times) == 1:
                resp = httpx.Response(429, headers={"Retry-After": "5"})
                resp.request = httpx.Request("POST", "http://test")
                return resp
            resp = httpx.Response(200, json={"content": "ok"})
            resp.request = httpx.Request("POST", "http://test")
            return resp
        
        with patch("httpx.AsyncClient.request", side_effect=mock_with_retry_after_5):
            await llm_client.generate("test", model="test_retry_5")
        
        elapsed = call_times[1] - call_times[0]
        assert 4.5 <= elapsed <= 6.5, f"Expected wait ~5s + jitter, got {elapsed}s"

    @pytest.mark.asyncio
    async def test_no_retry_after_uses_exponential_backoff(self, failure_simulator):
        """Without Retry-After, exponential backoff with jitter is used."""
        from backend.core.llm_client import llm_client
        
        call_times = []
        call_count = 0
        
        async def mock_no_retry_after(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            call_times.append(time.time())
            
            if call_count < 3:
                resp = httpx.Response(500)
                resp.request = httpx.Request("POST", "http://test")
                return resp
            resp = httpx.Response(200, json={"content": "ok"})
            resp.request = httpx.Request("POST", "http://test")
            return resp
        
        with patch("httpx.AsyncClient.request", side_effect=mock_no_retry_after):
            await llm_client.generate("test", model="test_backoff")
        
        # First retry: ~1s + jitter, second retry: ~2s + jitter
        # Total should be roughly 3-4 seconds
        total_elapsed = call_times[2] - call_times[0]
        assert 2.5 <= total_elapsed <= 6.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_llm_retry_after.py -v`
Expected: FAIL — test file doesn't exist

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/integration/test_llm_retry_after.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_llm_retry_after.py
git commit -m "test: add Retry-After header parsing with jitter tests"
```

---

### Task 6: Task Degraded Broadcast Verification

**Files:**
- Create: `tests/integration/test_task_degraded_broadcast.py`

**Interfaces:**
- Consumes: `failure_simulator`, `ws_capture` fixtures (Task 1)
- Produces: Tests verifying task_degraded broadcast for each exhaustion reason

---

- [ ] **Step 1: Write failing tests for task_degraded broadcast reasons**

```python
# tests/integration/test_task_degraded_broadcast.py
import pytest
from backend.services.tasks.task_executor import execute_task
from backend.models.entities.task import Task, TaskStatus, TaskType
from backend.models.entities.agents import Agent, AgentStatus


class TestTaskDegradedBroadcast:
    @pytest.mark.asyncio
    async def test_all_keys_invalid_reason(self, failure_simulator, ws_capture, db_session):
        """When all API keys invalid, task_degraded broadcasts with reason='all_keys_invalid'."""
        agent = Agent(
            agentium_id="test-agent-keys-invalid",
            name="Test Agent",
            status=AgentStatus.ACTIVE,
            config={"model": "primary", "fallbacks": ["fallback1"]}
        )
        db_session.add(agent)
        
        task = Task(
            title="Keys Invalid Test",
            description="Test",
            task_type=TaskType.CHAT,
            assigned_agent_id=agent.agentium_id,
            status=TaskStatus.PENDING,
            execution_context={"model": "primary"}
        )
        db_session.add(task)
        db_session.commit()
        
        # Simulate 401 Unauthorized (invalid API key)
        with failure_simulator.patch_http(status_code=401):
            result = await execute_task(task.id, db_session)
        
        assert result["status"] == "failed"
        assert result["reason"] == "all_keys_invalid"
        
        degraded = ws_capture.wait_for_event("task_degraded", timeout=3)
        assert degraded["reason"] == "all_keys_invalid"
        assert degraded["task_id"] == task.id

    @pytest.mark.asyncio
    async def test_rate_limited_reason(self, failure_simulator, ws_capture, db_session):
        """When all fallbacks rate limited, task_degraded broadcasts with reason='rate_limited'."""
        agent = Agent(
            agentium_id="test-agent-rate-limited",
            name="Test Agent",
            status=AgentStatus.ACTIVE,
            config={"model": "primary", "fallbacks": ["fallback1", "fallback2", "fallback3"]}
        )
        db_session.add(agent)
        
        task = Task(
            title="Rate Limited Test",
            description="Test",
            task_type=TaskType.CHAT,
            assigned_agent_id=agent.agentium_id,
            status=TaskStatus.PENDING,
            execution_context={"model": "primary"}
        )
        db_session.add(task)
        db_session.commit()
        
        with failure_simulator.patch_http(status_code=429):
            result = await execute_task(task.id, db_session)
        
        assert result["reason"] == "rate_limited"
        
        degraded = ws_capture.wait_for_event("task_degraded", timeout=3)
        assert degraded["reason"] == "rate_limited"

    @pytest.mark.asyncio
    async def test_provider_unreachable_reason(self, failure_simulator, ws_capture, db_session):
        """When all providers unreachable, task_degraded broadcasts with reason='provider_unreachable'."""
        agent = Agent(
            agentium_id="test-agent-unreachable",
            name="Test Agent",
            status=AgentStatus.ACTIVE,
            config={"model": "primary", "fallbacks": ["fallback1"]}
        )
        db_session.add(agent)
        
        task = Task(
            title="Unreachable Test",
            description="Test",
            task_type=TaskType.CHAT,
            assigned_agent_id=agent.agentium_id,
            status=TaskStatus.PENDING,
            execution_context={"model": "primary"}
        )
        db_session.add(task)
        db_session.commit()
        
        # Network error / timeout
        import httpx
        with failure_simulator.patch_http(side_effect=httpx.ConnectError("Connection refused")):
            result = await execute_task(task.id, db_session)
        
        assert result["reason"] == "provider_unreachable"
        
        degraded = ws_capture.wait_for_event("task_degraded", timeout=3)
        assert degraded["reason"] == "provider_unreachable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_task_degraded_broadcast.py -v`
Expected: FAIL — test file doesn't exist

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/integration/test_task_degraded_broadcast.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_task_degraded_broadcast.py
git commit -m "test: add task_degraded broadcast verification for all exhaustion reasons"
```

---

### Task 7: Storage Fallback — S3 to Local

**Files:**
- Create: `tests/integration/test_storage_fallback.py`

**Interfaces:**
- Consumes: `failure_simulator` fixture (Task 1)
- Produces: Test verifying S3 failure falls back to local filesystem

---

- [ ] **Step 1: Write failing test for S3 → Local fallback**

```python
# tests/integration/test_storage_fallback.py
import pytest
from backend.services.storage_service import StorageService, _S3Backend, _LocalBackend
import tempfile
import os


class TestStorageFallback:
    def test_s3_failure_falls_back_to_local(self, failure_simulator, tmp_path):
        """When S3 put_object fails, StorageService uses local backend."""
        # Configure storage to use S3 initially
        service = StorageService()
        service.backend = "s3"
        service.s3_bucket = "test-bucket"
        service.s3_client = None  # Will be created via boto3.client
        
        # Create a test file
        test_content = b"test file content"
        test_path = "test/path/file.txt"
        
        # Simulate S3 failure
        from botocore.exceptions import ClientError
        error_response = {"Error": {"Code": "503", "Message": "Service Unavailable"}}
        with failure_simulator.patch_s3(side_effect=ClientError(error_response, "PutObject")):
            # Should fall back to local
            result = service.upload(test_path, test_content)
        
        # Verify file written locally
        assert result["backend"] == "local"
        local_file = service.local_root / test_path
        assert local_file.exists()
        assert local_file.read_bytes() == test_content

    def test_s3_credentials_error_falls_back(self, failure_simulator, tmp_path):
        """403 credentials error triggers fallback to local."""
        from backend.services.storage_service import StorageService
        from botocore.exceptions import ClientError
        
        service = StorageService()
        service.backend = "s3"
        
        test_content = b"creds test"
        test_path = "creds/test.txt"
        
        error_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
        with failure_simulator.patch_s3(side_effect=ClientError(error_response, "PutObject")):
            result = service.upload(test_path, test_content)
        
        assert result["backend"] == "local"
        assert (service.local_root / test_path).read_bytes() == test_content

    def test_s3_timeout_falls_back(self, failure_simulator, tmp_path):
        """S3 timeout triggers fallback."""
        from backend.services.storage_service import StorageService
        import botocore.exceptions
        
        service = StorageService()
        service.backend = "s3"
        
        test_content = b"timeout test"
        test_path = "timeout/test.txt"
        
        with failure_simulator.patch_s3(side_effect=botocore.exceptions.ReadTimeoutError(
            endpoint_url="https://s3.amazonaws.com", 
            message="Timeout"
        )):
            result = service.upload(test_path, test_content)
        
        assert result["backend"] == "local"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_storage_fallback.py -v`
Expected: FAIL — test file doesn't exist

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/integration/test_storage_fallback.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_storage_fallback.py
git commit -m "test: add storage S3 to local fallback tests"
```

---

### Task 8: Vector Store Fallback — ChromaDB HTTP to PersistentClient

**Files:**
- Create: `tests/integration/test_vector_store_fallback.py`

**Interfaces:**
- Consumes: `failure_simulator` fixture (Task 1)
- Produces: Test verifying ChromaDB HTTP failure falls back to local PersistentClient

---

- [ ] **Step 1: Write failing test for ChromaDB HTTP → PersistentClient fallback**

```python
# tests/integration/test_vector_store_fallback.py
import pytest
from backend.core.vector_store import VectorStore
import tempfile
import httpx


class TestVectorStoreFallback:
    def test_http_timeout_falls_back_to_persistent(self, failure_simulator, tmp_path):
        """When ChromaDB HTTP client times out, falls back to PersistentClient."""
        # Create vector store with HTTP config
        persist_dir = tmp_path / "chroma_data"
        store = VectorStore(
            use_http=True,
            http_host="localhost",
            http_port=8000,
            persist_directory=str(persist_dir)
        )
        
        # Simulate HTTP timeout on query
        with failure_simulator.patch_chroma(side_effect=httpx.TimeoutException("Timeout")):
            # Should fall back to local PersistentClient
            results = store.query("test query", n_results=5)
        
        # Verify fallback worked (local client used)
        assert store._using_local_fallback is True
        assert isinstance(results, list)

    def test_http_connection_error_falls_back(self, failure_simulator, tmp_path):
        """Connection error triggers fallback."""
        from backend.core.vector_store import VectorStore
        import httpx
        
        persist_dir = tmp_path / "chroma_data2"
        store = VectorStore(
            use_http=True,
            http_host="localhost",
            http_port=8000,
            persist_directory=str(persist_dir)
        )
        
        with failure_simulator.patch_chroma(side_effect=httpx.ConnectError("Connection refused")):
            results = store.query("test", n_results=3)
        
        assert store._using_local_fallback is True

    def test_http_500_error_falls_back(self, failure_simulator, tmp_path):
        """5xx error triggers fallback."""
        from backend.core.vector_store import VectorStore
        import chromadb
        
        persist_dir = tmp_path / "chroma_data3"
        store = VectorStore(
            use_http=True,
            http_host="localhost",
            http_port=8000,
            persist_directory=str(persist_dir)
        )
        
        # Mock HTTP client to raise error on query
        def mock_query(*args, **kwargs):
            raise chromadb.errors.ChromaError("HTTP 500")
        
        with failure_simulator.patch_chroma(return_value=type('MockClient', (), {'query': mock_query})()):
            results = store.query("test", n_results=3)
        
        assert store._using_local_fallback is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_vector_store_fallback.py -v`
Expected: FAIL — test file doesn't exist

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/integration/test_vector_store_fallback.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_vector_store_fallback.py
git commit -m "test: add vector store HTTP to PersistentClient fallback tests"
```

---

### Task 9: DB Pool Exhaustion Warning

**Files:**
- Create: `tests/integration/test_db_pool_exhaustion.py`

**Interfaces:**
- Consumes: `failure_simulator`, `ws_capture` fixtures (Task 1)
- Produces: Test verifying system_resource_check broadcasts resource_warning when DB pool exhausted

---

- [ ] **Step 1: Write failing test for DB pool exhaustion alert**

```python
# tests/integration/test_db_pool_exhaustion.py
import pytest
from backend.services.idle_tasks.health_monitor import system_resource_check
from backend.models.entities.agents import Agent, AgentStatus
from unittest.mock import MagicMock, patch


class TestDBPoolExhaustion:
    @pytest.mark.asyncio
    async def test_pool_exhaustion_triggers_resource_warning(self, failure_simulator, ws_capture, db_session):
        """When DB pool checked_out == size, resource_warning broadcast fires."""
        # Create a test agent for the health monitor task
        agent = Agent(
            agentium_id="health-monitor-agent",
            name="Health Monitor",
            status=AgentStatus.ACTIVE
        )
        db_session.add(agent)
        db_session.commit()
        
        # Mock engine pool to report exhaustion
        mock_pool = MagicMock()
        mock_pool.size.return_value = 10
        mock_pool.checkedout.return_value = 10  # 100% utilized
        mock_pool.overflow.return_value = 0
        
        with patch("backend.core.database.engine.pool", mock_pool):
            result = await system_resource_check(db_session, agent)
        
        assert result["status"] == "completed"
        assert "warnings" in result
        assert any("DB pool" in w for w in result["warnings"])
        
        # Verify system_alert broadcast
        alert = ws_capture.wait_for_event("system_alert", timeout=3)
        assert alert["type"] == "resource_warning"
        assert any("DB pool" in w for w in alert["warnings"])
        assert alert["metrics"]["db_pool"]["checked_out"] == 10
        assert alert["metrics"]["db_pool"]["size"] == 10

    @pytest.mark.asyncio
    async def test_pool_under_threshold_no_warning(self, failure_simulator, ws_capture, db_session):
        """Pool at 50% does not trigger warning."""
        agent = Agent(
            agentium_id="health-monitor-agent-2",
            name="Health Monitor 2",
            status=AgentStatus.ACTIVE
        )
        db_session.add(agent)
        db_session.commit()
        
        mock_pool = MagicMock()
        mock_pool.size.return_value = 10
        mock_pool.checkedout.return_value = 5  # 50% utilized
        mock_pool.overflow.return_value = 0
        
        with patch("backend.core.database.engine.pool", mock_pool):
            result = await system_resource_check(db_session, agent)
        
        db_warnings = [w for w in result.get("warnings", []) if "DB pool" in w]
        assert len(db_warnings) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_db_pool_exhaustion.py -v`
Expected: FAIL — test file doesn't exist

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/integration/test_db_pool_exhaustion.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_db_pool_exhaustion.py
git commit -m "test: add DB pool exhaustion resource warning test"
```

---

### Task 10: Health Monitor Alerts — Agent Health, Channel, Anomaly

**Files:**
- Create: `tests/integration/test_health_monitor_alerts.py`

**Interfaces:**
- Consumes: `ws_capture` fixture (Task 1), `db_session`
- Produces: Tests verifying all health monitor alert types broadcast correctly

---

- [ ] **Step 1: Write failing tests for health monitor alert types**

```python
# tests/integration/test_health_monitor_alerts.py
import pytest
from datetime import datetime, timedelta
from backend.services.idle_tasks.health_monitor import (
    agent_health_scan,
    channel_deep_health,
    anomaly_correlation,
    auto_recovery_action,
)
from backend.models.entities.agents import Agent, AgentStatus
from backend.models.entities.channels import ExternalChannel as Channel
from backend.models.entities.task import Task, TaskStatus, TaskType
from unittest.mock import AsyncMock, patch, MagicMock


class TestHealthMonitorAlerts:
    @pytest.mark.asyncio
    async def test_agent_health_scan_detects_stalled_and_crashed(self, ws_capture, db_session):
        """Stalled (>2min) and crashed (>10min) agents trigger agent_health alert."""
        now = datetime.utcnow()
        
        # Active agent with recent heartbeat (healthy)
        healthy = Agent(
            agentium_id="healthy-agent",
            name="Healthy",
            status=AgentStatus.ACTIVE,
            last_heartbeat_at=now - timedelta(seconds=30)
        )
        
        # Stalled agent (>2min, <10min)
        stalled = Agent(
            agentium_id="stalled-agent",
            name="Stalled",
            status=AgentStatus.IDLE_WORKING,
            last_heartbeat_at=now - timedelta(minutes=5)
        )
        
        # Crashed agent (>10min)
        crashed = Agent(
            agentium_id="crashed-agent",
            name="Crashed",
            status=AgentStatus.ACTIVE,
            last_heartbeat_at=now - timedelta(minutes=15)
        )
        
        # No heartbeat ever
        no_heartbeat = Agent(
            agentium_id="no-heartbeat-agent",
            name="No Heartbeat",
            status=AgentStatus.ACTIVE,
            last_heartbeat_at=None
        )
        
        db_session.add_all([healthy, stalled, crashed, no_heartbeat])
        db_session.commit()
        
        agent = Agent(agentium_id="monitor", name="Monitor", status=AgentStatus.ACTIVE)
        db_session.add(agent)
        db_session.commit()
        
        result = await agent_health_scan(db_session, agent)
        
        assert result["scanned"] == 4
        assert len(result["stalled_agents"]) == 1
        assert result["stalled_agents"][0]["agentium_id"] == "stalled-agent"
        assert len(result["crashed_agents"]) == 2
        crashed_ids = {c["agentium_id"] for c in result["crashed_agents"]}
        assert crashed_ids == {"crashed-agent", "no-heartbeat-agent"}
        
        # Verify system_alert broadcast
        alert = ws_capture.wait_for_event("system_alert", timeout=3)
        assert alert["alert_type"] == "agent_health"
        assert len(alert["stalled"]) == 1
        assert len(alert["crashed"]) == 2

    @pytest.mark.asyncio
    async def test_channel_deep_health_detects_unhealthy(self, ws_capture, db_session):
        """Unhealthy channels trigger channel_unhealthy alert."""
        ch1 = Channel(name="slack", channel_type="slack", is_active=True, config={})
        ch2 = Channel(name="discord", channel_type="discord", is_active=True, config={})
        db_session.add_all([ch1, ch2])
        db_session.commit()
        
        agent = Agent(agentium_id="monitor", name="Monitor", status=AgentStatus.ACTIVE)
        db_session.add(agent)
        db_session.commit()
        
        # Mock channel health check: slack healthy, discord timeout
        async def mock_health_check(channel_name, payload, timeout=5):
            if channel_name == "slack":
                return {"status": "ok", "channel": channel_name}
            raise TimeoutError("Discord timeout")
        
        with patch("backend.services.idle_tasks.health_monitor._send_channel_health_check", side_effect=mock_health_check):
            result = await channel_deep_health(db_session, agent)
        
        assert result["checked"] == 2
        assert result["healthy"] == 1
        assert result["unhealthy"] == 1
        assert result["details"][1]["channel"] == "discord"
        assert result["details"][1]["error"] == "timeout"
        
        # Verify alert
        alert = ws_capture.wait_for_event("system_alert", timeout=3)
        assert alert["type"] == "channel_unhealthy"
        assert len(alert["channels"]) == 1
        assert alert["channels"][0]["channel"] == "discord"

    @pytest.mark.asyncio
    async def test_anomaly_correlation_detects_outliers(self, ws_capture, db_session):
        """Isolation forest detects anomalous tasks."""
        # Create 20 normal tasks + 3 anomalous (very long duration)
        base_time = datetime.utcnow() - timedelta(hours=1)
        
        for i in range(20):
            task = Task(
                title=f"Normal Task {i}",
                description="Normal",
                task_type=TaskType.CHAT,
                status=TaskStatus.COMPLETED,
                created_at=base_time + timedelta(minutes=i*3),
                completed_at=base_time + timedelta(minutes=i*3 + 2),
                tokens_used=1000,
            )
            db_session.add(task)
        
        for i in range(3):
            task = Task(
                title=f"Anomalous Task {i}",
                description="Anomalous",
                task_type=TaskType.CHAT,
                status=TaskStatus.COMPLETED,
                created_at=base_time + timedelta(minutes=60 + i*5),
                completed_at=base_time + timedelta(minutes=60 + i*5 + 60),  # 60 min duration
                tokens_used=50000,  # High tokens
            )
            db_session.add(task)
        
        db_session.commit()
        
        agent = Agent(agentium_id="monitor", name="Monitor", status=AgentStatus.ACTIVE)
        db_session.add(agent)
        db_session.commit()
        
        result = await anomaly_correlation(db_session, agent)
        
        assert result["analyzed"] == 23
        assert result["anomalies_found"] >= 1
        
        if result["anomalies_found"] > 0:
            alert = ws_capture.wait_for_event("system_alert", timeout=3)
            assert alert["type"] == "anomaly_detected"
            assert len(alert["anomalies"]) >= 1

    @pytest.mark.asyncio
    async def test_auto_recovery_resets_stuck_agents(self, ws_capture, db_session):
        """Stuck IDLE_WORKING agents reset to ACTIVE."""
        stuck = Agent(
            agentium_id="stuck-agent",
            name="Stuck",
            status=AgentStatus.IDLE_WORKING,
            updated_at=datetime.utcnow() - timedelta(minutes=15)
        )
        db_session.add(stuck)
        db_session.commit()
        
        agent = Agent(agentium_id="monitor", name="Monitor", status=AgentStatus.ACTIVE)
        db_session.add(agent)
        db_session.commit()
        
        result = await auto_recovery_action(db_session, agent)
        
        assert "reset_agent_status:stuck-agent" in result["actions_taken"]
        
        # Verify agent status changed
        db_session.refresh(stuck)
        assert stuck.status == AgentStatus.ACTIVE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_health_monitor_alerts.py -v`
Expected: FAIL — test file doesn't exist

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/integration/test_health_monitor_alerts.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_health_monitor_alerts.py
git commit -m "test: add health monitor alert tests (agent, channel, anomaly, recovery)"
```

---

### Task 11: Health Degradation Endpoint — GET /api/v1/health/degradation

**Files:**
- Create: `backend/api/routes/health.py`
- Modify: `backend/api/routes/__init__.py` (to include health router)

**Interfaces:**
- Consumes: `llm_client._circuit_breakers`, `StorageService`, `VectorStore` (for fallback status)
- Produces: `GET /api/v1/health/degradation` returning circuit breaker states, active fallbacks, provider health, recent alerts

---

- [ ] **Step 1: Write failing test for health degradation endpoint**

```python
# tests/integration/test_health_degradation_endpoint.py
import pytest
from httpx import AsyncClient


class TestHealthDegradationEndpoint:
    @pytest.mark.asyncio
    async def test_degradation_endpoint_returns_circuit_breakers(self, health_client):
        """Endpoint returns circuit breaker states for all providers."""
        result = await health_client.get_degradation()
        
        assert "circuit_breakers" in result
        assert isinstance(result["circuit_breakers"], dict)
        # Should have entries for known providers
        for provider in ["openai", "anthropic", "google"]:
            if provider in result["circuit_breakers"]:
                cb = result["circuit_breakers"][provider]
                assert "state" in cb
                assert cb["state"] in ["closed", "open", "half_open"]
                assert "failures" in cb
                assert isinstance(cb["failures"], int)

    @pytest.mark.asyncio
    async def test_degradation_endpoint_returns_active_fallbacks(self, health_client):
        """Endpoint returns currently active fallback for each domain."""
        result = await health_client.get_degradation()
        
        assert "active_fallbacks" in result
        fallbacks = result["active_fallbacks"]
        assert "storage" in fallbacks
        assert fallbacks["storage"] in ["s3", "local"]
        assert "vector_store" in fallbacks
        assert fallbacks["vector_store"] in ["http", "persistent"]
        assert "llm_provider" in fallbacks

    @pytest.mark.asyncio
    async def test_degradation_endpoint_returns_provider_health(self, health_client):
        """Endpoint returns provider health scores and last errors."""
        result = await health_client.get_degradation()
        
        assert "provider_health" in result
        health = result["provider_health"]
        for provider, info in health.items():
            assert "score" in info
            assert 0.0 <= info["score"] <= 1.0
            assert "last_error" in info

    @pytest.mark.asyncio
    async def test_degradation_endpoint_returns_recent_alerts(self, health_client):
        """Endpoint returns recent system_alert events."""
        result = await health_client.get_degradation()
        
        assert "system_alerts_recent" in result
        assert isinstance(result["system_alerts_recent"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_health_degradation_endpoint.py -v`
Expected: FAIL — endpoint doesn't exist

- [ ] **Step 3: Implement health degradation endpoint**

```python
# backend/api/routes/health.py
"""Health and degradation monitoring endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from datetime import datetime, timedelta

from backend.core.database import get_db
from backend.core.llm_client import llm_client
from backend.services.storage_service import StorageService
from backend.core.vector_store import VectorStore
from backend.models.entities.audit import AuditLog, AuditCategory

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/degradation")
async def get_degradation_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get current system degradation status including circuit breakers, fallbacks, and alerts."""
    
    # Circuit breaker states
    circuit_breakers = {}
    for name, breaker in llm_client._circuit_breakers.items():
        circuit_breakers[name] = {
            "state": breaker.state,
            "failures": breaker.failure_count,
            "last_failure": breaker.last_failure_time.isoformat() if breaker.last_failure_time else None,
            "half_open_successes": getattr(breaker, "success_count_in_half_open", 0),
        }
    
    # Active fallbacks
    storage_service = StorageService()
    vector_store = VectorStore()
    
    active_fallbacks = {
        "storage": "local" if storage_service.backend == "local" else "s3",
        "vector_store": "persistent" if getattr(vector_store, "_using_local_fallback", False) else "http",
        "llm_provider": _get_current_primary_provider(),
    }
    
    # Provider health scores
    provider_health = _calculate_provider_health()
    
    # Recent system alerts (from audit log)
    since = datetime.utcnow() - timedelta(hours=24)
    alerts = db.query(AuditLog).filter(
        AuditLog.category == AuditCategory.SYSTEM,
        AuditLog.created_at >= since,
        AuditLog.action.like("%alert%")
    ).order_by(AuditLog.created_at.desc()).limit(20).all()
    
    system_alerts_recent = [
        {
            "type": a.action.replace("alert_", ""),
            "timestamp": a.created_at.isoformat(),
            "details": a.after_state,
        }
        for a in alerts
    ]
    
    return {
        "circuit_breakers": circuit_breakers,
        "active_fallbacks": active_fallbacks,
        "provider_health": provider_health,
        "system_alerts_recent": system_alerts_recent,
    }


def _get_current_primary_provider() -> str:
    """Determine which LLM provider is currently primary."""
    # Check which provider has a closed circuit breaker
    for name, breaker in llm_client._circuit_breakers.items():
        if breaker.state == "closed":
            return name
    # Fallback to first available
    return next(iter(llm_client._circuit_breakers.keys()), "unknown")


def _calculate_provider_health() -> Dict[str, Dict[str, Any]]:
    """Calculate health score per provider based on circuit breaker state and recent errors."""
    health = {}
    for name, breaker in llm_client._circuit_breakers.items():
        if breaker.state == "closed":
            score = 1.0
        elif breaker.state == "half_open":
            score = 0.5
        else:  # open
            score = 0.0
        
        health[name] = {
            "score": score,
            "last_error": _get_last_provider_error(name),
        }
    return health


def _get_last_provider_error(provider: str) -> str | None:
    """Get last error for a provider from circuit breaker."""
    breaker = llm_client._circuit_breakers.get(provider)
    if breaker and breaker.last_failure_time:
        return f"Last failure at {breaker.last_failure_time.isoformat()}"
    return None
```

```python
# backend/api/routes/__init__.py — ADD to existing imports
from backend.api.routes import health

# In the router inclusion section:
app.include_router(health.router, prefix="/api/v1")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_health_degradation_endpoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/health.py backend/api/routes/__init__.py tests/integration/test_health_degradation_endpoint.py
git commit -m "feat: add GET /api/v1/health/degradation endpoint"
```

---

### Task 12: Enhanced run_health_check Celery Task

**Files:**
- Modify: `backend/services/monitoring/health_checks.py`

**Interfaces:**
- Consumes: `llm_client._circuit_breakers`, `StorageService`, `VectorStore`
- Produces: Enhanced `run_health_check` Celery task returning degradation summary

---

- [ ] **Step 1: Write failing test for enhanced health check**

```python
# tests/integration/test_enhanced_health_check.py
import pytest
from backend.services.monitoring.health_checks import run_health_check
from unittest.mock import patch, MagicMock


class TestEnhancedHealthCheck:
    def test_run_health_check_includes_degradation_summary(self):
        """Enhanced health check returns degradation info alongside basic status."""
        # Mock circuit breakers
        mock_breaker = MagicMock()
        mock_breaker.state = "closed"
        mock_breaker.failure_count = 0
        mock_breaker.last_failure_time = None
        mock_breaker.success_count_in_half_open = 0
        
        with patch("backend.services.monitoring.health_checks.llm_client") as mock_llm:
            mock_llm._circuit_breakers = {"openai": mock_breaker}
            
            with patch("backend.services.monitoring.health_checks.StorageService") as mock_storage:
                mock_storage.return_value.backend = "s3"
                
                with patch("backend.services.monitoring.health_checks.VectorStore") as mock_vector:
                    mock_vector.return_value._using_local_fallback = False
                    
                    result = run_health_check()
        
        assert result["status"] == "healthy"
        assert "degradation" in result
        degradation = result["degradation"]
        assert "circuit_breakers" in degradation
        assert "active_fallbacks" in degradation
        assert "provider_health" in degradation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_enhanced_health_check.py -v`
Expected: FAIL — health_checks.py not yet enhanced

- [ ] **Step 3: Enhance run_health_check task**

```python
# backend/services/monitoring/health_checks.py — REPLACE existing file
"""
Health check tasks.
"""
from backend.celery_app import celery_app
from backend.core.llm_client import llm_client
from backend.services.storage_service import StorageService
from backend.core.vector_store import VectorStore
from backend.services.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def _collect_degradation_status() -> dict:
    """Collect current degradation status for health check."""
    # Circuit breaker states
    circuit_breakers = {}
    for name, breaker in llm_client._circuit_breakers.items():
        circuit_breakers[name] = {
            "state": breaker.state,
            "failures": breaker.failure_count,
            "last_failure": breaker.last_failure_time.isoformat() if breaker.last_failure_time else None,
        }
    
    # Active fallbacks
    storage_service = StorageService()
    vector_store = VectorStore()
    
    active_fallbacks = {
        "storage": "local" if storage_service.backend == "local" else "s3",
        "vector_store": "persistent" if getattr(vector_store, "_using_local_fallback", False) else "http",
    }
    
    # Provider health scores
    provider_health = {}
    for name, breaker in llm_client._circuit_breakers.items():
        if breaker.state == "closed":
            score = 1.0
        elif breaker.state == "half_open":
            score = 0.5
        else:
            score = 0.0
        provider_health[name] = {"score": score}
    
    return {
        "circuit_breakers": circuit_breakers,
        "active_fallbacks": active_fallbacks,
        "provider_health": provider_health,
    }


@celery_app.task(name="agentium.monitoring.health_checks.run_health_check")
def run_health_check():
    """Run system health check with degradation status."""
    logger.info("Running health check")
    
    degradation = _collect_degradation_status()
    
    # Determine overall status
    has_open_circuits = any(cb["state"] == "open" for cb in degradation["circuit_breakers"].values())
    has_local_fallbacks = any(
        v == "local" for v in degradation["active_fallbacks"].values()
    ) or degradation["active_fallbacks"].get("vector_store") == "persistent"
    
    if has_open_circuits or has_local_fallbacks:
        status = "degraded"
    else:
        status = "healthy"
    
    return {
        "status": status,
        "degradation": degradation,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_enhanced_health_check.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/monitoring/health_checks.py tests/integration/test_enhanced_health_check.py
git commit -m "feat: enhance run_health_check with degradation summary"
```

---

### Task 13: CI Integration — GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/resilience-tests.yml`

**Interfaces:**
- Consumes: All test files from Tasks 2-12
- Produces: CI pipeline running resilience tests on every push/PR

---

- [ ] **Step 1: Write GitHub Actions workflow**

```yaml
# .github/workflows/resilience-tests.yml
name: Resilience Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  resilience-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: agentium
          POSTGRES_PASSWORD: agentium
          POSTGRES_DB: agentium_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U agentium"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports: ["6379:6379"]
        options: --health-cmd "redis-cli ping" --health-interval 10s --health-timeout 5s --health-retries 5

      minio:
        image: minio/minio:latest
        command: server /data --console-address ":9001"
        env:
          MINIO_ROOT_USER: minioadmin
          MINIO_ROOT_PASSWORD: minioadmin
        ports: ["9000:9000", "9001:9001"]
        options: --health-cmd "curl -f http://localhost:9000/minio/health/live" --health-interval 10s --health-timeout 5s --health-retries 5

      chromadb:
        image: chromadb/chroma:latest
        ports: ["8000:8000"]
        options: --health-cmd "curl -f http://localhost:8000/api/v1/heartbeat" --health-interval 10s --health-timeout 5s --health-retries 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -e ".[test]"
          pip install pytest-asyncio httpx pytest-mock

      - name: Run database migrations
        run: |
          export DATABASE_URL="postgresql://agentium:agentium@localhost:5432/agentium_test"
          export REDIS_URL="redis://localhost:6379/0"
          export MINIO_ENDPOINT="localhost:9000"
          export MINIO_ACCESS_KEY="minioadmin"
          export MINIO_SECRET_KEY="minioadmin"
          export MINIO_BUCKET="agentium-test"
          export CHROMA_HOST="localhost"
          export CHROMA_PORT="8000"
          alembic upgrade head

      - name: Run resilience integration tests
        run: |
          export DATABASE_URL="postgresql://agentium:agentium@localhost:5432/agentium_test"
          export REDIS_URL="redis://localhost:6379/0"
          export MINIO_ENDPOINT="localhost:9000"
          export MINIO_ACCESS_KEY="minioadmin"
          export MINIO_SECRET_KEY="minioadmin"
          export MINIO_BUCKET="agentium-test"
          export CHROMA_HOST="localhost"
          export CHROMA_PORT="8000"
          pytest tests/integration/ -v --tb=short -x
        timeout-minutes: 20
```

- [ ] **Step 2: Verify workflow syntax**

Run: `gh workflow run resilience-tests.yml` (or push to trigger)
Expected: Workflow runs without syntax errors

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/resilience-tests.yml
git commit -m "ci: add resilience tests GitHub Actions workflow"
```

---

### Task 14: Documentation Update — TODO.md and Design Doc

**Files:**
- Modify: `docs/documents/TODO.md` (mark 21.5.1 complete)
- Verify: `docs/superpowers/specs/2026-10-30-graceful-degradation-design.md` (already exists)

**Interfaces:**
- Consumes: Completed implementation from Tasks 1-13
- Produces: Updated TODO.md with completion marker

---

- [ ] **Step 1: Update TODO.md to mark 21.5.1 complete**

```markdown
# docs/documents/TODO.md — Find line 1017 and update

- [x] 21.5.1 — Graceful Degradation & Component Fallback: Verify resilience mechanisms (circuit breakers, cached fallbacks, degraded operation indicators) when LLMs, DB, or search providers fail. (commit: <commit-hash>)
```

- [ ] **Step 2: Verify design doc is committed**

The design doc at `docs/superpowers/specs/2026-10-30-graceful-degradation-design.md` should already be committed from the brainstorming phase.

- [ ] **Step 3: Run full test suite to verify everything works**

Run: `pytest tests/integration/ -v --tb=short`
Expected: All 10 integration test files pass

- [ ] **Step 4: Final commit**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark TODO 21.5.1 complete - graceful degradation verification"
```

---

## Plan Complete

All 14 tasks defined. This plan covers:

1. **Test Infrastructure** (Task 1) — FailureSimulator, CircuitBreakerInspector, WebSocketEventCapture, HealthEndpointClient, conftest fixtures
2. **LLM Circuit Breaker Tests** (Tasks 2-3) — CLOSED→OPEN, HALF_OPEN→CLOSED/OPEN transitions
3. **LLM Failover & Retry** (Tasks 4-5) — Fallback chain exhaustion, Retry-After header parsing
4. **Task Degraded Broadcast** (Task 6) — All three exhaustion reasons verified
5. **Storage & Vector Fallbacks** (Tasks 7-8) — S3→Local, ChromaDB HTTP→PersistentClient
6. **Health Monitor Alerts** (Tasks 9-10) — DB pool, agent health, channel, anomaly, auto-recovery
7. **Health Degradation Endpoint** (Task 11) — GET /api/v1/health/degradation
8. **Enhanced Celery Health Check** (Task 12) — run_health_check includes degradation summary
9. **CI Integration** (Task 13) — GitHub Actions workflow with all services
10. **Documentation** (Task 14) — TODO.md update, design doc verification

Total estimated effort: ~12 hours across 14 tasks.