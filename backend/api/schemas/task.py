"""
Pydantic schemas for Task API.
Maps to/from backend.models.entities.task (Task entity).
Updated: Phase 6.3 — Pre-Declared Acceptance Criteria
"""
from pydantic import BaseModel, Field, validator as pydantic_validator
from datetime import datetime
from typing import Optional, List, Any, Dict

from backend.models.entities.task import TaskStatus, TaskType, TaskPriority


class AssignedAgents(BaseModel):
    head: Optional[str] = None
    lead: Optional[str] = None
    task_agents: List[str] = []


class AcceptanceCriterionSchema(BaseModel):
    """
    Single success criterion submitted alongside a task proposal.
    Validated by critic agents during review.
    """
    metric: str = Field(..., min_length=1, pattern=r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    threshold: Any
    validator: str = Field(..., description="code | output | plan")
    is_mandatory: bool = True
    description: str = ""

    @pydantic_validator("validator")
    def validate_validator(cls, v: str) -> str:
        allowed = {"code", "output", "plan"}
        if v not in allowed:
            raise ValueError(f"validator must be one of {sorted(allowed)}")
        return v


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    priority: str = Field(default="normal")
    task_type: str = Field(default="execution")

    # Governance (pre-existing)
    constitutional_basis: Optional[str] = None
    hierarchical_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    execution_plan_id: Optional[str] = None
    recurrence_pattern: Optional[str] = None

    # Phase 6.3 — Acceptance Criteria
    acceptance_criteria: Optional[List[AcceptanceCriterionSchema]] = Field(
        default=None,
        description="Pre-declared success criteria evaluated by critic agents on review."
    )
    veto_authority: Optional[str] = Field(
        default=None,
        description="Critic type with veto authority: code | output | plan"
    )

    # Phase 13.1 — Auto-Delegation
    auto_delegate: bool = Field(
        default=True,
        description="Trigger auto-delegation engine on task creation"
    )

    @pydantic_validator("priority")
    def validate_priority(cls, v):
        allowed = [p.value for p in TaskPriority]
        mapping = {"urgent": "high"}
        v = mapping.get(v, v)
        if v not in allowed:
            raise ValueError(f"priority must be one of {allowed}")
        return v

    @pydantic_validator("task_type")
    def validate_task_type(cls, v):
        allowed = [t.value for t in TaskType]
        if v not in allowed:
            return "execution"
        return v

    @pydantic_validator("veto_authority")
    def validate_veto_authority(cls, v):
        if v is None:
            return v
        if v not in {"code", "output", "plan"}:
            raise ValueError("veto_authority must be one of: code, output, plan")
        return v

    @pydantic_validator("acceptance_criteria", each_item=False)
    def validate_unique_metrics(cls, v):
        if not v:
            return v
        metrics = [c.metric for c in v]
        if len(metrics) != len(set(metrics)):
            dupes = {m for m in metrics if metrics.count(m) > 1}
            raise ValueError(f"Duplicate metric names in acceptance_criteria: {dupes}")
        return v

    def acceptance_criteria_as_dicts(self) -> Optional[List[Dict[str, Any]]]:
        if not self.acceptance_criteria:
            return None
        return [c.dict() for c in self.acceptance_criteria]


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str
    task_type: str = "execution"
    progress: float = 0.0
    assigned_agents: AssignedAgents = AssignedAgents()
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    status_note: Optional[str] = None
    priority: Optional[str] = None
    constitutional_basis: Optional[str] = None
    hierarchical_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    execution_plan_id: Optional[str] = None
    # Phase 6.3
    acceptance_criteria: Optional[List[AcceptanceCriterionSchema]] = None
    veto_authority: Optional[str] = None
    # Phase 13.1
    escalation_timeout_seconds: Optional[int] = None

    @pydantic_validator("veto_authority")
    def validate_veto_authority(cls, v):
        if v is None:
            return v
        if v not in {"code", "output", "plan"}:
            raise ValueError("veto_authority must be one of: code, output, plan")
        return v

