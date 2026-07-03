"""
Wait & Poll API routes.

Endpoints
---------
POST   /api/v1/wait-conditions/              Create a WaitCondition for a task
GET    /api/v1/wait-conditions/{id}          Get a single WaitCondition
GET    /api/v1/wait-conditions/task/{task_id} List all conditions for a task
POST   /api/v1/wait-conditions/{id}/resolve  Manually resolve (WEBHOOK / MANUAL)
POST   /api/v1/wait-conditions/{id}/cancel   Cancel an active condition
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user
from backend.models.database import get_db
from backend.models.entities.task import Task, TaskStatus
from backend.models.entities.wait_condition import (
    WaitCondition,
    WaitConditionStatus,
    WaitStrategy,
)
from backend.services.wait_poll_service import WaitPollService
from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Wait & Poll"])


# ── Request / Response schemas ────────────────────────────────────────────────

class CreateWaitConditionRequest(BaseModel):
    task_id:               str
    strategy:              WaitStrategy
    config:                Dict[str, Any]           = Field(default_factory=dict)
    max_attempts:          int                       = 60
    poll_interval_seconds: int                       = 30
    timeout_seconds:       Optional[int]             = None


class ResolveWaitConditionRequest(BaseModel):
    data: Optional[Dict[str, Any]] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_condition_or_404(db: Session, condition_id: str) -> WaitCondition:
    condition = db.query(WaitCondition).filter(WaitCondition.id == condition_id).first()
    if not condition:
        raise NotFoundError(error="WaitCondition not found", code="WAITCONDITION_NOT_FOUND")
    return condition


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/wait-conditions/",
    status_code=status.HTTP_201_CREATED,
    summary="Create a WaitCondition and put the task into WAITING state",
    description="Create a new WaitCondition for a task, placing the task into WAITING state. The task will remain waiting until the condition is resolved or cancelled.",
    responses=build_responses(None),
)
def create_wait_condition(
    body: CreateWaitConditionRequest,
    db:   Session = Depends(get_db),
    _user = Depends(get_current_user),
):
    # Validate task exists
    task = db.query(Task).filter(Task.id == body.task_id).first()
    if not task:
        raise NotFoundError(error="Task not found", code="TASK_NOT_FOUND")

    if task.status == TaskStatus.WAITING:
        raise ConflictError(error="Task is already in WAITING state", code="TASK_IS_ALREADY_IN_WAITING")

    # Create condition
    condition = WaitPollService.create_condition(
        db=db,
        task_id=body.task_id,
        strategy=body.strategy,
        config=body.config,
        max_attempts=body.max_attempts,
        poll_interval_seconds=body.poll_interval_seconds,
        timeout_seconds=body.timeout_seconds,
    )

    # Transition task → WAITING
    try:
        task.set_status(
            TaskStatus.WAITING,
            actor_id="api",
            note=f"WaitCondition {condition.agentium_id} created (strategy={body.strategy.value})",
        )
    except Exception as exc:
        db.rollback()
        raise BadRequestError(error=f"Could not transition task to WAITING: {exc}", code="COULD_NOT_TRANSITION_TASK_TO")

    db.commit()
    db.refresh(condition)
    return condition.to_dict()


@router.get(
    "/wait-conditions/{condition_id}",
    summary="Get a WaitCondition by ID",
    description="Retrieve a single WaitCondition by its unique identifier. Returns the condition's current status, strategy, and metadata.",
    responses=build_responses(None),
)
def get_wait_condition(
    condition_id: str,
    db:           Session = Depends(get_db),
    _user = Depends(get_current_user),
):
    return _get_condition_or_404(db, condition_id).to_dict()


@router.get(
    "/wait-conditions/task/{task_id}",
    summary="List all WaitConditions for a task",
    description="List all WaitConditions associated with a specific task, ordered by creation date (most recent first).",
    responses=build_responses(None),
)
def list_wait_conditions_for_task(
    task_id: str,
    db:      Session = Depends(get_db),
    _user = Depends(get_current_user),
) -> List[Dict]:
    conditions = (
        db.query(WaitCondition)
        .filter(WaitCondition.task_id == task_id)
        .order_by(WaitCondition.created_at.desc())
        .all()
    )
    return [c.to_dict() for c in conditions]


@router.post(
    "/wait-conditions/{condition_id}/resolve",
    summary="Manually resolve a WaitCondition (WEBHOOK / MANUAL strategies)",
    description="Manually resolve an active WaitCondition. The parent task will transition back to IN_PROGRESS. Only conditions in ACTIVE status can be resolved.",
    responses=build_responses(None),
)
def resolve_wait_condition(
    condition_id: str,
    body:         ResolveWaitConditionRequest = ResolveWaitConditionRequest(),
    db:           Session = Depends(get_db),
    _user = Depends(get_current_user),
):
    condition = _get_condition_or_404(db, condition_id)

    if condition.status != WaitConditionStatus.ACTIVE:
        raise ConflictError(error=f"WaitCondition is not ACTIVE (current status: {condition.status.value})", code="WAITCONDITION_IS_NOT_ACTIVE_CURRENT")

    success = WaitPollService.resolve_condition(db, condition_id, data=body.data)
    if not success:
        raise InternalServerError(error="Resolution failed", code="RESOLUTION_FAILED")

    db.refresh(condition)
    return condition.to_dict()


@router.post(
    "/wait-conditions/{condition_id}/cancel",
    summary="Cancel an active WaitCondition",
    description="Cancel an active WaitCondition. If the parent task is in WAITING state, it will revert to IN_PROGRESS.",
    responses=build_responses(None),
)
def cancel_wait_condition(
    condition_id: str,
    db:           Session = Depends(get_db),
    _user = Depends(get_current_user),
):
    condition = _get_condition_or_404(db, condition_id)

    if condition.status not in (WaitConditionStatus.ACTIVE, WaitConditionStatus.PENDING):
        raise ConflictError(error=f"Cannot cancel a condition in state: {condition.status.value}", code="CANNOT_CANCEL_A_CONDITION_IN")

    condition.cancel()

    # If the parent task is still WAITING, revert it to IN_PROGRESS
    task = db.query(Task).filter(Task.id == condition.task_id).first()
    if task and task.status == TaskStatus.WAITING:
        try:
            task.set_status(
                TaskStatus.IN_PROGRESS,
                actor_id="api",
                note=f"WaitCondition {condition.agentium_id} cancelled by user",
            )
        except Exception:
            pass  # Non-fatal; task status is best-effort here

    db.commit()
    db.refresh(condition)
    return condition.to_dict()