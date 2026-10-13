"""
Integration Tests — Workflow Execution  (Phase 18.2)
====================================================

Covers:
  18.2.1 — WorkflowExecutor runs DAG steps in correct order
  18.2.2 — Parallel branches execute concurrently
  18.2.3 — Step dependencies are respected
  18.2.4 — Workflow failure at one step handles rollback/retry
  18.2.5 — Celery workflow_tasks.py processes workflows asynchronously

All tests mock ``workflow_tools.execute`` so that no external service
(stock API, email, etc.) is required.  The ``db_session`` fixture provides
transactional isolation; every test rolls back automatically.
"""

import asyncio
import uuid
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.entities.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowSubTask,
    WorkflowStep,
    WorkflowStepType,
    WorkflowExecutionStatus,
)
from backend.services.workflow_executor import WorkflowExecutor
from backend.services.workflow_planner import WorkflowPlan, SubTaskSpec
from backend.services.workflow_engine import WorkflowEngine

pytestmark = pytest.mark.integration


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_workflow(db_session, name: str = None) -> Workflow:
    """Create a minimal Workflow row in the DB and return it."""
    wf = Workflow(
        name=name or f"wf-{uuid.uuid4().hex[:8]}",
        template_json={"steps": []},
        version=1,
    )
    db_session.add(wf)
    db_session.flush()
    return wf


def _make_plan(
    workflow_id: str,
    subtasks: list[SubTaskSpec],
    message: str = "test plan",
) -> WorkflowPlan:
    """Build a WorkflowPlan from a list of SubTaskSpec."""
    for i, st in enumerate(subtasks):
        st.step_index = i
    return WorkflowPlan(
        workflow_id=workflow_id,
        original_message=message,
        subtasks=subtasks,
    )


def _mock_tool(return_value: dict = None, side_effect=None) -> AsyncMock:
    """Create an AsyncMock for workflow_tools.execute."""
    mock = AsyncMock()
    if side_effect is not None:
        mock.side_effect = side_effect
    elif return_value is not None:
        mock.return_value = return_value
    else:
        mock.return_value = {"ok": True}
    return mock


# ==========================================================================
# 18.2.1 — WorkflowExecutor runs DAG steps in correct order
# ==========================================================================

class TestDAGOrdering_18_2_1:
    """WorkflowExecutor must run tasks in topological (dependency) order."""

    @pytest.mark.asyncio
    async def test_single_task_completes(self, db_session):
        """Simplest case: one task with no deps completes successfully."""
        wf = _create_workflow(db_session)
        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="only_task", params={"x": 1}),
        ])

        mock_exec = _mock_tool({"result": "done"})
        with patch("backend.services.workflow_tools.execute", mock_exec):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution is not None
        assert execution.status == "completed"
        mock_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_linear_chain_runs_in_order(self, db_session):
        """A→B→C chain: each step should run only after its predecessor."""
        wf = _create_workflow(db_session)

        call_order = []

        async def _track_order(name, params, context=None):
            call_order.append(name)
            return {"intent": name, "done": True}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="step_a", params={}),
            SubTaskSpec(intent="step_b", params={}, depends_on=["step_a"]),
            SubTaskSpec(intent="step_c", params={}, depends_on=["step_b"]),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_track_order):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        assert call_order == ["step_a", "step_b", "step_c"]

    @pytest.mark.asyncio
    async def test_final_status_completed_when_all_succeed(self, db_session):
        """Final workflow status must be 'completed' when every task succeeds."""
        wf = _create_workflow(db_session)
        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="task_1", params={}),
            SubTaskSpec(intent="task_2", params={}, depends_on=["task_1"]),
        ])

        mock_exec = _mock_tool({"ok": True})
        with patch("backend.services.workflow_tools.execute", mock_exec):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        assert execution.completed_at is not None

    @pytest.mark.asyncio
    async def test_subtask_rows_created_in_db(self, db_session):
        """_persist_plan should create WorkflowSubTask rows for every subtask."""
        wf = _create_workflow(db_session)
        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="alpha", params={"a": 1}),
            SubTaskSpec(intent="beta", params={"b": 2}, depends_on=["alpha"]),
        ])

        mock_exec = _mock_tool({"ok": True})
        with patch("backend.services.workflow_tools.execute", mock_exec):
            executor = WorkflowExecutor()
            await executor.execute(plan, created_by="test", db_session=db_session)

        subs = db_session.query(WorkflowSubTask).filter_by(workflow_id=wf.id).all()
        assert len(subs) == 2
        intents = {s.intent for s in subs}
        assert intents == {"alpha", "beta"}

    @pytest.mark.asyncio
    async def test_context_flows_downstream(self, db_session):
        """Upstream task output should be merged into downstream task params."""
        wf = _create_workflow(db_session)

        received_contexts = {}

        async def _capture_context(name, params, context=None):
            received_contexts[name] = dict(context or {})
            return {"from": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="producer", params={}),
            SubTaskSpec(intent="consumer", params={}, depends_on=["producer"]),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_capture_context):
            executor = WorkflowExecutor()
            await executor.execute(plan, created_by="test", db_session=db_session)

        # consumer should have received producer's output in context
        assert "producer" in received_contexts["consumer"]
        assert received_contexts["consumer"]["producer"] == {"from": "producer"}


