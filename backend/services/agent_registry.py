from __future__ import annotations
from typing import Optional
from backend.services.decision_engine import Decision, DecisionAction
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.services.capability_registry import CapabilityRegistry, Capability
from backend.services.reincarnation_service import ReincarnationService
import logging

logger = logging.getLogger(__name__)


class AgentRegistry:
    # Task agents span 3xxxx-6xxxx (AgentType.TASK_AGENT).
    TASK_TIER_PREFIXES = {"3", "4", "5", "6"}

    @staticmethod
    async def choose_target(decision: Decision, db, caller) -> Optional[str]:
        """Resolve the best agent to receive a delegated task, or auto-spawn one."""
        if (
            decision.target_tier
            and decision.target_tier[:1] in AgentRegistry.TASK_TIER_PREFIXES
        ):
            agent = (
                db.query(Agent)
                .filter(
                    Agent.agent_type == AgentType.TASK_AGENT,
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True,
                )
                .first()
            )
            if agent:
                return agent.agentium_id
            try:
                if CapabilityRegistry.can_agent(caller, Capability.SPAWN_TASK_AGENT, db):
                    new_agent = ReincarnationService.spawn_task_agent(
                        parent=caller,
                        name=f"TaskAgent-{getattr(caller, 'agentium_id', 'x')}",
                        description=decision.task_brief or "Auto-spawned for delegation",
                        db=db,
                    )
                    db.commit()
                    return new_agent.agentium_id
            except Exception as e:
                logger.warning("AgentRegistry auto-spawn failed: %s", e)
            return None
        # For Lead-tier targets (2xxxx) reuse existing Lead selection logic of caller.
        return None
