"""
Clarification Service for Agentium.
Allows agents to query supervisors when confused about inherited state.
Implements the full clarification hierarchy (Workflow §2.3):
  Sovereign → Head → Council → Lead → Task → Critics
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from backend.models.entities import Agent
from backend.models.entities.agents import AgentType, AgentStatus
from backend.models.entities.constitution import Ethos

from backend.services.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)
# Full hierarchy chain for clarification (Workflow §2.3)
# Index 0 = highest authority; higher index = lower tier.
HIERARCHY_ORDER: List[AgentType] = [
    AgentType.HEAD_OF_COUNCIL,
    AgentType.COUNCIL_MEMBER,
    AgentType.LEAD_AGENT,
    AgentType.TASK_AGENT,
    AgentType.CODE_CRITIC,
    AgentType.OUTPUT_CRITIC,
    AgentType.PLAN_CRITIC,
]

class ClarificationService:
    """
    Service for agent-to-supervisor clarification queries.
    Used when reincarnated agents are confused about their task.

    The clarification chain follows:
      Sovereign → Head → Council → Lead → Task → Critics
    Each agent asks its immediate superior. If the superior cannot clarify,
    the question escalates up the chain until clarity or the Sovereign is reached.
    """
    
    @staticmethod
    def consult_supervisor(
        agent: Agent,
        db: Session,
        question: str,
        context: str
    ) -> Dict[str, Any]:
        """
        Agent asks parent/supervisor for clarification.
        Returns guidance and historical context.
        """
        if not agent.parent:
            return {
                "guidance": "You report directly to the Sovereign. Check system logs for your assigned purpose.",
                "historical_context": None,
                "direct_supervisor": None
            }
        
        parent = agent.parent
        
        # Get parent's perspective on what this agent should be doing
        parent_context = ClarificationService._get_parent_perspective(parent, agent, db)
        
        # Get task history from parent's viewpoint
        task_history = ClarificationService._get_task_history_from_parent(parent, agent, db)
        
        response = {
            "consulted": parent.agentium_id,
            "parent_role": parent.agent_type.value,
            "guidance": f"As your {parent.agent_type.value}, I assigned you to: {parent_context}",
            "your_purpose": agent.ethos.mission_statement[:300] + "..." if agent.ethos else "Mission not loaded",
            "task_history": task_history,
            "recommendation": ClarificationService._generate_recommendation(agent, parent, task_history),
            "escalation_available": True if parent.parent else False
        }
        
        return response
    
    @staticmethod
    def escalate_clarification(
        agent: Agent,
        question: str,
        db: Session,
        max_escalations: int = 3
    ) -> Dict[str, Any]:
        """
        Escalate a clarification up the hierarchy chain (Workflow §2.3).

        Walks up the chain from the agent's immediate supervisor until:
          - A satisfactory response is obtained, or
          - The Sovereign level is reached, or
          - max_escalations is exhausted.
        """
        escalation_trail = []
        current_agent = agent

        for step in range(max_escalations):
            if not current_agent.parent:
                escalation_trail.append({
                    "step": step + 1,
                    "agent_id": current_agent.agentium_id,
                    "role": current_agent.agent_type.value,
                    "result": "reached_top_of_hierarchy",
                    "guidance": "Escalate to the Sovereign for final clarification.",
                })
                break

            parent = current_agent.parent
            parent_context = ClarificationService._get_parent_perspective(
                parent, current_agent, db
            )
            task_history = ClarificationService._get_task_history_from_parent(
                parent, current_agent, db
            )

            step_result = {
                "step": step + 1,
                "consulted": parent.agentium_id,
                "role": parent.agent_type.value,
                "guidance": f"As your {parent.agent_type.value}: {parent_context}",
                "task_history": task_history,
            }
            escalation_trail.append(step_result)

            # If the parent has useful task context, stop escalation
            if task_history:
                step_result["result"] = "clarity_achieved"
                break

            # Otherwise, continue up the chain
            current_agent = parent

        return {
            "original_agent": agent.agentium_id,
            "question": question,
            "escalation_trail": escalation_trail,
            "resolved": any(
                s.get("result") == "clarity_achieved" for s in escalation_trail
            ),
        }

    @staticmethod
    def _get_parent_perspective(parent: Agent, child: Agent, db: Session) -> str:
        """Get what the parent thinks the child should be doing."""
        # Check if parent spawned this child specifically
        if child.created_by_agentium_id == parent.agentium_id:
            return f"You were spawned by me ({parent.agentium_id}) for: {child.description or 'general service'}"
        
        # Find recent spawn relationship
        from backend.models.entities.audit import AuditLog
        spawn_log = db.query(AuditLog).filter_by(
            actor_id=parent.agentium_id,
            action="agent_spawned",
            target_id=child.agentium_id
        ).order_by(AuditLog.created_at.desc()).first()
        
        if spawn_log:
            return spawn_log.description or "Spawned for task execution"
        
        return "Standard hierarchical assignment"
    
    @staticmethod
    def _get_task_history_from_parent(parent: Agent, child: Agent, db: Session) -> list:
        """Get tasks parent assigned to this child."""
        from backend.models.entities.task import Task
        
        tasks = db.query(Task).filter(
            Task.created_by == parent.agentium_id,
            Task.assigned_task_agent_ids.contains(child.agentium_id)
        ).order_by(Task.created_at.desc()).limit(3).all()
        
        return [
            {
                "task_id": t.agentium_id,
                "title": t.title,
                "status": t.status.value,
                "progress": t.completion_percentage
            }
            for t in tasks
        ]
    
    @staticmethod
    def _generate_recommendation(agent: Agent, parent: Agent, task_history: list) -> str:
        """Generate guidance based on state."""
        if not task_history:
            return "Ask me (your parent) for a new task assignment. Reference your ethos for your specialized role."
        
        current_task = task_history[0]
        
        if current_task["status"] in ["in_progress", "assigned"]:
            return f"Continue work on {current_task['task_id']}: {current_task['title']} ({current_task['progress']}% complete). Check subtasks for next steps."
        
        if current_task["status"] == "completed":
            return f"Last task completed. Request new assignment from me or check idle task queue."
        
        return "Review task history and consult your ethos behavioral rules for guidance."
    
    @staticmethod
    def get_lineage(agent: Agent, db: Session) -> Dict[str, Any]:
        """
        Get full chain of command for an agent.
        Useful for understanding hierarchy.
        """
        lineage = []
        current = agent
        
        while current:
            lineage.append({
                "agentium_id": current.agentium_id,
                "role": current.agent_type.value,
                "status": current.status.value,
                "is_persistent": current.is_persistent
            })
            
            if current.parent:
                current = current.parent
            else:
                break
        
        return {
            "my_id": agent.agentium_id,
            "lineage": lineage,
            "supervisor": agent.parent.agentium_id if agent.parent else "The Sovereign",
            "subordinates": [sub.agentium_id for sub in agent.subordinates]
        }

# Singleton
clarification_service = ClarificationService()