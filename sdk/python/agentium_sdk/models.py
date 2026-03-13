"""
Pydantic models mirroring the Agentium backend schemas.

These provide type-safe data containers for SDK responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# Agent Models
# ═══════════════════════════════════════════════════════════

class Agent(BaseModel):
    """Represents an Agentium agent."""
    id: Optional[str] = None
    agentium_id: str
    role: str
    status: str
    tier: int
    current_task: Optional[str] = None
    performance_score: Optional[float] = None
    supervised_by: Optional[str] = None
    total_tasks_completed: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    is_persistent: bool = False
    responsibilities: Optional[str] = None
    created_at: Optional[datetime] = None
    last_active: Optional[datetime] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


# ═══════════════════════════════════════════════════════════
# Task Models
# ═══════════════════════════════════════════════════════════

class Task(BaseModel):
    """Represents an Agentium task."""
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: str = "pending"
    priority: Optional[str] = None
    task_type: Optional[str] = None
    assigned_to: Optional[str] = None
    created_by: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        extra = "allow"


# ═══════════════════════════════════════════════════════════
# Constitution Models
# ═══════════════════════════════════════════════════════════

class ConstitutionArticle(BaseModel):
    """A single article within the constitution."""
    title: str
    content: str


class Constitution(BaseModel):
    """Represents the Agentium Constitution."""
    id: Optional[str] = None
    agentium_id: Optional[str] = None
    version: str
    version_number: Optional[int] = None
    preamble: Optional[str] = None
    articles: Optional[Dict[str, Any]] = None
    prohibited_actions: Optional[List[str]] = None
    sovereign_preferences: Optional[Dict[str, Any]] = None
    is_active: bool = True
    effective_date: Optional[datetime] = None
    changelog: Optional[List[Dict[str, Any]]] = None

    class Config:
        extra = "allow"


# ═══════════════════════════════════════════════════════════
# Voting Models
# ═══════════════════════════════════════════════════════════

class Vote(BaseModel):
    """Represents a vote or proposal."""
    id: Optional[str] = None
    proposal_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    proposed_by: Optional[str] = None
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    quorum_required: Optional[float] = None
    deadline: Optional[datetime] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        extra = "allow"


# ═══════════════════════════════════════════════════════════
# Webhook Models
# ═══════════════════════════════════════════════════════════

class WebhookSubscription(BaseModel):
    """Represents an outbound webhook subscription."""
    id: Optional[str] = None
    url: str
    events: List[str] = Field(default_factory=list)
    secret: Optional[str] = None
    is_active: bool = True
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        extra = "allow"


class WebhookDelivery(BaseModel):
    """Represents a webhook delivery attempt."""
    id: Optional[str] = None
    subscription_id: Optional[str] = None
    event_type: str
    payload: Optional[Dict[str, Any]] = None
    status_code: Optional[int] = None
    attempts: int = 0
    delivered_at: Optional[datetime] = None
    error: Optional[str] = None

    class Config:
        extra = "allow"


# ═══════════════════════════════════════════════════════════
# Chat / Message Models
# ═══════════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    """Represents a chat message."""
    id: Optional[str] = None
    content: str
    role: str = "user"
    agent_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        extra = "allow"


class ChatResponse(BaseModel):
    """Response from sending a chat message."""
    message: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    response: Optional[str] = None

    class Config:
        extra = "allow"


# ═══════════════════════════════════════════════════════════
# System Models
# ═══════════════════════════════════════════════════════════

class HealthStatus(BaseModel):
    """System health status."""
    status: str
    database: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


class TokenStatus(BaseModel):
    """Token optimizer status."""
    optimizer: Optional[Dict[str, Any]] = None
    idle_budget: Optional[Dict[str, Any]] = None
    mode: str = "active"