# ==========================================================================
# 18.2.2 — Parallel branches execute concurrently
# ==========================================================================

class TestParallelBranches_18_2_2:
    """Independent tasks with no deps must execute concurrently."""

    @pytest.mark.asyncio
    async def test_independent_tasks_run_concurrently(self, db_session):
        """Two tasks with no deps should both run in the first round."""
        wf = _create_workflow(db_session)

        call_order = []

        async def _track(name, params, context=None):
            call_order.append(name)
            return {"intent": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="branch_a", params={}),
            SubTaskSpec(intent="branch_b", params={}),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_track):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        # Both should have been called (order may vary within gather)
        assert set(call_order) == {"branch_a", "branch_b"}

    @pytest.mark.asyncio
    async def test_fork_join_pattern(self, db_session):
        """A, B (no deps) then C (depends on A and B) — classic fork-join."""
        wf = _create_workflow(db_session)

        call_order = []

        async def _track(name, params, context=None):
            call_order.append(name)
            return {"intent": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="fork_a", params={}),
            SubTaskSpec(intent="fork_b", params={}),
            SubTaskSpec(intent="join_c", params={}, depends_on=["fork_a", "fork_b"]),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_track):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        # join_c must be last
        assert call_order[-1] == "join_c"
        # fork_a and fork_b must both run before join_c
        assert set(call_order[:2]) == {"fork_a", "fork_b"}

    @pytest.mark.asyncio
    async def test_three_independent_all_gathered(self, db_session):
        """Three independent tasks should all be gathered in one round."""
        wf = _create_workflow(db_session)

        gathered_count = []

        async def _track(name, params, context=None):
            gathered_count.append(name)
            return {"intent": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="a", params={}),
            SubTaskSpec(intent="b", params={}),
            SubTaskSpec(intent="c", params={}),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_track):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        assert len(gathered_count) == 3


# ==========================================================================
# 18.2.3 — Step dependencies are respected
# ==========================================================================

class TestDependencyRespect_18_2_3:
    """Downstream tasks must NOT run until their dependencies complete."""

    @pytest.mark.asyncio
    async def test_diamond_dag_c_waits_for_a_and_b(self, db_session):
        """Diamond: A,B independent → C depends on both. C must not run first."""
        wf = _create_workflow(db_session)

        call_order = []

        async def _track(name, params, context=None):
            call_order.append(name)
            return {"intent": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="d_a", params={}),
            SubTaskSpec(intent="d_b", params={}),
            SubTaskSpec(intent="d_c", params={}, depends_on=["d_a", "d_b"]),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_track):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        assert call_order.index("d_c") > call_order.index("d_a")
        assert call_order.index("d_c") > call_order.index("d_b")

    @pytest.mark.asyncio
    async def test_failed_dep_cascades_to_downstream(self, db_session):
        """If A fails, B (depends on A) should be marked 'failed' automatically."""
        wf = _create_workflow(db_session)

        async def _fail_a(name, params, context=None):
            if name == "fail_a":
                raise RuntimeError("A blew up")
            return {"intent": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="fail_a", params={}),
            SubTaskSpec(intent="dep_b", params={}, depends_on=["fail_a"]),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_fail_a):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "failed"

        sub_b = db_session.query(WorkflowSubTask).filter_by(
            workflow_id=wf.id, intent="dep_b"
        ).first()
        assert sub_b is not None
        assert sub_b.status == "failed"
        assert "dependency failed" in sub_b.error.lower()

    @pytest.mark.asyncio
    async def test_multi_level_dep_chain(self, db_session):
        """A→B→C→D: four-level dependency chain executes in strict order."""
        wf = _create_workflow(db_session)

        call_order = []

        async def _track(name, params, context=None):
            call_order.append(name)
            return {"intent": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="l1", params={}),
            SubTaskSpec(intent="l2", params={}, depends_on=["l1"]),
            SubTaskSpec(intent="l3", params={}, depends_on=["l2"]),
            SubTaskSpec(intent="l4", params={}, depends_on=["l3"]),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_track):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        assert call_order == ["l1", "l2", "l3", "l4"]

    @pytest.mark.asyncio
    async def test_partial_failure_completed_with_errors(self, db_session):
        """If one branch fails but another succeeds, status is 'completed_with_errors'."""
        wf = _create_workflow(db_session)

        async def _partial_fail(name, params, context=None):
            if name == "bad":
                raise RuntimeError("bad task")
            return {"intent": name}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="good", params={}),
            SubTaskSpec(intent="bad", params={}),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_partial_fail):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed_with_errors"


