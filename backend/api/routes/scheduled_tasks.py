# backend/api/routes/scheduled_tasks.py
"""Scheduled Tasks API routes.

CRUD lifecycle for :class:`ScheduledTask` rows under ``/api/v1/scheduled-tasks``.
Sovereign/admin users (or any ``is_admin`` token, matching the User model's
``is_admin`` -> ``primary_sovereign`` equivalence) have full access; all other
users are scoped to their own ``owner_agentium_id``.
"""
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.auth import get_current_active_user
from backend.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from backend.api.schemas.scheduled_task import ScheduledTaskCreate, ScheduledTaskUpdate
from backend.models.database import get_db
from backend.models.entities.scheduled_task import ScheduledTask, ScheduledTaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


def _is_sovereign(current_user: Dict[str, Any]) -> bool:
    cu = current_user or {}
    return (
        cu.get("role") in ("primary_sovereign", "sovereign", "admin")
        or bool(cu.get("is_admin"))
    )


def _resolve_owner(current_user: Dict[str, Any]) -> str:
    cu = current_user or {}
    owner = cu.get("agentium_id") or cu.get("user_id") or cu.get("sub")
    return str(owner) if owner else "00001"


def _serialize(rec: ScheduledTask) -> dict:
    return rec.to_dict()


def _get_or_404(db: Session, agentium_id: str) -> ScheduledTask:
    rec = (
        db.query(ScheduledTask)
        .filter_by(agentium_id=agentium_id, is_active=True)
        .first()
    )
    if not rec:
        raise NotFoundError(
            error=f"Scheduled task {agentium_id} not found", code="SCHEDULE_NOT_FOUND"
        )
    return rec


def _scope_or_403(rec: ScheduledTask, current_user: Dict[str, Any]) -> None:
    if not _is_sovereign(current_user) and rec.owner_agentium_id != _resolve_owner(current_user):
        raise ForbiddenError(error="Not your scheduled task", code="SCHEDULE_FORBIDDEN")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_scheduled_task(
    payload: ScheduledTaskCreate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        rec = ScheduledTask(
            name=payload.name,
            description=payload.description,
            cron_expression=payload.cron_expression,
            timezone=payload.timezone or "UTC",
            run_once=payload.run_once,
            run_at=payload.run_at,
            task_payload=json.dumps(payload.task_payload),
            owner_agentium_id=payload.owner_agentium_id or _resolve_owner(current_user),
            priority=payload.priority,
            max_retries=payload.max_retries,
        )
    except ValueError as exc:
        raise BadRequestError(error=str(exc), code="INVALID_SCHEDULE_CONFIG")

    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _serialize(rec)


@router.get("")
def list_scheduled_tasks(
    status_: Optional[str] = Query(default=None, alias="status"),
    owner: Optional[str] = Query(default=None, alias="owner_agentium_id"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not _is_sovereign(current_user):
        owner = owner or _resolve_owner(current_user)
    q = db.query(ScheduledTask).filter(ScheduledTask.is_active == True)  # noqa: E712
    if status_:
        q = q.filter(ScheduledTask.status == ScheduledTaskStatus(status_))
    if owner:
        q = q.filter(ScheduledTask.owner_agentium_id == owner)
    rows = (
        q.order_by(ScheduledTask.created_at.desc()).offset(offset).limit(limit).all()
    )
    return [_serialize(r) for r in rows]


@router.get("/{schedule_id}")
def get_scheduled_task(
    schedule_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rec = _get_or_404(db, schedule_id)
    _scope_or_403(rec, current_user)
    return _serialize(rec)


@router.patch("/{schedule_id}")
def update_scheduled_task(
    schedule_id: str,
    payload: ScheduledTaskUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rec = _get_or_404(db, schedule_id)
    _scope_or_403(rec, current_user)

    data = payload.model_dump(exclude_unset=True)
    schedule_changed = any(
        k in data for k in ("cron_expression", "timezone", "run_once", "run_at")
    )

    if "name" in data and data["name"] is not None:
        rec.name = data["name"]
    if "description" in data:
        rec.description = data["description"]
    if "priority" in data and data["priority"] is not None:
        rec.priority = data["priority"]
    if "max_retries" in data and data["max_retries"] is not None:
        rec.max_retries = data["max_retries"]
    if "cron_expression" in data:
        rec.cron_expression = data["cron_expression"]
    if "timezone" in data and data["timezone"]:
        rec.timezone = data["timezone"]
    if "run_once" in data:
        rec.run_once = bool(data["run_once"])
    if "run_at" in data:
        rec.run_at = data["run_at"]
    if "task_payload" in data and data["task_payload"] is not None:
        rec.set_task_payload(data["task_payload"])
    if "paused" in data:
        if data["paused"]:
            rec.pause()
        else:
            rec.resume()

    try:
        rec.validate_schedule_config()
        if schedule_changed and rec.status != ScheduledTaskStatus.PAUSED:
            rec.next_execution_at = rec.calculate_next_run()
        db.commit()
        db.refresh(rec)
    except ValueError as exc:
        db.rollback()
        raise BadRequestError(error=str(exc), code="INVALID_SCHEDULE_CONFIG")
    return _serialize(rec)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheduled_task(
    schedule_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rec = _get_or_404(db, schedule_id)
    _scope_or_403(rec, current_user)
    db.delete(rec)
    db.commit()
    return None