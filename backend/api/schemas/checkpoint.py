"""
Pydantic schemas for ExecutionCheckpoints.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from backend.models.entities.checkpoint import CheckpointPhase


class CheckpointBase(BaseModel):
    session_id: str
    task_id: str
    phase: CheckpointPhase
    agent_states: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    task_state_snapshot: Dict[str, Any] = Field(default_factory=dict)
    parent_checkpoint_id: Optional[str] = None
    branch_name: Optional[str] = None


class CheckpointCreate(CheckpointBase):
    """Payload for manually creating a snapshot."""
    pass


class CheckpointResponse(CheckpointBase):
    """Response model for a checkpoint."""
    id: str
    agentium_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CheckpointBranchRequest(BaseModel):
    """Payload for branching from a checkpoint."""
    branch_name: str
    new_supervisor_id: Optional[str] = None


# ─── Phase 18: Unified Diff ──────────────────────────────────────────────

class UnifiedDiffResponse(BaseModel):
    """Unified diff of two checkpoint snapshot JSONs."""
    left_checkpoint_id: str
    right_checkpoint_id: str
    left_branch: Optional[str] = None
    right_branch: Optional[str] = None
    left_agentium_id: Optional[str] = None
    right_agentium_id: Optional[str] = None
    unified_diff: str
    left_json: str
    right_json: str
