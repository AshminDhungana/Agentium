import logging
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from backend.services.clarification_service import ClarificationService
from backend.core.uncertainty_detector import UncertaintySignal

logger = logging.getLogger(__name__)


class ClarificationHandler:
    """
    Orchestrates clarification within the agentic loop.
    Handles: supervisor consult → escalation → guidance injection.
    """

    MAX_CLARIFICATION_ROUNDS = 2  # Prevent infinite loops per task execution

    def __init__(self, agent: Any, db: Session):
        self.agent = agent
        self.db = db
        self.clarification_rounds = 0
        self.escalation_trail: List[Dict[str, Any]] = []

    async def handle_uncertainty(
        self,
        signal: UncertaintySignal,
        conversation: List[Dict[str, str]],
    ) -> Tuple[bool, Optional[str]]:
        """
        Attempt to resolve uncertainty via clarification.

        Returns:
            (resolved: bool, guidance_text: Optional[str])
            If resolved=True, guidance_text contains the injected system message.
            If resolved=False, max rounds exceeded or clarification unavailable.
        """
        # Check round limit
        if self.clarification_rounds >= self.MAX_CLARIFICATION_ROUNDS:
            logger.warning(
                f"Agent {self.agent.agentium_id}: Max clarification rounds ({self.MAX_CLARIFICATION_ROUNDS}) exceeded"
            )
            return False, None

        # Step 1: Consult immediate supervisor
        logger.info(
            f"Agent {self.agent.agentium_id}: Requesting clarification from supervisor "
            f"(round {self.clarification_rounds + 1}/{self.MAX_CLARIFICATION_ROUNDS})"
        )

        consult_result = ClarificationService.consult_supervisor(
            agent=self.agent,
            db=self.db,
            question=signal.suggested_question,
            context=f"Uncertainty detected: {signal.reason} in tools {signal.affected_tools}. Details: {signal.details}"
        )

        # Check if consultation provided useful guidance
        guidance = consult_result.get("guidance")
        if guidance and guidance.strip() and "cannot clarify" not in guidance.lower():
            self.clarification_rounds += 1
            formatted = self._format_guidance(consult_result, signal, source="supervisor")
            logger.info(f"Agent {self.agent.agentium_id}: Clarification resolved via supervisor")
            return True, formatted

        # Step 2: Escalate if supervisor couldn't help and escalation is available
        if consult_result.get("escalation_available"):
            logger.info(
                f"Agent {self.agent.agentium_id}: Supervisor unclear, escalating up hierarchy"
            )
            escalation_result = ClarificationService.escalate_clarification(
                agent=self.agent,
                question=signal.suggested_question,
                db=self.db,
                max_escalations=3
            )

            self.escalation_trail.append(escalation_result)

            # Check if escalation resolved
            if escalation_result.get("resolved"):
                # Find the step that achieved clarity
                for step in escalation_result.get("escalation_trail", []):
                    if step.get("result") == "clarity_achieved":
                        guidance = step.get("guidance")
                        if guidance:
                            self.clarification_rounds += 1
                            formatted = self._format_guidance(
                                {"guidance": guidance, "consulted": step.get("consulted"),
                                 "role": step.get("role")},
                                signal, source="escalation"
                            )
                            logger.info(
                                f"Agent {self.agent.agentium_id}: Clarification resolved via escalation "
                                f"to {step.get('role')}"
                            )
                            return True, formatted

        # No resolution found
        logger.warning(f"Agent {self.agent.agentium_id}: Clarification unresolved after escalation")
        return False, None

    def _format_guidance(
        self,
        result: Dict[str, Any],
        signal: UncertaintySignal,
        source: str
    ) -> str:
        """Format clarification result into a system message."""
        consulted = result.get("consulted", "unknown")
        role = result.get("role", result.get("parent_role", "supervisor"))
        guidance = result.get("guidance", "")
        your_purpose = result.get("your_purpose", "")
        task_history = result.get("task_history", [])
        recommendation = result.get("recommendation", "")

        parts = [
            f"CLARIFICATION FROM {role.upper()} ({consulted}) — {source}",
            f"Original uncertainty: {signal.reason} in tools {signal.affected_tools}",
            f"Guidance: {guidance}",
        ]

        if your_purpose:
            parts.append(f"Your purpose: {your_purpose}")

        if task_history:
            task_summary = "; ".join(
                f"{t['task_id']}: {t['title']} ({t['status']}, {t['progress']}%)"
                for t in task_history[:2]
            )
            parts.append(f"Recent tasks: {task_summary}")

        if recommendation:
            parts.append(f"Recommendation: {recommendation}")

        return "\n".join(parts)