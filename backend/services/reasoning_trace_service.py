"""
ReasoningTraceService for Agentium.

Adds structured, step-by-step internal reasoning traces to agent execution.
Addresses Issue #6: Agent Self-Reasoning Flow Needs Improvement.

Integration points:
  - AgentOrchestrator.execute_task()  → wrap with trace
  - SkillRAG.execute_with_skills()    → inject trace steps
  - CriticService.review_task_output() → outcome validation before completion

Trace lifecycle:
  1. GOAL_INTERPRETATION   — parse and restate the task goal
  2. CONTEXT_RETRIEVAL     — what RAG / skills / history were loaded
  3. PLAN_GENERATION       — ordered steps the agent intends to take
  4. STEP_EXECUTION        — one entry per plan step (decision + outcome)
  5. OUTCOME_VALIDATION    — check output satisfies the original goal
  6. COMPLETION / FAILURE  — final sealed trace

Each trace is persisted to the DB (ReasoningTrace + ReasoningStep tables)
AND broadcast over WebSocket so the frontend can stream the agent's thinking
in real time.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enums & Data Classes
# ─────────────────────────────────────────────────────────────────────────────

class TracePhase(str, Enum):
    GOAL_INTERPRETATION = "goal_interpretation"
    CONTEXT_RETRIEVAL   = "context_retrieval"
    PLAN_GENERATION     = "plan_generation"
    STEP_EXECUTION      = "step_execution"
    OUTCOME_VALIDATION  = "outcome_validation"
    COMPLETED           = "completed"
    FAILED              = "failed"


class StepOutcome(str, Enum):
    PENDING   = "pending"
    SUCCESS   = "success"
    SKIPPED   = "skipped"
    FAILED    = "failed"
    RETRIED   = "retried"


@dataclass
class ReasoningStep:
    """A single step within a reasoning trace."""
    step_id:        str
    phase:          TracePhase
    sequence:       int                        # Order within the trace
    description:    str                        # What this step is doing
    rationale:      str                        # Why this step was chosen
    alternatives:   List[str] = field(default_factory=list)   # Other options considered
    inputs:         Dict[str, Any] = field(default_factory=dict)
    outputs:        Dict[str, Any] = field(default_factory=dict)
    outcome:        StepOutcome = StepOutcome.PENDING
    error:          Optional[str] = None
    duration_ms:    float = 0.0
    started_at:     str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at:   Optional[str] = None
    tokens_used:    int = 0

    def complete(self, outcome: StepOutcome, outputs: Dict[str, Any] = None,
                 error: str = None, tokens: int = 0):
        self.outcome      = outcome
        self.outputs      = outputs or {}
        self.error        = error
        self.tokens_used  = tokens
        self.completed_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["phase"]   = self.phase.value
        d["outcome"] = self.outcome.value
        return d


@dataclass
class ReasoningTrace:
    """Full trace for one task execution by one agent."""
    trace_id:       str
    task_id:        str
    agent_id:       str
    agent_tier:     int
    goal:           str                        # Original task description
    goal_restated:  str = ""                   # Agent's own rephrasing
    current_phase:  TracePhase = TracePhase.GOAL_INTERPRETATION
    steps:          List[ReasoningStep] = field(default_factory=list)
    plan:           List[str] = field(default_factory=list)   # High-level intended steps
    skills_used:    List[str] = field(default_factory=list)
    context_summary: str = ""
    final_outcome:  Optional[str] = None       # "success" | "failure"
    failure_reason: Optional[str] = None
    validation_passed: Optional[bool] = None
    validation_notes:  str = ""
    total_tokens:   int = 0
    total_duration_ms: float = 0.0
    started_at:     str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at:   Optional[str] = None
    incarnation:    int = 1

    # ── Step helpers ──────────────────────────────────────────────────────────

    def add_step(
        self,
        phase: TracePhase,
        description: str,
        rationale: str,
        alternatives: List[str] = None,
        inputs: Dict[str, Any] = None,
    ) -> ReasoningStep:
        step = ReasoningStep(
            step_id=f"{self.trace_id}_s{len(self.steps) + 1:03d}",
            phase=phase,
            sequence=len(self.steps) + 1,
            description=description,
            rationale=rationale,
            alternatives=alternatives or [],
            inputs=inputs or {},
        )
        self.steps.append(step)
        self.current_phase = phase
        return step

    def latest_step(self) -> Optional[ReasoningStep]:
        return self.steps[-1] if self.steps else None

    def seal(self, success: bool, reason: str = ""):
        self.final_outcome  = "success" if success else "failure"
        self.failure_reason = reason if not success else None
        self.current_phase  = TracePhase.COMPLETED if success else TracePhase.FAILED
        self.completed_at   = datetime.utcnow().isoformat()
        self.total_tokens   = sum(s.tokens_used for s in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["current_phase"] = self.current_phase.value
        d["steps"] = [s.to_dict() for s in self.steps]
        return d

    def summary(self) -> Dict[str, Any]:
        """Compact summary for logging / WebSocket broadcast."""
        return {
            "trace_id":          self.trace_id,
            "task_id":           self.task_id,
            "agent_id":          self.agent_id,
            "current_phase":     self.current_phase.value,
            "steps_completed":   sum(1 for s in self.steps if s.outcome != StepOutcome.PENDING),
            "total_steps":       len(self.steps),
            "plan_steps":        len(self.plan),
            "final_outcome":     self.final_outcome,
            "validation_passed": self.validation_passed,
            "total_tokens":      self.total_tokens,
            "total_duration_ms": round(self.total_duration_ms, 1),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Outcome Validator
# ─────────────────────────────────────────────────────────────────────────────

class OutcomeValidator:
    """
    Deterministic validation checks run BEFORE marking a task complete.
    Lightweight — no extra LLM call unless needed.

    Checks (in order):
      1. Non-empty output
      2. No raw error traceback
      3. Minimum keyword overlap with original goal
      4. Output length sanity (not unbounded)
    """

    MIN_KEYWORD_OVERLAP = 0.05   # 5 % overlap between goal words and output words
    MAX_OUTPUT_CHARS    = 200_000
    MIN_OUTPUT_CHARS    = 10

    @classmethod
    def validate(
        cls,
        goal: str,
        output: str,
        task_type: str = "general",
    ) -> Tuple[bool, str, List[str]]:
        """
        Returns (passed: bool, summary: str, issues: List[str]).
        """
        issues: List[str] = []

        # 1. Non-empty
        if not output or len(output.strip()) < cls.MIN_OUTPUT_CHARS:
            issues.append("Output is empty or too short to be meaningful.")

        # 2. Error traceback check
        traceback_markers = ["Traceback (most recent call last)", "Error:", "Exception:"]
        hits = sum(1 for m in traceback_markers if m in output)
        if hits >= 2:
            issues.append(
                "Output looks like an error traceback rather than a task result."
            )

        # 3. Keyword overlap with goal
        goal_words   = set(goal.lower().split())
        output_words = set(output.lower().split()[:300])   # First 300 words
        if goal_words:
            overlap = len(goal_words & output_words) / len(goal_words)
            if overlap < cls.MIN_KEYWORD_OVERLAP and len(goal_words) > 5:
                issues.append(
                    f"Output may be unrelated to the goal "
                    f"(keyword overlap: {overlap:.1%})."
                )

        # 4. Size sanity
        if len(output) > cls.MAX_OUTPUT_CHARS:
            issues.append(
                f"Output is extremely long ({len(output):,} chars). "
                "Possible unbounded generation."
            )

        passed  = len(issues) == 0
        summary = "All validation checks passed." if passed else "; ".join(issues)
        return passed, summary, issues


# ─────────────────────────────────────────────────────────────────────────────
# ReasoningTraceService
# ─────────────────────────────────────────────────────────────────────────────

class ReasoningTraceService:
    """
    Central service for structured agent reasoning traces.

    Usage (in AgentOrchestrator.execute_task):

        async with reasoning_trace_service.trace(task, agent, db) as trace:
            # Phase 1 – interpret goal
            step = trace.add_step(
                phase=TracePhase.GOAL_INTERPRETATION,
                description="Interpreting task goal",
                rationale="Re-state goal to confirm understanding before acting",
            )
            ... do goal interpretation ...
            step.complete(StepOutcome.SUCCESS, outputs={"restated_goal": ...})

            # Phase 2 – retrieve context / skills
            ...

            # Phase 3 – generate plan
            ...

            # Phase 4 – execute steps
            ...

            # Phase 5 – validate outcome  ← NEW: REQUIRED before completion
            validated = reasoning_trace_service.validate_outcome(trace, output)
            if not validated:
                raise ValueError("Outcome validation failed")

    The `trace()` context manager auto-seals and persists on exit.
    """

    # In-memory store for active traces (keyed by trace_id).
    # Production: back with Redis or the DB ReasoningTrace table.
    _active_traces: Dict[str, ReasoningTrace] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def create_trace(
        self,
        task_id: str,
        agent_id: str,
        goal: str,
        incarnation: int = 1,
    ) -> ReasoningTrace:
        """Create and register a new trace for a task execution."""
        trace = ReasoningTrace(
            trace_id=f"rt_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            agent_id=agent_id,
            agent_tier=int(agent_id[0]) if agent_id and agent_id[0].isdigit() else 3,
            goal=goal,
            incarnation=incarnation,
        )
        self._active_traces[trace.trace_id] = trace
        logger.info(
            "[Trace %s] Started for task=%s agent=%s",
            trace.trace_id, task_id, agent_id,
        )
        return trace

    @asynccontextmanager
    async def trace(
        self,
        task_id: str,
        agent_id: str,
        goal: str,
        db: Session,
        incarnation: int = 1,
    ):
        """
        Async context manager that wraps a full task execution with a trace.
        Auto-seals (success or failure) and persists to DB on exit.

        Example:
            async with reasoning_trace_service.trace(task.id, agent.agentium_id,
                                                      task.description, db) as t:
                ... execute task using t.add_step(...) ...
        """
        t = self.create_trace(task_id, agent_id, goal, incarnation)
        wall_start = time.monotonic()
        try:
            yield t
            # Auto-seal as success if no exception
            if t.final_outcome is None:
                t.seal(success=True)
        except Exception as exc:
            t.seal(success=False, reason=str(exc))
            raise
        finally:
            t.total_duration_ms = (time.monotonic() - wall_start) * 1000
            await self._persist(t, db)
            await self._broadcast(t)
            self._active_traces.pop(t.trace_id, None)

    # ── Phase helpers (called from orchestrator / skill_rag) ──────────────────

    def record_goal_interpretation(
        self,
        trace: ReasoningTrace,
        restated_goal: str,
        key_entities: List[str] = None,
        ambiguities: List[str] = None,
    ) -> ReasoningStep:
        """Record how the agent understood and restated the goal."""
        trace.goal_restated = restated_goal
        step = trace.add_step(
            phase=TracePhase.GOAL_INTERPRETATION,
            description="Interpret and restate the task goal",
            rationale="Confirming goal understanding before planning reduces wasted effort.",
            inputs={"original_goal": trace.goal},
        )
        step.complete(
            StepOutcome.SUCCESS,
            outputs={
                "restated_goal": restated_goal,
                "key_entities":  key_entities or [],
                "ambiguities":   ambiguities or [],
            },
        )
        logger.debug("[Trace %s] Goal interpreted: %s", trace.trace_id, restated_goal[:120])
        return step

    def record_context_retrieval(
        self,
        trace: ReasoningTrace,
        skills_found: List[Dict[str, Any]],
        rag_docs: int = 0,
        history_entries: int = 0,
    ) -> ReasoningStep:
        """Record what context / skills were loaded."""
        skill_names = [s.get("name", s.get("skill_id", "?")) for s in skills_found]
        trace.skills_used = skill_names
        trace.context_summary = (
            f"{len(skills_found)} skills, {rag_docs} RAG docs, "
            f"{history_entries} history entries"
        )
        step = trace.add_step(
            phase=TracePhase.CONTEXT_RETRIEVAL,
            description="Retrieve relevant skills and context",
            rationale=(
                "Skills from the knowledge library guide execution and "
                "reduce trial-and-error. RAG context grounds the response."
            ),
            inputs={"goal": trace.goal_restated or trace.goal},
        )
        step.complete(
            StepOutcome.SUCCESS,
            outputs={
                "skills_found": skill_names,
                "rag_docs":     rag_docs,
                "history":      history_entries,
            },
        )
        logger.debug(
            "[Trace %s] Context loaded: %s skills, %d RAG docs",
            trace.trace_id, skill_names, rag_docs,
        )
        return step

    def record_plan_generation(
        self,
        trace: ReasoningTrace,
        plan_steps: List[str],
        strategy: str = "",
        alternatives_considered: List[str] = None,
    ) -> ReasoningStep:
        """Record the multi-step plan the agent intends to follow."""
        trace.plan = plan_steps
        step = trace.add_step(
            phase=TracePhase.PLAN_GENERATION,
            description=f"Generate {len(plan_steps)}-step execution plan",
            rationale=(
                strategy or
                "Breaking the task into ordered steps allows for incremental "
                "progress tracking and targeted retries on failure."
            ),
            alternatives=alternatives_considered or [],
            inputs={"goal": trace.goal_restated or trace.goal, "skills": trace.skills_used},
        )
        step.complete(
            StepOutcome.SUCCESS,
            outputs={"plan": plan_steps, "step_count": len(plan_steps)},
        )
        logger.info(
            "[Trace %s] Plan generated (%d steps): %s",
            trace.trace_id, len(plan_steps),
            " → ".join(plan_steps[:5]) + ("..." if len(plan_steps) > 5 else ""),
        )
        return step

    def record_step_execution(
        self,
        trace: ReasoningTrace,
        step_name: str,
        decision: str,
        inputs: Dict[str, Any] = None,
        alternatives: List[str] = None,
    ) -> ReasoningStep:
        """
        Record a single plan-step execution decision.
        Call `.complete()` on the returned step when the step finishes.
        """
        step = trace.add_step(
            phase=TracePhase.STEP_EXECUTION,
            description=step_name,
            rationale=decision,
            alternatives=alternatives or [],
            inputs=inputs or {},
        )
        logger.debug(
            "[Trace %s] Step %d starting: %s",
            trace.trace_id, step.sequence, step_name,
        )
        return step

    def validate_outcome(
        self,
        trace: ReasoningTrace,
        output: str,
        task_type: str = "general",
    ) -> bool:
        """
        Run deterministic outcome validation and record as a trace step.
        Returns True if output passes validation.

        MUST be called before marking a task complete.
        """
        passed, summary, issues = OutcomeValidator.validate(
            goal=trace.goal_restated or trace.goal,
            output=output,
            task_type=task_type,
        )

        trace.validation_passed = passed
        trace.validation_notes  = summary

        step = trace.add_step(
            phase=TracePhase.OUTCOME_VALIDATION,
            description="Validate output against original goal",
            rationale=(
                "Outcome validation prevents incomplete or erroneous results "
                "from being marked complete, triggering retry if needed."
            ),
            inputs={"goal": trace.goal, "output_length": len(output)},
        )
        step.complete(
            outcome=StepOutcome.SUCCESS if passed else StepOutcome.FAILED,
            outputs={
                "passed":  passed,
                "summary": summary,
                "issues":  issues,
            },
        )

        if passed:
            logger.info("[Trace %s] Outcome validation PASSED.", trace.trace_id)
        else:
            logger.warning(
                "[Trace %s] Outcome validation FAILED: %s", trace.trace_id, summary
            )

        return passed

    # ── Query / retrieval ─────────────────────────────────────────────────────

    def get_active_trace(self, trace_id: str) -> Optional[ReasoningTrace]:
        return self._active_traces.get(trace_id)

    def check_stalled_traces(
        self,
        db,
        timeout_seconds: float = 120.0,
    ) -> List[Dict[str, Any]]:
        """
        Scan all active in-memory traces and seal any that have been stuck
        (no step progress) for longer than *timeout_seconds*.

        For each stalled trace:
          - Seals it as FAILED with reason "stalled".
          - Emits a ``trace_stalled`` WebSocket event carrying ``task_id``
            and the last known ethos snapshot from the agent's working memory.

        Returns a list of dicts, one per stalled trace:
          {"trace_id", "task_id", "agent_id", "last_activity_at", "age_seconds"}

        Called by the ``check_stalled_reasoning`` Celery beat task every 60 s.
        """
        now = datetime.utcnow()
        stalled: List[Dict[str, Any]] = []

        # Iterate over a snapshot so we can mutate _active_traces inside the loop
        for trace_id, trace in list(self._active_traces.items()):
            # Skip already-terminal traces (they should have been removed, but be safe)
            if trace.current_phase in (TracePhase.COMPLETED, TracePhase.FAILED):
                self._active_traces.pop(trace_id, None)
                continue

            # Determine the timestamp of the most recent activity
            last_step = trace.latest_step()
            if last_step:
                # Prefer the step's own started_at (always set) over completed_at
                ts_str = last_step.started_at
            else:
                ts_str = trace.started_at

            try:
                last_activity = datetime.fromisoformat(ts_str.rstrip("Z"))
            except (ValueError, AttributeError):
                continue

            age_seconds = (now - last_activity).total_seconds()
            if age_seconds < timeout_seconds:
                continue

            # ── This trace is stalled ─────────────────────────────────────
            logger.warning(
                "[Watchdog] Trace %s for task=%s agent=%s stalled for %.0f s — sealing.",
                trace_id, trace.task_id, trace.agent_id, age_seconds,
            )

            trace.seal(success=False, reason="stalled")
            stalled.append({
                "trace_id":        trace_id,
                "task_id":         trace.task_id,
                "agent_id":        trace.agent_id,
                "last_activity_at": ts_str,
                "age_seconds":     round(age_seconds, 1),
            })

            # Emit WebSocket event (best-effort, non-fatal)
            try:
                import asyncio
                from backend.api.routes.websocket import manager

                # Attempt to fetch the agent's ethos snapshot for the event payload
                ethos_snapshot: Dict[str, Any] = {}
                try:
                    from backend.models.entities.agents import Agent
                    agent_row = db.query(Agent).filter_by(
                        agentium_id=trace.agent_id, is_active=True
                    ).first()
                    if agent_row and agent_row.ethos:
                        ethos_snapshot = {
                            "mission_statement": getattr(agent_row.ethos, "mission_statement", ""),
                            "working_memory":    getattr(agent_row.ethos, "working_memory", {}),
                        }
                except Exception as ethos_exc:
                    logger.debug("[Watchdog] Could not load ethos for %s: %s", trace.agent_id, ethos_exc)

                event = {
                    "event_type":  "trace_stalled",
                    "timestamp":   now.isoformat(),
                    "trace_id":    trace_id,
                    "task_id":     trace.task_id,
                    "agent_id":    trace.agent_id,
                    "age_seconds": round(age_seconds, 1),
                    "ethos":       ethos_snapshot,
                }

                # broadcast() is a coroutine; run it safely from a sync context
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(manager.broadcast(event))
                    else:
                        loop.run_until_complete(manager.broadcast(event))
                except RuntimeError:
                    # No event loop — skip broadcast gracefully
                    pass
            except Exception as ws_exc:
                logger.debug("[Watchdog] WebSocket broadcast skipped: %s", ws_exc)

            # Remove from active registry
            self._active_traces.pop(trace_id, None)

        if stalled:
            logger.info("[Watchdog] Sealed %d stalled trace(s).", len(stalled))
        return stalled

    def get_traces_for_task(self, task_id: str, db: Session) -> List[Dict[str, Any]]:
        """
        Retrieve all persisted traces for a task from the DB.
        Falls back gracefully if the table doesn't exist yet.
        """
        try:
            from backend.models.entities.reasoning_trace import ReasoningTraceModel
            rows = (
                db.query(ReasoningTraceModel)
                .filter_by(task_id=task_id)
                .order_by(ReasoningTraceModel.started_at.desc())
                .all()
            )
            return [r.to_dict() for r in rows]
        except Exception as exc:
            logger.warning("Could not load traces from DB: %s", exc)
            return []

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _persist(self, trace: ReasoningTrace, db: Session):
        """
        Persist a sealed trace to the database.
        Uses a soft-fail so analytics never breaks the main execution path.
        """
        try:
            from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
            audit = AuditLog(
                level=AuditLevel.INFO if trace.final_outcome == "success" else AuditLevel.WARNING,
                category=AuditCategory.GOVERNANCE,
                actor_type="agent",
                actor_id=trace.agent_id,
                action="reasoning_trace_completed",
                target_type="task",
                target_id=trace.task_id,
                description=(
                    f"Agent {trace.agent_id} completed task {trace.task_id} "
                    f"in {len(trace.steps)} steps. "
                    f"Outcome: {trace.final_outcome}. "
                    f"Validation: {'passed' if trace.validation_passed else 'failed'}."
                ),
                after_state=trace.summary(),
                is_active=True,
                created_at=datetime.utcnow(),
                agentium_id=trace.trace_id,
            )
            db.add(audit)
            db.commit()
            logger.debug("[Trace %s] Persisted to audit log.", trace.trace_id)
        except Exception as exc:
            logger.error("[Trace %s] Failed to persist: %s", trace.trace_id, exc)
            try:
                db.rollback()
            except Exception:
                pass

    async def _broadcast(self, trace: ReasoningTrace):
        """
        Broadcast sealed trace summary over WebSocket.
        Non-fatal if WebSocket manager is unavailable.
        """
        try:
            from backend.api.routes.websocket import manager
            await manager.broadcast({
                "event_type": "reasoning_trace",
                "timestamp":  datetime.utcnow().isoformat(),
                "trace":      trace.summary(),
                "steps": [
                    {
                        "step_id":     s.step_id,
                        "phase":       s.phase.value,
                        "sequence":    s.sequence,
                        "description": s.description,
                        "rationale":   s.rationale[:200],
                        "outcome":     s.outcome.value,
                        "duration_ms": round(s.duration_ms, 1),
                    }
                    for s in trace.steps
                ],
            })
        except Exception as exc:
            logger.debug("[Trace %s] WebSocket broadcast skipped: %s", trace.trace_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Integration patches
# ─────────────────────────────────────────────────────────────────────────────

class TracedSkillRAG:
    """
    Drop-in replacement for SkillRAG.execute_with_skills() that injects
    a full reasoning trace around the RAG execution pipeline.

    Usage (in task_executor.py or agent_orchestrator.py):

        from backend.services.reasoning_trace_service import TracedSkillRAG
        result = await TracedSkillRAG.execute(
            task=task, agent=agent, db=db, model_config_id=config_id
        )
    """

    @staticmethod
    async def execute(
        task,          # Task entity
        agent,         # Agent entity
        db: Session,
        model_config_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Traced version of SkillRAG.execute_with_skills()."""
        from backend.services.skill_rag import skill_rag

        task_description = task.description or ""
        task_id          = task.agentium_id
        agent_id         = agent.agentium_id

        async with reasoning_trace_service.trace(
            task_id=task_id,
            agent_id=agent_id,
            goal=task_description,
            db=db,
        ) as trace:

            # ── Phase 1: Goal Interpretation ──────────────────────────────────
            reasoning_trace_service.record_goal_interpretation(
                trace,
                restated_goal=f"Execute: {task_description[:300]}",
                key_entities=_extract_key_entities(task_description),
            )

            # ── Phase 2: Context / Skill Retrieval ────────────────────────────
            skills = skill_rag.skill_manager.search_skills(
                query=task_description,
                agent_tier=agent.agent_type.value,
                db=db,
                n_results=3,
                min_success_rate=0.7,
            )
            reasoning_trace_service.record_context_retrieval(
                trace,
                skills_found=[
                    {"name": s["metadata"].get("display_name"), "skill_id": s["skill_id"]}
                    for s in skills
                ],
            )

            # ── Phase 3: Plan Generation ──────────────────────────────────────
            skill_names = [s["metadata"].get("display_name", "?") for s in skills]
            plan_steps  = _derive_plan_from_skills(task_description, skill_names)
            reasoning_trace_service.record_plan_generation(
                trace,
                plan_steps=plan_steps,
                strategy=f"Using {len(skills)} retrieved skills to guide execution.",
            )

            # ── Phase 4: Step Execution ───────────────────────────────────────
            exec_step = reasoning_trace_service.record_step_execution(
                trace,
                step_name="Execute task via SkillRAG pipeline",
                decision=(
                    "Delegate to ModelService with RAG-augmented prompt. "
                    "Skills provide proven patterns; model handles task-specific logic."
                ),
                inputs={"skills": skill_names, "model_config": model_config_id},
                alternatives=["Direct model call without skills", "Manual step-by-step execution"],
            )

            exec_start = time.monotonic()
            rag_result = await skill_rag.execute_with_skills(
                task_description=task_description,
                agent=agent,
                db=db,
                model_config_id=model_config_id,
            )
            exec_step.duration_ms = (time.monotonic() - exec_start) * 1000
            exec_step.complete(
                outcome=StepOutcome.SUCCESS,
                outputs={
                    "model":       rag_result.get("model"),
                    "tokens_used": rag_result.get("tokens_used", 0),
                    "skills_used": [s.get("name") for s in rag_result.get("skills_used", [])],
                },
                tokens=rag_result.get("tokens_used", 0),
            )

            # ── Phase 5: Outcome Validation ───────────────────────────────────
            output_content = rag_result.get("content", "")
            task_type      = _infer_task_type(task)
            passed = reasoning_trace_service.validate_outcome(
                trace, output_content, task_type
            )

            if not passed:
                trace.seal(
                    success=False,
                    reason=f"Outcome validation failed: {trace.validation_notes}",
                )
                rag_result["validation_passed"] = False
                rag_result["validation_notes"]  = trace.validation_notes
                rag_result["trace_id"]           = trace.trace_id
                return rag_result

            # ── Seal success ──────────────────────────────────────────────────
            trace.seal(success=True)
            rag_result["validation_passed"] = True
            rag_result["trace_id"]           = trace.trace_id
            return rag_result


