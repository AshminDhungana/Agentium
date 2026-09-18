# backend/api/schemas/scheduled_task.py
"""Pydantic schemas for the Scheduled Tasks API.

Scheduling-mode (cron vs one-time) validation intentionally lives on the
ScheduledTask model's ``validate_schedule_config()`` (surfaced by the route as
HTTP 400), not in a Pydantic model_validator.  Pydantic request-validation
errors render as 422 app-wide (there is no 422->400 override in
``register_error_handlers``), so a model_validator here would break the
documented "mutual exclusion -> 400 on ValueError" contract.  The cron-syntax
``field_validator`` stays: malformed cron is a malformed *request* (422) and is
indistinguishable from any other bad field, so that can remain Pydantic-native.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class ScheduledTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    cron_expression: Optional[str] = Field(default=None, description="cron, or None for one-time")
    timezone: str = Field(default="UTC")
    run_once: bool = False
    run_at: Optional[datetime] = None
    task_payload: Dict[str, Any] = Field(
        default_factory=lambda: {"action_type": "execution", "params": {}}
    )
    owner_agentium_id: str = Field(default="00001")
    priority: int = Field(default=1, ge=1, le=5)
    max_retries: int = Field(default=3, ge=0)

    @field_validator("cron_expression")
    def validate_cron(cls, v):
        if not v:
            return v
        from croniter import croniter
        try:
            croniter(v, datetime(2026, 1, 1))
        except Exception as exc:
            raise ValueError(f"Invalid cron expression: {v}") from exc
        return v


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    run_once: Optional[bool] = None
    run_at: Optional[datetime] = None
    task_payload: Optional[Dict[str, Any]] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    max_retries: Optional[int] = Field(default=None, ge=0)
    paused: Optional[bool] = None


class ScheduledTaskResponse(BaseModel):
    """Documentation-only shape; the route returns the model's ``to_dict()``."""

    agentium_id: str
    name: str
    description: Optional[str]
    cron_expression: Optional[str]
    timezone: str
    run_once: bool
    run_at: Optional[datetime]
    task_payload: Dict[str, Any] = Field(default_factory=dict)
    owner_agentium_id: str
    status: str
    priority: int
    max_retries: int
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    execution_count: int
    failure_count: int