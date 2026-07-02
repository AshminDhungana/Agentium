"""
Critic Agents Service for Agentium.

Ephemeral per-task critics: spawned by the orchestrator when a task is
delegated, terminated when the task completes (pass) or escalates (max
retries exhausted).

ID scheme
---------
  7xxxx  →  Code critics
  8xxxx  →  Output critics
  9xxxx  →  Plan critics

Each task gets its own critic instances (tracked via current_task_id).
The same instances survive retries so the critic has context from prior
rejections — no cold-start penalty on a retry.
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from backend.models.database import get_db_context
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.critics import (
    CriticAgent, CritiqueReview, CriticType, CriticVerdict, CRITIC_TYPE_TO_AGENT_TYPE
)
from backend.models.entities.task import Task, TaskStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.acceptance_criteria import (
    AcceptanceCriteriaService, AcceptanceCriterion, CriterionResult
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Which ID prefix each critic type uses
CRITIC_TYPE_TO_ID_PREFIX: Dict[CriticType, str] = {
    CriticType.CODE:   "7",
    CriticType.OUTPUT: "8",
    CriticType.PLAN:   "9",
}

# Which critics are spawned for each task type.
# Keys are task_type values (lower-cased).  Anything not listed falls back to
# DEFAULT_CRITIC_TYPES.
TASK_TYPE_CRITIC_MAP: Dict[str, List[CriticType]] = {
    "code":           [CriticType.CODE, CriticType.OUTPUT],
    "script":         [CriticType.CODE, CriticType.OUTPUT],
    "sql":            [CriticType.CODE, CriticType.OUTPUT],
    "function":       [CriticType.CODE, CriticType.OUTPUT],
    "plan":           [CriticType.PLAN],
    "dag":            [CriticType.PLAN],
    "strategy":       [CriticType.PLAN],
    "decompose":      [CriticType.PLAN],
    "predictive_planning": [CriticType.PLAN],
    "analysis":       [CriticType.OUTPUT, CriticType.PLAN],
    "research":       [CriticType.OUTPUT],
    "general":        [CriticType.OUTPUT],
}

DEFAULT_CRITIC_TYPES: List[CriticType] = [CriticType.OUTPUT]


class CriticService:
    """
    Orchestrates critic reviews on task outputs.

    Lifecycle
    ---------
    1. Orchestrator calls ``spawn_critics_for_task()`` before task execution.
    2. Task agent produces output.
    3. Orchestrator calls ``review_task_output()`` (once per spawned critic type).
    4. On PASS or ESCALATE, orchestrator calls ``terminate_critics_for_task()``.
    5. On REJECT, critics survive for the retry (same instances, retained context).
    """

    DEFAULT_MAX_RETRIES = 5
    CRITIC_DEFAULT_MODEL = "openai:gpt-4o-mini"

    # -------------------------------------------------------------------------
    # Spawn / terminate
    # -------------------------------------------------------------------------

    async def spawn_critics_for_task(
        self,
        db: Session,
        task_id: str,
        task_type: str,
        parent_agent_id: str = "00001",
    ) -> Dict[str, str]:
        """
        Spawn ephemeral critics appropriate for *task_type*.

        Returns a dict mapping CriticType.value → agentium_id for each
        critic that was successfully created.
        """
        task_str = (task_type or "general").lower()
        critic_types = TASK_TYPE_CRITIC_MAP.get(task_str, DEFAULT_CRITIC_TYPES)

        spawned: Dict[str, str] = {}
        for ct in critic_types:
            try:
                critic = await self._spawn_single_critic(db, ct, task_id, parent_agent_id)
                if critic:
                    spawned[ct.value] = critic.agentium_id
                    logger.info(
                        "Spawned %s critic %s for task %s",
                        ct.value, critic.agentium_id, task_id,
                    )
            except Exception as exc:
                logger.error("Failed to spawn %s critic for task %s: %s", ct.value, task_id, exc)

        if spawned:
            db.commit()
        return spawned

    async def _spawn_single_critic(
        self,
        db: Session,
        critic_type: CriticType,
        task_id: str,
        parent_agent_id: str,
    ) -> Optional[CriticAgent]:
        """Create one ephemeral critic and persist it."""
        prefix = CRITIC_TYPE_TO_ID_PREFIX[critic_type]

        # Next sequential ID for this prefix
        last = (
            db.query(CriticAgent)
            .filter(CriticAgent.agentium_id.like(f"{prefix}%"))
            .order_by(CriticAgent.agentium_id.desc())
            .first()
        )
        num = int(last.agentium_id[1:]) + 1 if last else 1
        new_id = f"{prefix}{num:04d}"

        # Fetch constitution version from the task
        task = db.query(Task).filter_by(id=task_id).first()
        constitution_version = (
            getattr(task, "constitution_version", None) or "v1.0.0"
        )

        critic = CriticAgent(
            agentium_id=new_id,
            name=f"{critic_type.value.title()} Critic {new_id}",
            description=(
                f"Ephemeral {critic_type.value} critic for task {task_id}. "
                "Terminates on task completion or escalation."
            ),
            critic_specialty=critic_type,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,       # ephemeral
            idle_mode_enabled=False,   # critics never idle
            constitution_version=constitution_version,
            preferred_review_model=self.CRITIC_DEFAULT_MODEL,
            current_task_id=task_id,   # tracks which task owns this critic
        )

        db.add(critic)
        db.flush()
        return critic

    async def terminate_critics_for_task(
        self, db: Session, task_id: str, reason: str = "task_completed"
    ) -> int:
        """
        Terminate all critics associated with *task_id*.

        Returns the number of critics terminated.
        """
        critics = (
            db.query(CriticAgent)
            .filter(
                CriticAgent.current_task_id == task_id,
                CriticAgent.is_active == True,
            )
            .all()
        )

        if not critics:
            return 0

        for c in critics:
            c.status = AgentStatus.TERMINATED
            c.is_active = False

        db.commit()

        logger.info(
            "Terminated %d critic(s) for task %s (reason: %s)",
            len(critics), task_id, reason,
        )
        return len(critics)

    def get_required_critic_types(self, task_type: str) -> List[CriticType]:
        """Return the list of critic types that should be spawned for a task type."""
        return TASK_TYPE_CRITIC_MAP.get((task_type or "general").lower(), DEFAULT_CRITIC_TYPES)

    # -------------------------------------------------------------------------
    # Review
    # -------------------------------------------------------------------------

    async def review_task_output(
        self,
        db: Session,
        task_id: str,
        output_content: str,
        critic_type: CriticType,
        subtask_id: Optional[str] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Submit a task output for critic review.

        Finds the ephemeral critic that was spawned for *task_id* with the
        matching *critic_type*.  Falls back to any available critic of that
        type if none was explicitly spawned (e.g. legacy call sites).
        """
        start_time = time.monotonic()

        # Find the critic assigned to this specific task
        critic = self._get_critic_for_task(db, critic_type, task_id)
        if not critic:
            # Fallback: any available critic (shouldn't happen in normal flow)
            critic = self._get_available_critic(db, critic_type)

        if not critic:
            return {
                "verdict": CriticVerdict.PASS.value,
                "message": f"No {critic_type.value} critic available — auto-passed",
                "auto_passed": True,
                "task_id": task_id,
            }

        original_status = critic.status
        critic.status = AgentStatus.REVIEWING

        output_hash = hashlib.sha256(output_content.encode()).hexdigest()

        # Deduplication check
        existing_review = db.query(CritiqueReview).filter(
            CritiqueReview.task_id == task_id,
            CritiqueReview.output_hash == output_hash,
            CritiqueReview.critic_type == critic_type,
        ).first()

        if existing_review:
            critic.status = original_status
            return {
                "verdict": existing_review.verdict.value,
                "message": "Duplicate output — returning cached review",
                "review_id": existing_review.id,
                "task_id": task_id,
                "cached": True,
            }

        # Acceptance criteria pre-check (Phase 6.3)
        task_for_criteria = db.query(Task).filter_by(id=task_id).first()
        task_criteria: list[AcceptanceCriterion] = []
        criteria_results: list[CriterionResult] = []
        if task_for_criteria and task_for_criteria.acceptance_criteria:
            task_criteria = AcceptanceCriteriaService.from_json(
                task_for_criteria.acceptance_criteria
            )

        if task_criteria:
            criteria_results = AcceptanceCriteriaService.evaluate_criteria(
                task_criteria, output_content, critic_type.value
            )
            aggregation = AcceptanceCriteriaService.aggregate(criteria_results)
            if not aggregation["all_mandatory_passed"]:
                failed_metrics = ", ".join(aggregation["mandatory_failures"])
                duration_ms = (time.monotonic() - start_time) * 1000
                review = CritiqueReview(
                    task_id=task_id,
                    subtask_id=subtask_id,
                    critic_type=critic_type,
                    critic_agentium_id=critic.agentium_id,
                    verdict=CriticVerdict.REJECT,
                    rejection_reason=f"Mandatory acceptance criteria failed: {failed_metrics}",
                    suggestions="Fix the criteria listed in criteria_results before resubmitting.",
                    retry_count=retry_count,
                    max_retries=self.DEFAULT_MAX_RETRIES,
                    review_duration_ms=duration_ms,
                    model_used=critic.preferred_review_model,
                    output_hash=output_hash,
                    criteria_results=[r.to_dict() for r in criteria_results],
                    criteria_evaluated=aggregation["total"],
                    criteria_passed=aggregation["passed"],
                    agentium_id=f"CR{critic.agentium_id}",
                )
                db.add(review)
                critic.record_review(CriticVerdict.REJECT, duration_ms)
                critic.status = original_status
                self._log_review(db, critic, task_id, CriticVerdict.REJECT,
                                 f"Mandatory criteria failed: {failed_metrics}")
                db.commit()
                return {
                    "verdict": CriticVerdict.REJECT.value,
                    "review_id": review.id,
                    "task_id": task_id,
                    "critic_id": critic.agentium_id,
                    "critic_type": critic_type.value,
                    "rejection_reason": f"Mandatory acceptance criteria failed: {failed_metrics}",
                    "suggestions": "Fix the criteria listed in criteria_results.",
                    "criteria_results": [r.to_dict() for r in criteria_results],
                    "criteria_summary": aggregation,
                    "retry_count": retry_count,
                    "max_retries": self.DEFAULT_MAX_RETRIES,
                    "review_duration_ms": round(duration_ms, 1),
                    "cached": False,
                }

        # AI model review
        verdict, reason, suggestions = await self._execute_review(
            db, critic, task_id, output_content, critic_type
        )

        duration_ms = (time.monotonic() - start_time) * 1000

        # Escalate if max retries exhausted
        if verdict == CriticVerdict.REJECT and retry_count >= self.DEFAULT_MAX_RETRIES:
            verdict = CriticVerdict.ESCALATE
            reason = f"Max retries ({self.DEFAULT_MAX_RETRIES}) exhausted. Original: {reason}"

        review = CritiqueReview(
            task_id=task_id,
            subtask_id=subtask_id,
            critic_type=critic_type,
            critic_agentium_id=critic.agentium_id,
            verdict=verdict,
            rejection_reason=reason if verdict != CriticVerdict.PASS else None,
            suggestions=suggestions,
            retry_count=retry_count,
            max_retries=self.DEFAULT_MAX_RETRIES,
            review_duration_ms=duration_ms,
            model_used=critic.preferred_review_model,
            output_hash=output_hash,
            criteria_results=[r.to_dict() for r in criteria_results] if criteria_results else None,
            criteria_evaluated=len(criteria_results) if criteria_results else None,
            criteria_passed=sum(1 for r in criteria_results if r.passed) if criteria_results else None,
            agentium_id=f"CR{critic.agentium_id}",
        )

        db.add(review)
        critic.record_review(verdict, duration_ms)
        critic.status = AgentStatus.ACTIVE
        self._log_review(db, critic, task_id, verdict, reason)
        db.commit()

        criteria_aggregation = (
            AcceptanceCriteriaService.aggregate(criteria_results)
            if criteria_results else None
        )
        result = {
            "verdict": verdict.value,
            "review_id": review.id,
            "task_id": task_id,
            "critic_id": critic.agentium_id,
            "critic_type": critic_type.value,
            "rejection_reason": reason if verdict != CriticVerdict.PASS else None,
            "suggestions": suggestions,
            "criteria_results": [r.to_dict() for r in criteria_results] if criteria_results else [],
            "criteria_summary": criteria_aggregation,
            "retry_count": retry_count,
            "max_retries": self.DEFAULT_MAX_RETRIES,
            "review_duration_ms": round(duration_ms, 1),
            "cached": False,
            "consensus_reached": True,
        }

        # Consensus protocol (first rejection only)
        if verdict == CriticVerdict.REJECT and retry_count == 0:
            secondary = self._get_critic_for_task(
                db, critic_type, task_id, exclude_id=critic.id
            )
            if secondary:
                logger.info(
                    "Consensus protocol: secondary critic %s re-evaluating",
                    secondary.agentium_id,
                )
                sec_verdict, _, _ = await self._execute_review(
                    db, secondary, task_id, output_content, critic_type
                )
                if sec_verdict == CriticVerdict.PASS:
                    logger.warning("Critic consensus failure — conditional pass")
                    result["verdict"] = CriticVerdict.PASS.value
                    result["consensus_reached"] = False
                    verdict = CriticVerdict.PASS

        # Case law indexing for hard rejections
        if verdict == CriticVerdict.REJECT:
            try:
                from backend.services.knowledge_service import get_knowledge_service
                knowledge = get_knowledge_service()
                case_law_content = (
                    f"REJECTED OUTPUT CASE LAW\n"
                    f"Task: {task_for_criteria.description if task_for_criteria else 'Unknown'}\n"
                    f"Reason for rejection: {reason}\n"
                    f"Critic actionable feedback: {suggestions}\n"
                    f"Do NOT repeat the mistakes found in this output pattern."
                )
                knowledge.store_or_revise_knowledge(
                    content=case_law_content,
                    collection_name="critic_case_law",
                    doc_id=f"case_law_{task_id}_{int(time.time())}",
                    metadata={"critic_type": critic_type.value, "task_id": task_id},
                )
            except Exception as exc:
                logger.error("Failed to index case law: %s", exc)

        if verdict == CriticVerdict.ESCALATE:
            result["escalation"] = await self._escalate_to_council(
                db, task_id, critic_type, reason
            )

        return result

    # -------------------------------------------------------------------------
    # Aggregate review (all spawned critics for a task)
    # -------------------------------------------------------------------------

    async def review_with_all_task_critics(
        self,
        db: Session,
        task_id: str,
        output_content: str,
        task_type: str,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Run output through ALL critics that were spawned for *task_id*.

        Returns the first non-PASS verdict (fail fast), or a PASS result
        once every critic approves.
        """
        task_str = (task_type or "general").lower()
        critic_types = TASK_TYPE_CRITIC_MAP.get(task_str, DEFAULT_CRITIC_TYPES)

        for ct in critic_types:
            result = await self.review_task_output(
                db=db,
                task_id=task_id,
                output_content=output_content,
                critic_type=ct,
                retry_count=retry_count,
            )
            if result.get("verdict") != CriticVerdict.PASS.value:
                result["blocking_critic_type"] = ct.value
                return result  # fail fast

        return {
            "verdict": CriticVerdict.PASS.value,
            "task_id": task_id,
            "reviewer_count": len(critic_types),
        }

    # -------------------------------------------------------------------------
    # Critic lookup
    # -------------------------------------------------------------------------

    def _get_critic_for_task(
        self,
        db: Session,
        critic_type: CriticType,
        task_id: str,
        exclude_id: Optional[str] = None,
    ) -> Optional[CriticAgent]:
        """Find the ephemeral critic spawned for a specific task and type."""
        agent_type = CRITIC_TYPE_TO_AGENT_TYPE[critic_type]

        q = db.query(CriticAgent).filter(
            CriticAgent.agent_type == agent_type,
            CriticAgent.is_active == True,
            CriticAgent.current_task_id == task_id,
            CriticAgent.status.in_([AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING]),
        )
        if exclude_id:
            q = q.filter(CriticAgent.id != exclude_id)

        return q.order_by(CriticAgent.reviews_completed.asc()).first()

    def _get_available_critic(
        self,
        db: Session,
        critic_type: CriticType,
        exclude_id: Optional[str] = None,
    ) -> Optional[CriticAgent]:
        """
        Fallback: find any available critic of *critic_type* (not task-specific).
        Used by legacy call sites that have not been migrated to spawn-based flow.
        """
        agent_type = CRITIC_TYPE_TO_AGENT_TYPE[critic_type]

        q = db.query(CriticAgent).filter(
            CriticAgent.agent_type == agent_type,
            CriticAgent.is_active == True,
            CriticAgent.status.in_([AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING]),
        )
        if exclude_id:
            q = q.filter(CriticAgent.id != exclude_id)

        return q.order_by(CriticAgent.reviews_completed.asc()).first()

    # -------------------------------------------------------------------------
    # AI review logic (unchanged from original)
    # -------------------------------------------------------------------------

    async def _execute_review(
        self,
        db: Session,
        critic: CriticAgent,
        task_id: str,
        output_content: str,
        critic_type: CriticType,
    ) -> tuple:
        """Run preflight check followed by AI review with rule-based fallback."""
        task = db.query(Task).filter_by(id=task_id).first()
        preflight_verdict, preflight_reason, preflight_suggestions = self._preflight_check(
            output_content, critic_type, task
        )
        if preflight_verdict == CriticVerdict.REJECT:
            return (preflight_verdict, preflight_reason, preflight_suggestions)

        try:
            return await self._ai_review(critic, task, output_content, critic_type)
        except Exception as exc:
            logger.warning(
                "AI review failed for task %s (%s critic): %s. Falling back to rule-based.",
                task_id, critic_type.value, exc,
            )
            return self._rule_based_review(output_content, critic_type, task)

    async def _ai_review(
        self,
        critic: CriticAgent,
        task: Optional[Task],
        output_content: str,
        critic_type: CriticType,
    ) -> tuple:
        """Call the AI model to review the output and return the parsed verdict."""
        from backend.services.model_provider import ModelService

        model_key = critic.preferred_review_model or self.CRITIC_DEFAULT_MODEL
        system_prompt = self._build_critic_system_prompt(critic_type)
        user_prompt = self._build_critic_user_prompt(critic_type, task, output_content)

        raw_response = await ModelService.generate(
            model_key=model_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=512,
            temperature=0.1,
        )
        return self._parse_ai_verdict(raw_response)

    def _build_critic_system_prompt(self, critic_type: CriticType) -> str:
        """Return the system prompt string for the given critic type."""
        role_descriptions = {
            CriticType.CODE: (
                "You are a senior code reviewer with a security and correctness focus. "
                "You NEVER write code yourself — only evaluate what you are given."
            ),
            CriticType.OUTPUT: (
                "You are a quality assurance specialist. "
                "Your job is to verify that an agent's output actually satisfies the user's intent."
            ),
            CriticType.PLAN: (
                "You are an execution plan auditor. "
                "You verify that plans are sound, non-circular, and achievable."
            ),
        }
        return f"""{role_descriptions[critic_type]}

Respond ONLY with a JSON object — no markdown, no preamble:
{{
  "verdict": "pass" | "reject",
  "reason": "<one concise sentence — null if pass>",
  "suggestions": "<one actionable fix — null if pass>"
}}"""

    def _build_critic_user_prompt(
        self,
        critic_type: CriticType,
        task: Optional[Task],
        output_content: str,
    ) -> str:
        """Return the user prompt string for the given critic type, task, and output."""
        task_context = (
            f"TASK DESCRIPTION:\n{task.description}\n\n"
            if task and task.description
            else "TASK DESCRIPTION: (not available)\n\n"
        )
        criteria_map = {
            CriticType.CODE: (
                "Evaluate for: syntax correctness, security (no eval/exec/shell injection), "
                "logic soundness, and absence of obvious bugs."
            ),
            CriticType.OUTPUT: (
                "Evaluate whether the output meaningfully addresses the task description. "
                "Reject if: empty, pure error traceback, or clearly off-topic."
            ),
            CriticType.PLAN: (
                "Evaluate the plan for: completeness, absence of circular steps, "
                "and achievability within reasonable scope (< 100 steps)."
            ),
        }
        return (
            f"{task_context}"
            f"EVALUATION CRITERIA:\n{criteria_map[critic_type]}\n\n"
            f"OUTPUT TO REVIEW:\n{output_content[:6000]}"
        )

    def _parse_ai_verdict(self, raw_response: str) -> tuple:
        """Parse the AI response and return a tuple of (verdict, reason, suggestions)."""
        import json, re

        cleaned = re.sub(r"```(?:json)?|```", "", raw_response).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Critic AI returned non-JSON: %s", raw_response[:200])
            return (CriticVerdict.PASS, None, "AI response was not valid JSON — manual review recommended")

        verdict_str = str(data.get("verdict", "pass")).lower()
        verdict = CriticVerdict.REJECT if verdict_str == "reject" else CriticVerdict.PASS
        reason = data.get("reason") or None
        suggestions = data.get("suggestions") or None
        return (verdict, reason, suggestions)

    def _preflight_check(self, content: str, critic_type: CriticType, task: Optional[Task]) -> tuple:
        """Dispatch to the appropriate rule-based review based on critic type."""
        if critic_type == CriticType.CODE:
            return self._review_code(content, task)
        elif critic_type == CriticType.OUTPUT:
            return self._review_output(content, task)
        elif critic_type == CriticType.PLAN:
            return self._review_plan(content, task)
        return (CriticVerdict.PASS, None, None)

    def _rule_based_review(self, content: str, critic_type: CriticType, task: Optional[Task]) -> tuple:
        """Run a rule-based review as a fallback when AI review fails."""
        return self._preflight_check(content, critic_type, task)

    def _review_code(self, content: str, task: Optional[Task]) -> tuple:
        """Check code output for dangerous patterns and obvious issues."""
        issues, suggestions = [], []
        dangerous_patterns = [
            "eval(", "exec(", "__import__", "os.system(", "subprocess.Popen(",
            "rm -rf", "DROP TABLE", "DELETE FROM", "; --",
        ]
        for p in dangerous_patterns:
            if p in content:
                issues.append(f"Dangerous pattern detected: '{p}'")
                suggestions.append(f"Remove or sandbox usage of '{p}'")
        if not content.strip():
            issues.append("Empty output")
        if len(content) > 100000:
            issues.append("Output exceeds 100K chars — may indicate unbounded generation")
            suggestions.append("Add output length constraints")
        if issues:
            return (CriticVerdict.REJECT, "; ".join(issues), "; ".join(suggestions) or None)
        return (CriticVerdict.PASS, None, None)

    def _review_output(self, content: str, task: Optional[Task]) -> tuple:
        """Check output for emptiness, error traces, and task relevance."""
        issues, suggestions = [], []
        if not content.strip():
            issues.append("Output is empty — does not fulfill any user intent")
            suggestions.append("Ensure the executor produces meaningful output")
        error_indicators = ["Traceback (most recent call last)", "Error:", "Exception:"]
        if sum(1 for i in error_indicators if i in content) >= 2:
            issues.append("Output appears to be an error traceback, not a valid result")
            suggestions.append("Fix the underlying error before resubmitting")
        if task and task.description:
            task_keywords = set(task.description.lower().split())
            output_keywords = set(content.lower().split()[:200])
            relevance = len(task_keywords & output_keywords) / max(len(task_keywords), 1)
            if relevance < 0.05 and len(task_keywords) > 5:
                issues.append("Output appears unrelated to the task description")
                suggestions.append("Ensure output addresses the task requirements")
        if issues:
            return (CriticVerdict.REJECT, "; ".join(issues), "; ".join(suggestions) or None)
        return (CriticVerdict.PASS, None, None)

    def _review_plan(self, content: str, task: Optional[Task]) -> tuple:
        """Check execution plan for completeness, duplicates, and length."""
        issues, suggestions = [], []
        if not content.strip():
            issues.append("Execution plan is empty")
            suggestions.append("Generate a valid plan with at least one step")
        lines = content.lower().split("\n")
        if len(lines) > 1:
            seen = set()
            for line in lines:
                stripped = line.strip()
                if stripped in seen and stripped:
                    issues.append(f"Duplicate step detected: '{stripped[:50]}'")
                    suggestions.append("Remove duplicate steps from the plan")
                    break
                seen.add(stripped)
        if len(lines) > 100:
            issues.append(f"Plan has {len(lines)} steps — may be over-engineered")
            suggestions.append("Simplify the plan to fewer, higher-level steps")
        if issues:
            return (CriticVerdict.REJECT, "; ".join(issues), "; ".join(suggestions) or None)
        return (CriticVerdict.PASS, None, None)

    # -------------------------------------------------------------------------
    # Escalation
    # -------------------------------------------------------------------------

    async def _escalate_to_council(
        self,
        db: Session,
        task_id: str,
        critic_type: CriticType,
        reason: str,
    ) -> Dict[str, Any]:
        """Escalate a rejected task to the Council for deliberation."""
        audit = AuditLog(
            level=AuditLevel.WARNING,
            category=AuditCategory.GOVERNANCE,
            actor_type="critic",
            actor_id=f"critic_{critic_type.value}",
            action="critic_escalation",
            target_type="task",
            target_id=task_id,
            description=(
                f"Task {task_id} escalated to Council after max retries. "
                f"Critic type: {critic_type.value}. Reason: {reason}"
            ),
            created_at=datetime.utcnow(),
            is_active=True,
        )
        db.add(audit)
        task = db.query(Task).filter_by(id=task_id).first()
        if task:
            task.status = TaskStatus.DELIBERATING
            task._log_status_change(
                "deliberating",
                f"critic_{critic_type.value}",
                f"Escalated by {critic_type.value} critic: {reason[:200]}",
            )
        db.commit()
        return {"escalated": True, "reason": reason, "task_status": "deliberating"}

    def _log_review(
        self,
        db: Session,
        critic: CriticAgent,
        task_id: str,
        verdict: CriticVerdict,
        reason: Optional[str],
    ):
        """Write an audit log entry for a critic review."""
        level = AuditLevel.INFO if verdict == CriticVerdict.PASS else AuditLevel.WARNING
        audit = AuditLog(
            level=level,
            category=AuditCategory.GOVERNANCE,
            actor_type="critic",
            actor_id=critic.agentium_id,
            action=f"critic_review_{verdict.value}",
            target_type="task",
            target_id=task_id,
            description=(
                f"Critic {critic.agentium_id} ({critic.critic_specialty.value}) "
                f"verdict: {verdict.value}"
                + (f" — {reason[:200]}" if reason else "")
            ),
            created_at=datetime.utcnow(),
        )
        db.add(audit)

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_reviews_for_task(self, db: Session, task_id: str) -> List[Dict[str, Any]]:
        """Return all active reviews associated with a task."""
        reviews = (
            db.query(CritiqueReview)
            .filter(CritiqueReview.task_id == task_id, CritiqueReview.is_active == True)
            .order_by(CritiqueReview.reviewed_at.desc())
            .all()
        )
        return [r.to_dict() for r in reviews]

    def get_critic_stats(self, db: Session) -> Dict[str, Any]:
        """Aggregate stats across all critic instances (including terminated ones)."""
        critics = db.query(CriticAgent).all()

        total_reviews = sum(c.reviews_completed for c in critics)
        total_vetoes = sum(c.vetoes_issued for c in critics)
        total_escalations = sum(c.escalations_issued for c in critics)
        active_count = sum(1 for c in critics if c.is_active)

        by_type: Dict[str, Any] = {}
        for c in critics:
            ct = c.critic_specialty.value
            if ct not in by_type:
                by_type[ct] = {
                    "count": 0, "active": 0, "reviews": 0,
                    "vetoes": 0, "escalations": 0, "approval_rate": 0.0,
                }
            by_type[ct]["count"] += 1
            by_type[ct]["active"] += 1 if c.is_active else 0
            by_type[ct]["reviews"] += c.reviews_completed
            by_type[ct]["vetoes"] += c.vetoes_issued
            by_type[ct]["escalations"] += c.escalations_issued

        for ct in by_type:
            r = by_type[ct]["reviews"]
            v = by_type[ct]["vetoes"]
            by_type[ct]["approval_rate"] = round(((r - v) / r) * 100, 1) if r > 0 else 0.0

        return {
            "total_critics": len(critics),
            "active_critics": active_count,
            "total_reviews": total_reviews,
            "total_vetoes": total_vetoes,
            "total_escalations": total_escalations,
            "overall_approval_rate": (
                round(((total_reviews - total_vetoes) / total_reviews) * 100, 1)
                if total_reviews > 0 else 0.0
            ),
            "by_type": by_type,
        }


# Singleton instance
critic_service = CriticService()