# ─────────────────────────────────────────────────────────────────────────────
# Small utility functions
# ─────────────────────────────────────────────────────────────────────────────

def _extract_key_entities(text: str) -> List[str]:
    """Very lightweight entity extraction (no NLP dep required)."""
    words = text.split()
    # Return capitalised words as rough entity proxies
    entities = [w.strip(".,;:!?") for w in words if w and w[0].isupper() and len(w) > 2]
    return list(dict.fromkeys(entities))[:10]   # Dedup, max 10


def _derive_plan_from_skills(goal: str, skill_names: List[str]) -> List[str]:
    """Build a simple plan list from goal + available skills."""
    plan = ["Interpret and confirm goal"]
    if skill_names:
        plan.append(f"Apply skill patterns: {', '.join(skill_names[:3])}")
    plan += [
        "Execute primary task logic",
        "Validate output against goal",
        "Return result",
    ]
    return plan


def _infer_task_type(task) -> str:
    """Infer task type string for OutcomeValidator."""
    if task is None:
        return "general"
    try:
        tt = str(task.task_type or "").lower()
        if "code" in tt or "debug" in tt:
            return "code"
        if "plan" in tt or "strategy" in tt:
            return "plan"
    except Exception:
        pass
    return "general"


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

reasoning_trace_service = ReasoningTraceService()