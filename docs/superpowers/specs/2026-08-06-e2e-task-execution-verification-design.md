# 21.1.1 — End-to-End Task Execution Verification Design

## Overview

Implement end-to-end integration tests that verify representative agent task workflows complete without stalling or early termination. Tests cover three core execution paths with their critical failure modes.

## Scope

| In Scope | Out of Scope |
|----------|--------------|
| `AgentOrchestrator.execute_task()` happy path + stall/provider failure | Circuit breaker unit tests (covered elsewhere) |
| `WorkflowExecutor` DAG execution (parallel, context merge, deferred) | Load/stress testing |
| `AgentOrchestrator.delegate_to_task()` with critic review cycles | Frontend/UI tests |
| Pure unit/integration tests with mocking (no external deps) | Real LLM/providers |

---

## Test Architecture

### File Target
**`backend/tests/integration/test_e2e_task_execution.py`** — extend existing file (has fixtures, docstring declares this scope)

### Test Class Structure

```python
class TestExecuteTaskHappyPath:
    """AgentOrchestrator.execute_task() completes successfully."""

class TestExecuteTaskFailureModes:
    """StalledReasoningError retries, provider failover exhaustion."""

class TestWorkflowExecutorDAG:
    """WorkflowExecutor DAG with parallel branches, context merge, deferred tasks."""

class TestDelegateToTaskWithCritics:
    """Critic REJECT→retry, ESCALATE→council, PASS→terminate."""
```

---

## Test Cases

### 1. TestExecuteTaskHappyPath

| Test | Description | Key Assertions |
|------|-------------|----------------|
| `test_agent_executes_task_with_tools_successfully` | Task agent calls registered tools, returns result | `result["content"]` present, `completed_steps` populated, tokens recorded |
| `test_agent_executes_task_without_tools_fallback` | No tools available for tier → plain generation works | Result returned without tool calls |

**Mocking Strategy:**
- `mock_llm_client` returns success dict with `content`, `completed_steps`, token counts
- `ToolCreationService.execute_tool` patched to return `{"status": "success", "data": ...}`

---

### 2. TestExecuteTaskFailureModes

| Test | Description | Key Assertions |
|------|-------------|----------------|
| `test_stalled_reasoning_triggers_ethos_compression_and_retry_max_3` | LLM raises `StalledReasoningError` → ethos compressed → retry (×3) → fail | `agent.compress_ethos()` called, `execution_context["stalled_resume_count"]` increments, 3rd retry raises |
| `test_provider_failover_chain_exhaustion_returns_structured_failure` | All fallback configs exhausted (429/401/outage) → structured error | Result contains `finish_reason="provider_exhausted"`, `fallback_configs` chain attempted |
| `test_circuit_breaker_opens_after_threshold` | 5 consecutive failures → CB opens → 6th request blocked | `orchestrator._check_circuit_breaker()` returns error RouteResult |

**Mocking Strategy:**
- `mock_llm_client.side_effect = [StalledReasoningError(), StalledReasoningError(), StalledReasoningError(), success]`
- For failover: `mock_llm_client.side_effect = [RateLimitError(), AuthError(), ProviderOutageError(), ...]`
- Circuit breaker: Directly call `_update_circuit_breaker(agent_id, success=False)` 5×

---

### 3. TestWorkflowExecutorDAG

| Test | Description | Key Assertions |
|------|-------------|----------------|
| `test_dag_parallel_branches_merge_context_correctly` | Two independent branches run concurrently, results merged into downstream task | `context["branch_a"]` and `context["branch_b"]` both present in downstream params |
| `test_deferred_task_enqueued_with_celery_countdown` | `schedule_offset_days > 0` → Celery `apply_async` with correct countdown | `execute_deferred_subtask.apply_async` called with `countdown = days * 86400` |
| `test_workflow_final_status_completed_with_errors_on_partial_failure` | One subtask fails, others pass → final status = `completed_with_errors` | `WorkflowExecution.status == "completed_with_errors"`, failed task recorded |

**Mocking Strategy:**
- `workflow_tools.execute` patched per-tool (AsyncMock returning expected dict)
- Celery patch: `execute_deferred_subtask.apply_async = MagicMock(return_value=AsyncResult(id="celery-123"))`
- Build `WorkflowPlan` with `SubTaskSpec` objects directly (no API layer)

---

### 4. TestDelegateToTaskWithCritics

| Test | Description | Key Assertions |
|------|-------------|----------------|
| `test_critic_reject_triggers_retry_same_critics` | Critic returns `verdict="reject"` → task retried with same critic instances | `critic_service.review_with_all_task_critics` called again, `retry_count` incremented |
| `test_critic_escalate_triggers_council_escalation` | Critic returns `verdict="escalate"` → `escalate_to_council` called, critics terminated | `critic_service.terminate_critics_for_task(reason="escalated")`, escalation message sent |
| `test_critic_pass_terminates_critics_returns_success` | Critic returns `verdict="pass"` → critics terminated, success RouteResult | `terminate_critics_for_task(reason="task_passed")`, `result.success == True` |

**Mocking Strategy:**
- `critic_service.spawn_critics_for_task` → `AsyncMock(return_value=["critic_output", "critic_plan"])`
- `critic_service.review_with_all_task_critics` → `AsyncMock(return_value={"verdict": "...", "blocking_critic_type": "..."})`
- `critic_service.terminate_critics_for_task` → `AsyncMock()`

---

## Fixtures & Test Data Builders