# ==========================================================================
# 18.2.4 — Workflow failure at one step handles rollback/retry
# ==========================================================================

class TestFailureHandling_18_2_4:
    """Retry logic and failure cascading in WorkflowExecutor."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self, db_session):
        """A task that fails once then succeeds should end up 'completed'."""
        wf = _create_workflow(db_session)

        attempt_count = 0

        async def _flaky(name, params, context=None):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise RuntimeError("transient error")
            return {"retried": True}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="flaky_task", params={}, max_retries=2),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_flaky), \
             patch("asyncio.sleep", new_callable=AsyncMock):  # skip backoff delay
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        assert attempt_count == 2

        sub = db_session.query(WorkflowSubTask).filter_by(
            workflow_id=wf.id, intent="flaky_task"
        ).first()
        assert sub.status == "completed"

    @pytest.mark.asyncio
    async def test_retry_exhausted_marks_failed(self, db_session):
        """When all retries are exhausted the task and workflow are 'failed'."""
        wf = _create_workflow(db_session)

        async def _always_fail(name, params, context=None):
            raise RuntimeError("permanent error")

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="doomed", params={}, max_retries=2),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_always_fail), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "failed"

        sub = db_session.query(WorkflowSubTask).filter_by(
            workflow_id=wf.id, intent="doomed"
        ).first()
        assert sub.status == "failed"
        assert "permanent error" in sub.error

    @pytest.mark.asyncio
    async def test_no_retry_by_default(self, db_session):
        """With max_retries=0 (default), a single failure is final."""
        wf = _create_workflow(db_session)
        call_count = 0

        async def _fail_once(name, params, context=None):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("one-shot failure")

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="no_retry", params={}),  # max_retries defaults to 0
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_fail_once):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "failed"
        assert call_count == 1  # No retry attempted

    @pytest.mark.asyncio
    async def test_all_tasks_fail_workflow_status_is_failed(self, db_session):
        """If every task fails, final workflow status must be 'failed'."""
        wf = _create_workflow(db_session)

        async def _all_fail(name, params, context=None):
            raise RuntimeError(f"{name} failed")

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="fail_x", params={}),
            SubTaskSpec(intent="fail_y", params={}),
        ])

        with patch("backend.services.workflow_tools.execute", side_effect=_all_fail):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "failed"

    @pytest.mark.asyncio
    async def test_retry_with_backoff_calls_sleep(self, db_session):
        """Retry should call asyncio.sleep with exponential backoff."""
        wf = _create_workflow(db_session)
        attempt = 0

        async def _fail_twice(name, params, context=None):
            nonlocal attempt
            attempt += 1
            if attempt <= 2:
                raise RuntimeError("transient")
            return {"ok": True}

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="backoff_test", params={}, max_retries=3),
        ])

        mock_sleep = AsyncMock()
        with patch("backend.services.workflow_tools.execute", side_effect=_fail_twice), \
             patch("asyncio.sleep", mock_sleep):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        assert execution.status == "completed"
        # sleep called twice (for attempt 0 and 1 failures)
        assert mock_sleep.await_count == 2
        # Verify exponential backoff values: 0.5 * 2^0, 0.5 * 2^1
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls[0] == pytest.approx(0.5)
        assert calls[1] == pytest.approx(1.0)

    @pytest.fixture(autouse=True)
    def _mock_workflow_step_runner(self):
        """Mock Celery task to avoid Redis connection in WorkflowEngine tests."""
        with patch('backend.services.workflow_engine.workflow_step_runner') as mock_runner:
            mock_runner.delay = MagicMock()
            mock_runner.apply_async = MagicMock()
            yield mock_runner

    def test_workflow_engine_follows_on_failure_step(self, db_session):
        """WorkflowEngine: when a step fails, on_failure_step branch is followed."""
        # Create workflow with: step 0 (task) --fail--> step 1 (task, terminal)
        wf = Workflow(
            name=f"wf-failure-{uuid.uuid4().hex[:6]}",
            template_json={
                "steps": [
                    {
                        "step_index": 0,
                        "type": "condition",
                        "config": {"condition": {"operator": "==", "key": "status", "expected": "pass"}},
                        "on_success_step": None,
                        "on_failure_step": 1,
                    },
                    {
                        "step_index": 1,
                        "type": "task",
                        "config": {"task_title": "Fallback", "prompt": "Handle failure"},
                        "on_success_step": None,
                        "on_failure_step": None,
                    },
                ]
            },
            version=1,
        )
        db_session.add(wf)
        db_session.flush()

        WorkflowEngine._sync_steps_from_template(db_session, wf, wf.template_json)

        execution = WorkflowExecution(
            workflow_id=wf.id,
            status=WorkflowExecutionStatus.RUNNING,
            current_step_index=0,
            context_data={"status": "NOPE"},  # condition will fail
            original_message="test failure branch",
            triggered_by="test",
        )
        db_session.add(execution)
        db_session.commit()

        # Execute step 0 (condition fails → follows on_failure_step to step 1)
        WorkflowEngine.execute_current_step(db=db_session, execution_id=execution.id)
        db_session.refresh(execution)

        # Should have advanced to step 1 via the failure branch
        assert execution.current_step_index == 1


# ==========================================================================
# 18.2.5 — Celery workflow_tasks.py processes workflows asynchronously
# ==========================================================================

class TestCeleryAsync_18_2_5:
    """Celery tasks for deferred/async workflow processing."""

    @pytest.mark.asyncio
    async def test_deferred_task_enqueued_with_countdown(self, db_session):
        """Deferred subtasks should be handed to Celery with correct countdown."""
        wf = _create_workflow(db_session)

        plan = _make_plan(wf.id, [
            SubTaskSpec(intent="immediate", params={}),
            SubTaskSpec(
                intent="deferred_followup",
                params={"msg": "follow up"},
                schedule_offset_days=14,
            ),
        ])

        mock_exec = _mock_tool({"ok": True})
        mock_apply = MagicMock()
        mock_apply.return_value = MagicMock(id="celery-task-123")

        with patch("backend.services.workflow_tools.execute", mock_exec), \
             patch(
                 "backend.services.tasks.workflow_tasks.execute_deferred_subtask.apply_async",
                 mock_apply,
             ):
            executor = WorkflowExecutor()
            execution = await executor.execute(plan, created_by="test", db_session=db_session)

        # Verify Celery was called with 14-day countdown
        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args
        assert call_kwargs.kwargs.get("countdown") == 14 * 24 * 3600

        # Verify subtask row was updated with celery task ID
        sub = db_session.query(WorkflowSubTask).filter_by(
            workflow_id=wf.id, intent="deferred_followup"
        ).first()
        assert sub is not None
        assert sub.celery_task_id == "celery-task-123"
        assert sub.status == "scheduled"
        assert sub.scheduled_for is not None

    def test_execute_deferred_subtask_updates_db(self, db_session):
        """execute_deferred_subtask Celery task should update SubTask + Execution."""
        wf = _create_workflow(db_session)

        # Pre-create execution and subtask rows
        execution = WorkflowExecution(
            workflow_id=wf.id,
            original_message="deferred test",
            status="running",
            context_data={},
            created_by="test",
        )
        db_session.add(execution)

        sub = WorkflowSubTask(
            workflow_id=wf.id,
            step_index=0,
            intent="deferred_intent",
            params={"x": 1},
            depends_on=[],
            status="scheduled",
            schedule_offset_days=7,
        )
        db_session.add(sub)
        db_session.commit()

        tool_result = {"deferred_result": True}

        # Wrap session so db.close() in task doesn't detach fixture objects
        session_mock = MagicMock(wraps=db_session)
        session_mock.close = MagicMock()

        with patch("backend.services.workflow_tools.execute", new_callable=AsyncMock) as mock_tool, \
             patch(
                 "backend.services.tasks.workflow_tasks._make_session",
                 return_value=session_mock,
             ):
            mock_tool.return_value = tool_result

            from backend.services.tasks.workflow_tasks import execute_deferred_subtask
            # Call the task function directly
            result = execute_deferred_subtask(
                workflow_id=wf.id,
                intent="deferred_intent",
                params={"x": 1},
            )

        assert result == tool_result

        # Verify DB was updated
        sub_updated = db_session.query(WorkflowSubTask).filter_by(id=sub.id).first()
        assert sub_updated is not None
        assert sub_updated.status == "completed"
        assert sub_updated.result == tool_result
        assert sub_updated.completed_at is not None

        wf_exec = db_session.query(WorkflowExecution).filter_by(id=execution.id).first()
        assert wf_exec is not None
        assert wf_exec.context_data.get("deferred_intent") == tool_result

    def test_fire_reminder_creates_notification(self, db_session):
        """fire_reminder should create an ExternalMessage on an active channel."""
        from backend.models.entities.channels import (
            ExternalChannel, ExternalMessage, ChannelType, ChannelStatus,
        )

        # Create an active channel
        channel = ExternalChannel(
            agentium_id=f"CH{uuid.uuid4().hex[:5].upper()}",
            name="test-channel",
            channel_type=ChannelType.DISCORD,
            status=ChannelStatus.ACTIVE,
            config={},
        )
        db_session.add(channel)
        db_session.commit()

        session_mock = MagicMock(wraps=db_session)
        session_mock.close = MagicMock()

        with patch(
            "backend.services.tasks.workflow_tasks._make_session",
            return_value=session_mock,
        ):
            from backend.services.tasks.workflow_tasks import fire_reminder
            result = fire_reminder("Test reminder message", workflow_id=None)

        assert result["fired"] is True
        assert result["message"] == "Test reminder message"

        # Verify ExternalMessage was created
        msgs = db_session.query(ExternalMessage).filter_by(
            channel_id=channel.id
        ).all()
        assert len(msgs) == 1
        assert "Reminder" in msgs[0].content

    def test_fire_reminder_no_channel_graceful(self, db_session):
        """fire_reminder should succeed even when no active channel exists."""
        session_mock = MagicMock(wraps=db_session)
        session_mock.close = MagicMock()

        with patch(
            "backend.services.tasks.workflow_tasks._make_session",
            return_value=session_mock,
        ):
            from backend.services.tasks.workflow_tasks import fire_reminder
            result = fire_reminder("Orphan reminder", workflow_id=None)

        assert result["fired"] is True

    def test_workflow_step_runner_calls_execute_current_step(self, db_session):
        """workflow_step_runner Celery task should call execute_current_step."""
        wf = Workflow(
            name=f"wf-runner-{uuid.uuid4().hex[:6]}",
            template_json={
                "steps": [{
                    "step_index": 0,
                    "type": "task",
                    "config": {"task_title": "T", "prompt": "P"},
                    "on_success_step": None,
                    "on_failure_step": None,
                }]
            },
            version=1,
        )
        db_session.add(wf)
        db_session.flush()

        WorkflowEngine._sync_steps_from_template(db_session, wf, wf.template_json)

        execution = WorkflowExecution(
            workflow_id=wf.id,
            status=WorkflowExecutionStatus.RUNNING,
            current_step_index=0,
            context_data={},
            original_message="step runner test",
            triggered_by="test",
        )
        db_session.add(execution)
        db_session.commit()

        with patch(
            "backend.services.workflow_engine.WorkflowEngine.execute_current_step"
        ) as mock_step:
            with patch("backend.services.workflow_engine.get_db_context") as mock_ctx:
                mock_ctx.return_value.__enter__ = MagicMock(return_value=db_session)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

                from backend.services.workflow_engine import workflow_step_runner
                # Invoke the task directly via .run() to bypass any task decorators
                workflow_step_runner.run(execution.id)

            mock_step.assert_called_once_with(db_session, execution.id)

