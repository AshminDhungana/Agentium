"""
Auto-Delegation Service for Agentium.
Phase 13.1 — Automatic Task Delegation Engine

Provides:
  ComplexityAnalyzer  — scores task complexity 1-10 using heuristics
  AgentRanker         — ranks agents by performance and load
  SubTaskBreaker      — decomposes complex tasks into sub-tasks via LLM
  SmartRetryRouter    — re-dispatches failed tasks avoiding broken agents
  CostAwareDelegator  — forces local models when budget is low
  DelegationEngine    — single entry point orchestrating the above
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session

from backend.models.entities.task import (
    Task, TaskStatus, TaskPriority, TaskType, TaskDependency
)
from backend.models.entities.agents import Agent, AgentStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Complexity Analyzer
# ═══════════════════════════════════════════════════════════

# Keywords that indicate higher complexity
COMPLEXITY_KEYWORDS_HIGH = {
    "deploy", "migrate", "refactor", "integrate", "architecture",
    "security", "authentication", "database", "distributed", "multi-step",
    "orchestrate", "pipeline", "workflow", "concurrent", "parallel",
}
COMPLEXITY_KEYWORDS_MED = {
    "api", "service", "endpoint", "configure", "optimize", "debug",
    "analyze", "transform", "validate", "process", "schedule",
}


class ComplexityAnalyzer:
    """
    Scores task complexity on a 1-10 scale using heuristics.
    No LLM calls — pure keyword analysis + metadata signals.
    """

    @staticmethod
    def score(task: Task) -> int:
        """
        Compute a complexity score for the given task.

        Signals:
          - High-complexity keywords in description: +2 each (max +4)
          - Medium-complexity keywords: +1 each (max +2)
          - CRITICAL/SOVEREIGN priority: +2
          - Description length > 500 chars: +1
          - Task type deliberation/research/analysis: +1
          - Has parent_task_id (sub-task of a complex workflow): -1
          - Base score: 2

        Returns:
            Integer score clamped to [1, 10]
        """
        score = 2  # base
        desc_lower = (task.description or "").lower()

        # High-complexity keywords
        high_hits = sum(1 for kw in COMPLEXITY_KEYWORDS_HIGH if kw in desc_lower)
        score += min(high_hits * 2, 4)

        # Medium-complexity keywords
        med_hits = sum(1 for kw in COMPLEXITY_KEYWORDS_MED if kw in desc_lower)
        score += min(med_hits, 2)

        # Priority signal
        if task.priority in (TaskPriority.CRITICAL, TaskPriority.SOVEREIGN):
            score += 2

        # Length signal
        if len(task.description or "") > 500:
            score += 1

        # Task type signal
        complex_types = {TaskType.RESEARCH, TaskType.ANALYSIS, TaskType.CONSTITUTIONAL}
        if task.task_type in complex_types:
            score += 1

        # Sub-task discount
        if task.parent_task_id:
            score -= 1

        return max(1, min(10, score))


# ═══════════════════════════════════════════════════════════
# Agent Ranker
# ═══════════════════════════════════════════════════════════

class AgentRanker:
    """
    Ranks eligible agents by combining error rate, current load,
    and circuit breaker state.

    Formula per agent: (1 - error_rate) * (1 / max(1, current_load))
    Agents with CB_OPEN are excluded entirely.
    """

    @staticmethod
    def rank(
        db: Session,
        required_tier: Optional[str] = None,
        excluded_agent_ids: Optional[List[str]] = None,
        circuit_breakers: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Tuple[Agent, float]]:
        """
        Return agents sorted by descending suitability score.

        Args:
            db: Database session
            required_tier: If set, only agents whose agentium_id starts with this digit
            excluded_agent_ids: Agents to skip (e.g. previously failed)
            circuit_breakers: Per-agent CB state dict from AgentOrchestrator

        Returns:
            List of (Agent, score) sorted best-first.
        """
        excluded = set(excluded_agent_ids or [])
        cb = circuit_breakers or {}

        query = db.query(Agent).filter(
            Agent.is_active == True,
            Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING]),
        )

        if required_tier:
            query = query.filter(Agent.agentium_id.startswith(required_tier))

        agents = query.all()

        scored: List[Tuple[Agent, float]] = []
        for agent in agents:
            if agent.agentium_id in excluded:
                continue

            # Check circuit breaker
            agent_cb = cb.get(agent.agentium_id, {})
            if agent_cb.get("state") == "open":
                continue

            # Error rate
            completed = getattr(agent, "tasks_completed_count", 0) or 0
            failed = getattr(agent, "tasks_failed_count", 0) or 0
            total = completed + failed
            error_rate = failed / total if total > 0 else 0.0

            # Current load: count of in-progress tasks assigned to this agent
            active_tasks = db.query(Task).filter(
                Task.assigned_task_agent_ids.contains([agent.agentium_id]),
                Task.status.in_([TaskStatus.IN_PROGRESS, TaskStatus.PENDING]),
                Task.is_active == True,
            ).count()

            # Score formula
            performance = 1.0 - error_rate
            load_factor = 1.0 / max(1, active_tasks)
            agent_score = performance * load_factor

            scored.append((agent, agent_score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


# ═══════════════════════════════════════════════════════════
# Sub-Task Breaker
# ═══════════════════════════════════════════════════════════

class SubTaskBreaker:
    """
    Decomposes complex tasks (complexity >= 7) into sub-tasks using LLM.
    Creates child Task records and TaskDependency rows.
    """

    @staticmethod
    async def decompose(
        task: Task,
        db: Session,
        max_subtasks: int = 5,
    ) -> List[Task]:
        """
        Decompose a complex task into sub-tasks via LLM.

        Returns:
            List of created child Task objects.
        """
        try:
            from backend.services.model_provider import ModelService
        except ImportError:
            logger.warning("SubTaskBreaker: ModelService not available, skipping decomposition")
            return []

        prompt = (
            f"Break down this task into {max_subtasks} or fewer sub-tasks. "
            f"Return a JSON array of objects with 'title' and 'description' keys.\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n\n"
            f"Respond ONLY with the JSON array, no other text."
        )

        try:
            # Use the Head of Council's config for decomposition
            head = db.query(Agent).filter_by(agentium_id="00001").first()
            if not head:
                logger.warning("SubTaskBreaker: Head agent not found, skipping")
                return []

            result = await ModelService.generate_with_agent(
                agent=head,
                user_message=prompt,
                db=db,
                system_prompt_override=(
                    "You are a task decomposition specialist. "
                    "Break complex tasks into concrete, actionable sub-tasks. "
                    "Return ONLY a valid JSON array."
                ),
            )

            content = result.get("content", "")

            # Parse JSON from response
            import json
            # Try to extract JSON array from response
            start = content.find("[")
            end = content.rfind("]") + 1
            if start == -1 or end == 0:
                logger.warning("SubTaskBreaker: No JSON array found in LLM response")
                return []

            subtask_data = json.loads(content[start:end])

            created_tasks: List[Task] = []
            for i, st_data in enumerate(subtask_data[:max_subtasks]):
                title = st_data.get("title", f"Sub-task {i + 1}")
                description = st_data.get("description", title)

                child = Task(
                    title=title,
                    description=description,
                    task_type=task.task_type,
                    priority=task.priority,
                    status=TaskStatus.PENDING,
                    created_by=task.created_by,
                    parent_task_id=task.id,
                    is_idle_task=False,
                )
                db.add(child)
                db.flush()

                # Create dependency link
                dep = TaskDependency(
                    agentium_id=f"DEP{uuid.uuid4().hex[:6].upper()}",
                    parent_task_id=task.id,
                    child_task_id=child.id,
                    dependency_order=i,
                    status="pending",
                )
                db.add(dep)

                created_tasks.append(child)

            db.flush()
            logger.info(
                f"SubTaskBreaker: decomposed task {task.agentium_id} into "
                f"{len(created_tasks)} sub-tasks"
            )
            return created_tasks

        except Exception as e:
            logger.error(f"SubTaskBreaker: decomposition failed: {e}")
            return []


# ═══════════════════════════════════════════════════════════
# Smart Retry Router
# ═══════════════════════════════════════════════════════════

class SmartRetryRouter:
    """
    Re-dispatches failed tasks to a different agent of the same tier,
    avoiding agents with CB_OPEN status and the agent that previously failed.
    """

    @staticmethod
    def reroute(
        task: Task,
        failed_agent_id: str,
        db: Session,
        circuit_breakers: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[Agent]:
        """
        Find a replacement agent for a failed task.

        Returns:
            Agent if a suitable replacement was found, None otherwise.
        """
        # Determine the tier from the failed agent
        tier = failed_agent_id[0] if failed_agent_id else "3"

        # Get previously failed agents for this task
        meta = task.delegation_metadata or {}
        previous_failures = meta.get("failed_agent_ids", [])
        if failed_agent_id not in previous_failures:
            previous_failures.append(failed_agent_id)

        ranked = AgentRanker.rank(
            db=db,
            required_tier=tier,
            excluded_agent_ids=previous_failures,
            circuit_breakers=circuit_breakers,
        )

        if not ranked:
            logger.warning(
                f"SmartRetryRouter: no available agents on tier {tier} "
                f"for task {task.agentium_id}"
            )
            return None

        best_agent, best_score = ranked[0]

        # Update delegation metadata
        meta["failed_agent_ids"] = previous_failures
        meta["retry_routed_to"] = best_agent.agentium_id
        meta["retry_routed_at"] = datetime.utcnow().isoformat()
        meta["retry_agent_score"] = round(best_score, 4)
        task.delegation_metadata = meta

        # Assign the new agent
        agents = task.assigned_task_agent_ids or []
        if not isinstance(agents, list):
            agents = []
        if best_agent.agentium_id not in agents:
            agents.append(best_agent.agentium_id)
        task.assigned_task_agent_ids = agents

        logger.info(
            f"SmartRetryRouter: rerouted task {task.agentium_id} "
            f"from {failed_agent_id} → {best_agent.agentium_id} (score: {best_score:.3f})"
        )
        return best_agent


# ═══════════════════════════════════════════════════════════
# Cost-Aware Delegator
# ═══════════════════════════════════════════════════════════

class CostAwareDelegator:
    """
    When budget is low, forces simple tasks to use local Ollama
    to conserve API tokens.
    """

    @staticmethod
    def should_force_local(task: Task, complexity_score: int) -> bool:
        """
        Check if the task should be forced to use a local model.

        Returns True when:
          - idle_budget remaining < 20%
          - AND complexity_score <= 3 (simple task)
        """
        try:
            from backend.services.token_optimizer import idle_budget
            status = idle_budget.get_budget_status()
            remaining = status.get("remaining_percentage", 100)

            if remaining < 20 and complexity_score <= 3:
                logger.info(
                    f"CostAwareDelegator: budget at {remaining}%, "
                    f"complexity {complexity_score} — forcing local model"
                )
                return True
        except Exception as e:
            logger.debug(f"CostAwareDelegator: could not check budget: {e}")

        return False


# ═══════════════════════════════════════════════════════════
# Delegation Engine (Orchestrator)
# ═══════════════════════════════════════════════════════════

class DelegationEngine:
    """
    Single entry point for the full auto-delegation pipeline:
      1. Score complexity
      2. (Optionally) decompose into sub-tasks
      3. Rank eligible agents
      4. Assign best agent
      5. Record decision trail in delegation_metadata
    """

    @staticmethod
    async def delegate(
        task: Task,
        db: Session,
        force: bool = False,
        circuit_breakers: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Run the full auto-delegation pipeline on a task.

        Args:
            task: The task to delegate
            db: Database session
            force: If True, re-run delegation even if already delegated
            circuit_breakers: Per-agent CB map from AgentOrchestrator

        Returns:
            Dict with delegation results.
        """
        result: Dict[str, Any] = {
            "task_id": task.id,
            "agentium_id": task.agentium_id,
            "delegated": False,
        }

        # Skip if already delegated (unless forced)
        if task.delegation_metadata and not force:
            result["skipped"] = "already_delegated"
            return result

        # Skip idle tasks
        if task.is_idle_task:
            result["skipped"] = "idle_task"
            return result

        # ── Step 1: Score complexity ──────────────────────────────────────────
        complexity = ComplexityAnalyzer.score(task)
        task.complexity_score = complexity
        result["complexity_score"] = complexity

        # ── Step 2: Decompose if complex ─────────────────────────────────────
        subtasks_created = 0
        if complexity >= 7:
            try:
                subtasks = await SubTaskBreaker.decompose(task, db)
                subtasks_created = len(subtasks)
                result["subtasks_created"] = subtasks_created
            except Exception as e:
                logger.warning(f"DelegationEngine: decomposition failed: {e}")
                result["decomposition_error"] = str(e)

        # ── Step 3: Cost-aware check ─────────────────────────────────────────
        force_local = CostAwareDelegator.should_force_local(task, complexity)
        result["force_local_model"] = force_local

        # ── Step 4: Determine tier ───────────────────────────────────────────
        if complexity >= 8:
            target_tier = "2"  # Lead agent for very complex tasks
        elif complexity >= 5:
            target_tier = "3"  # Task agent for medium complexity
        else:
            target_tier = "3"  # Task agent for simple tasks

        # ── Step 5: Rank and assign ──────────────────────────────────────────
        ranked = AgentRanker.rank(
            db=db,
            required_tier=target_tier,
            circuit_breakers=circuit_breakers,
        )

        assigned_agent = None
        if ranked:
            best_agent, best_score = ranked[0]
            assigned_agent = best_agent

            # Assign the agent
            agents = task.assigned_task_agent_ids or []
            if not isinstance(agents, list):
                agents = []
            if best_agent.agentium_id not in agents:
                agents.append(best_agent.agentium_id)
            task.assigned_task_agent_ids = agents

            result["assigned_to"] = best_agent.agentium_id
            result["agent_score"] = round(best_score, 4)
            result["candidate_count"] = len(ranked)
            result["candidates"] = [
                {"agentium_id": a.agentium_id, "score": round(s, 4)}
                for a, s in ranked[:5]
            ]
        else:
            result["assigned_to"] = None
            result["candidate_count"] = 0
            logger.warning(
                f"DelegationEngine: no agents available for tier {target_tier}"
            )

        # ── Step 6: Record decision trail ────────────────────────────────────
        decision = {
            "delegated_at": datetime.utcnow().isoformat(),
            "complexity_score": complexity,
            "target_tier": target_tier,
            "force_local_model": force_local,
            "subtasks_created": subtasks_created,
            "assigned_to": result.get("assigned_to"),
            "agent_score": result.get("agent_score"),
            "candidate_count": result.get("candidate_count", 0),
            "candidates": result.get("candidates", []),
            "forced": force,
        }

        # Merge with existing metadata if re-delegating
        existing = task.delegation_metadata or {}
        history = existing.get("history", [])
        if existing.get("delegated_at"):
            history.append({k: v for k, v in existing.items() if k != "history"})
        decision["history"] = history

        task.delegation_metadata = decision

        result["delegated"] = assigned_agent is not None
        result["delegation_metadata"] = decision

        # ── Audit log ────────────────────────────────────────────────────────
        try:
            AuditLog.log(
                level=AuditLevel.INFO,
                category=AuditCategory.GOVERNANCE,
                actor_type="system",
                actor_id="DELEGATION_ENGINE",
                action="auto_delegation",
                target_type="task",
                target_id=task.id,
                description=(
                    f"Auto-delegated task {task.agentium_id} "
                    f"(complexity={complexity}, tier={target_tier}, "
                    f"agent={result.get('assigned_to', 'none')})"
                ),
                meta_data=decision,
            )
        except Exception:
            pass  # Audit failure should not break delegation

        db.flush()
        logger.info(
            f"DelegationEngine: task {task.agentium_id} — "
            f"complexity={complexity}, tier={target_tier}, "
            f"assigned={result.get('assigned_to', 'none')}, "
            f"subtasks={subtasks_created}"
        )

        return result