### Existing Fixtures (reuse)
- `mock_llm_client` — patch `LLMClient.generate_with_tools`
- `mock_checkpoint_write` — patch `checkpoint_write`
- `fake_get_task_db` — patch `task_executor.get_task_db`
- `mock_asyncio_run` — patch `asyncio.run`
- `seeded_db` — SQLAlchemy Session (from conftest)

### New Fixtures (add to file)

```python
@pytest.fixture
def mock_critic_service():
    with patch("backend.services.agent_orchestrator.critic_service") as mock:
        mock.spawn_critics_for_task = AsyncMock(return_value=["output", "plan"])
        mock.review_with_all_task_critics = AsyncMock(return_value={"verdict": "pass"})
        mock.terminate_critics_for_task = AsyncMock()
        mock.DEFAULT_MAX_RETRIES = 3
        yield mock

@pytest.fixture
def mock_celery_workflow_tasks():
    with patch("backend.services.workflow_executor.execute_deferred_subtask") as mock:
        mock.apply_async = MagicMock(return_value=MagicMock(id="celery-test-123"))
        yield mock

@pytest.fixture
def mock_tool_execution():
    with patch("backend.services.tool_creation_service.ToolCreationService.execute_tool") as mock:
        mock.return_value = {"status": "success", "data": {"result": "ok"}}
        yield mock
```

### Test Data Builders (add to file)

```python
def make_task(db: Session, description: str = "Test task", agent_id: str = "3xxxx0001") -> Task:
    task = Task(
        agentium_id=f"TST{uuid.uuid4().hex[:5].upper()}",
        description=description,
        status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        task_type=TaskType.GENERAL,
        assigned_agent_id=agent_id,
        execution_context={},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def make_agent(db: Session, tier: str = "3", agentium_id: str = None) -> Agent:
    aid = agentium_id or f"{tier}xxx{uuid.uuid4().hex[:4]}"
    agent = Agent(
        agentium_id=aid,
        agent_type=AgentType.TASK_AGENT if tier == "3" else AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        is_active=True,
        ethos="Test ethos",
        preferred_config_id="cfg-test",
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent

def make_workflow_plan(subtasks: List[SubTaskSpec]) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id=f"WF{uuid.uuid4().hex[:8]}",
        original_message="Test workflow",
        subtasks=subtasks,
    )

def make_subtask_spec(
    intent: str,
    params: dict = None,
    depends_on: List[str] = None,
    schedule_offset_days: int = 0,
    step_index: int = 0,
) -> SubTaskSpec:
    return SubTaskSpec(
        intent=intent,
        params=params or {},
        depends_on=depends_on or [],
        schedule_offset_days=schedule_offset_days,
        step_index=step_index,
    )
```

---

## Mocking Reference

| Target | Patch Path | Return / Side Effect |
|--------|------------|----------------------|
| LLM generate_with_tools | `backend.core.llm_client.LLMClient.generate_with_tools` | Success dict / `StalledReasoningError` / exceptions |
| Tool execution | `backend.services.tool_creation_service.ToolCreationService.execute_tool` | `{"status": "success", "data": ...}` |
| Critic spawn | `backend.services.critic_agents.critic_service.spawn_critics_for_task` | `List[str]` critic types |
| Critic review | `backend.services.critic_agents.critic_service.review_with_all_task_critics` | `{"verdict": "pass|reject|escalate", "blocking_critic_type": "..."}` |
| Critic terminate | `backend.services.critic_agents.critic_service.terminate_critics_for_task` | `None` |
| Celery deferred | `backend.services.workflow_executor.execute_deferred_subtask.apply_async` | `MagicMock(id="celery-...")` |
| Workflow tools | `backend.services.workflow_tools.execute` | Per-tool AsyncMock |
| API key fallback | `backend.services.api_key_manager.api_key_manager.get_fallback_config_ids` | `List[str]` config IDs |

---

## Success Criteria

1. **All tests pass** in isolation and as a suite (`pytest backend/tests/integration/test_e2e_task_execution.py -v`)
2. **Coverage**: Each happy path + each failure mode has at least one test
3. **No flakiness**: Tests use pure mocking, no timing dependencies, no external services
4. **Documentation**: Each test has docstring explaining the scenario and failure mode

---

## Implementation Order

1. Add new fixtures and test data builders to `test_e2e_task_execution.py`
2. `TestExecuteTaskHappyPath` (2 tests)
3. `TestExecuteTaskFailureModes` (3 tests)
4. `TestWorkflowExecutorDAG` (3 tests)
5. `TestDelegateToTaskWithCritics` (3 tests)
6. Run full suite, fix any import/integration issues

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Circular imports when patching | Patch at module where used (e.g., `backend.services.agent_orchestrator.critic_service`) |
| Async test complexity | Use existing `mock_asyncio_run` fixture + `pytest-asyncio` |
| DB state leakage between tests | Each test gets fresh `seeded_db` session; use `db.rollback()` in teardown if needed |
| Over-mocking hides real bugs | Keep mocks minimal; verify actual method calls with `assert_called_once_with()` |

---

## Self-Review Checklist

- [ ] No TBD/placeholder sections
- [ ] All test cases map to todo_verify.md item 21.1.1
- [ ] Mocking strategy consistent with existing fixtures
- [ ] Test data builders cover all needed entity types
- [ ] Failure modes match code (StalledReasoningError, provider failover, critic verdicts)
- [ ] Scope is focused (no load testing, no UI, no circuit breaker unit tests)