from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DecisionAction(str, Enum):
    REPLY = "reply"
    CREATE_TASK = "create_task"
    SPAWN_AGENT = "spawn_agent"
    DISPATCH_TASK = "dispatch_task"
    VOTE = "vote"
    DELEGATE = "delegate"


@dataclass
class Decision:
    action: DecisionAction
    rationale: str = ""
    target_tier: Optional[str] = None
    task_brief: Optional[str] = None
    tools_considered: List[str] = field(default_factory=list)
    confidence: float = 0.0


class DecisionEngine:
    """Single structured decision layer used by all agent tiers."""

    CONFIDENCE_FALLBACK = 0.4

    async def decide(self, agent, message: str, db, cache=None) -> Decision:
        raise NotImplementedError
