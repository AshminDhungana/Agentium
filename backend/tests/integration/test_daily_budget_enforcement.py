"""
Tests for Daily Token Budget Enforcement and Task Throttling/Resumption (Phase 21.3.1).
"""
import pytest
from unittest.mock import MagicMock, patch
import os
import json
import uuid

from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.services.predictive_scaling import PredictiveScalingService

pytestmark = pytest.mark.integration


def test_budget_warning_at_80_percent(db_session):
    """Verify that when spend reaches 80% of DAILY_TOKEN_BUDGET_USD, warning flag is set."""
    mock_redis = MagicMock()

    mock_status = {
        "budget_status": {
            "cost_used_today_usd": 8.50,
            "daily_cost_limit_usd": 10.00,
        }
    }

    with patch.dict(os.environ, {"DAILY_TOKEN_BUDGET_USD": "10.00"}), \
         patch("backend.services.predictive_scaling.token_optimizer.get_status", return_value=mock_status), \
         patch("backend.services.predictive_scaling.redis_client", mock_redis):

        PredictiveScalingService.enforce_token_budget_guard(db_session)

        mock_redis.set.assert_called_with("agentium:budget:warning", "true", ex=86400)
        mock_redis.delete.assert_called_with("agentium:budget:exceeded")


def test_budget_exceeded_pauses_non_critical_tasks(db_session):
    """
    Verify that when spend reaches 100% of budget:
    - Normal and Low priority tasks are paused with pause_reason.
    - Critical and Sovereign priority tasks are NOT paused.
    - Redis exceeded flag is set.
    """
    mock_redis = MagicMock()

    # Create test tasks of different priorities
    normal_task = Task(
        agentium_id=f"T{uuid.uuid4().int % 90000 + 10000}",
        title=f"Normal Task {uuid.uuid4().hex[:6]}",
        description="Normal test task",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.NORMAL,
        status=TaskStatus.IN_PROGRESS,
        execution_context=None
    )
    low_task = Task(
        agentium_id=f"T{uuid.uuid4().int % 90000 + 10000}",
        title=f"Low Task {uuid.uuid4().hex[:6]}",
        description="Low test task",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.LOW,
        status=TaskStatus.PENDING,
        execution_context=None
    )
    critical_task = Task(
        agentium_id=f"T{uuid.uuid4().int % 90000 + 10000}",
        title=f"Critical Task {uuid.uuid4().hex[:6]}",
        description="Critical test task",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.CRITICAL,
        status=TaskStatus.IN_PROGRESS,
        execution_context=None
    )
    sovereign_task = Task(
        agentium_id=f"T{uuid.uuid4().int % 90000 + 10000}",
        title=f"Sovereign Task {uuid.uuid4().hex[:6]}",
        description="Sovereign test task",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.SOVEREIGN,
        status=TaskStatus.IN_PROGRESS,
        execution_context=None
    )

    db_session.add_all([normal_task, low_task, critical_task, sovereign_task])
    db_session.commit()

    mock_status = {
        "budget_status": {
            "cost_used_today_usd": 10.50,
            "daily_cost_limit_usd": 10.00,
        }
    }

    with patch.dict(os.environ, {"DAILY_TOKEN_BUDGET_USD": "10.00"}), \
         patch("backend.services.predictive_scaling.token_optimizer.get_status", return_value=mock_status), \
         patch("backend.services.predictive_scaling.redis_client", mock_redis):

        PredictiveScalingService.enforce_token_budget_guard(db_session)

        mock_redis.set.assert_called_with("agentium:budget:exceeded", "true", ex=86400)

        # Refresh tasks from DB
        db_session.refresh(normal_task)
        db_session.refresh(low_task)
        db_session.refresh(critical_task)
        db_session.refresh(sovereign_task)

        # Non-critical tasks must be paused
        assert normal_task.status == TaskStatus.PAUSED
        normal_ctx = json.loads(normal_task.execution_context) if normal_task.execution_context else {}
        assert normal_ctx.get("pause_reason") == "Token Budget Exceeded"

        assert low_task.status == TaskStatus.PAUSED
        low_ctx = json.loads(low_task.execution_context) if low_task.execution_context else {}
        assert low_ctx.get("pause_reason") == "Token Budget Exceeded"

        # Critical and Sovereign must remain IN_PROGRESS
        assert critical_task.status == TaskStatus.IN_PROGRESS
        assert sovereign_task.status == TaskStatus.IN_PROGRESS


def test_resume_paused_tasks_when_budget_available(db_session):
    """
    Verify that resume_paused_tasks_if_budget_available resumes only tasks paused
    for budget exhaustion when spend is below budget.
    """
    mock_redis = MagicMock()

    # Create task paused due to budget
    budget_paused_task = Task(
        agentium_id=f"T{uuid.uuid4().int % 90000 + 10000}",
        title=f"Budget Paused {uuid.uuid4().hex[:6]}",
        description="Budget paused task",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.NORMAL,
        status=TaskStatus.PAUSED,
        execution_context=json.dumps({"pause_reason": "Token Budget Exceeded"})
    )
    # Create task paused for other reason (e.g. human intervention)
    other_paused_task = Task(
        agentium_id=f"T{uuid.uuid4().int % 90000 + 10000}",
        title=f"User Paused {uuid.uuid4().hex[:6]}",
        description="User paused task",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.NORMAL,
        status=TaskStatus.PAUSED,
        execution_context=json.dumps({"pause_reason": "Waiting for User Approval"})
    )

    db_session.add_all([budget_paused_task, other_paused_task])
    db_session.commit()

    mock_status = {
        "budget_status": {
            "cost_used_today_usd": 2.00,  # Below limit of 10.00
            "daily_cost_limit_usd": 10.00,
        }
    }

    with patch.dict(os.environ, {"DAILY_TOKEN_BUDGET_USD": "10.00"}), \
         patch("backend.services.predictive_scaling.token_optimizer.get_status", return_value=mock_status), \
         patch("backend.services.predictive_scaling.redis_client", mock_redis):

        resumed = PredictiveScalingService.resume_paused_tasks_if_budget_available(db_session)
        assert resumed >= 1

        db_session.refresh(budget_paused_task)
        db_session.refresh(other_paused_task)

        # Budget paused task is resumed to PENDING and pause_reason is cleared
        assert budget_paused_task.status == TaskStatus.PENDING
        budget_ctx = json.loads(budget_paused_task.execution_context) if budget_paused_task.execution_context else {}
        assert "pause_reason" not in budget_ctx

        # Other paused task is untouched
        assert other_paused_task.status == TaskStatus.PAUSED
        other_ctx = json.loads(other_paused_task.execution_context) if other_paused_task.execution_context else {}
        assert other_ctx.get("pause_reason") == "Waiting for User Approval"

        mock_redis.delete.assert_called_with("agentium:budget:exceeded")
