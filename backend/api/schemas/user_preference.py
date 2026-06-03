"""
Pydantic schemas for User Preference API.
"""

from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field, field_validator


class PreferenceBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    category: str = Field(default="general")
    scope: str = Field(default="global")
    description: Optional[str] = None


class PreferenceCreate(PreferenceBase):
    value: Any
    scope_target_id: Optional[str] = None
    editable_by_agents: bool = True

    @field_validator('key')
    def validate_key_format(cls, v):
        """Ensure key follows hierarchical format."""
        if '.' in v:
            parts = v.split('.')
            if len(parts) > 3:
                raise ValueError("Key can have at most 3 levels")
        return v.lower().strip().replace(' ', '_')


class PreferenceUpdate(BaseModel):
    value: Any
    reason: Optional[str] = None


class PreferenceValue(BaseModel):
    key: str
    value: Any
    data_type: str
    source: str = "user"  # user, system_default, agent_modified


class PreferenceBulkUpdate(BaseModel):
    preferences: Dict[str, Any]
    reason: Optional[str] = None


class PreferenceHistoryEntry(BaseModel):
    previous_value: Any
    new_value: Any
    changed_by: Optional[str]  # agentium_id or user_id
    change_reason: Optional[str]
    timestamp: str


class AgentPreferenceAccess(BaseModel):
    key: str
    value: Any
    editable: bool
    category: str
    description: Optional[str]


class OptimizationResult(BaseModel):
    duplicates_removed: int
    unused_cleaned: int
    history_compressed: int
    conflicts_resolved: int


class OptimizationRecommendation(BaseModel):
    type: str  # conflict, high_churn, unused
    key: str
    recommendation: str
    details: Optional[Dict[str, Any]] = None