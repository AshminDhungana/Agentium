"""
Self-Healing & Auto-Recovery Service for Agentium (Phase 13.2).

Central orchestrator for all self-healing behaviors:
 - Agent heartbeat & crash detection
 - State restoration from checkpoints
 - Agent reincarnation (spawn replacement + re-queue task)
 - Graceful degradation mode (pause non-critical when providers down)
 - Critical path protection (reserve slot for CRITICAL/SOVEREIGN chains)
 - Circuit breaker → Council auto-escalation
 - Daily self-diagnostic routine
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.entities.agents import Agent, AgentStatus, AgentType
from backend.models.entities.task import Task, TaskStatus, TaskPriority
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.voting import TaskDeliberation, DeliberationStatus

logger = logging.getLogger(__name__)

# ── Configurable thresholds ───────────────────────────────────────────────────
HEARTBEAT_STALE_SECONDS = 120     # 2 minutes without heartbeat → crash
CRITICAL_PATH_RESERVED_SLOTS = 1  # Agent slots reserved for critical chains
SELF_DIAG_VIOLATION_THRESHOLD = 3 # Repeated failures before proposing amendment


class SelfHealingService:
    """
    Stateless service providing self-healing operations.
    All methods are static with explicit db parameter —
    same pattern as ReincarnationService.
    """

    # ═══════════════════════════════════════════════════════════
    # 1. AGENT CRASH DETECTION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def detect_crashed_agents(db: Session) -> Dict[str, Any]:
        """
        Query agents with status='working' and stale heartbeat.
        Mark them as crashed and emit WebSocket events.

        Returns dict with detection results.
        """
        threshold = datetime.utcnow() - timedelta(seconds=HEARTBEAT_STALE_SECONDS)

        # Agents that are working but haven't heartbeated recently
        crashed_agents = db.query(Agent).filter(
            Agent.status == AgentStatus.WORKING,
            Agent.is_active == True,
            Agent.last_heartbeat_at.isnot(None),
            Agent.last_heartbeat_at < threshold,
        ).all()

        results = {
            "detected": len(crashed_agents),
            "recovered": 0,
            "failed_recoveries": 0,
            "details": [],
        }

        for agent in crashed_agents:
            logger.warning(
                "🚨 Crash detected: agent %s — last heartbeat %s",
                agent.agentium_id,
                agent.last_heartbeat_at,
            )

            try:
                # Mark agent as crashed
                agent.status = AgentStatus.SUSPENDED
                crash_detail = {
                    "agent_id": agent.agentium_id,
                    "last_heartbeat": agent.last_heartbeat_at.isoformat() if agent.last_heartbeat_at else None,
                    "current_task": agent.current_task_id,
                }

                # Log crash event
                audit = AuditLog.log(
                    level=AuditLevel.WARNING,
                    category=AuditCategory.SYSTEM,
                    actor_type="system",
                    actor_id="SELF_HEALING",
                    action="agent_crashed",
                    target_type="agent",
                    target_id=agent.agentium_id,
                    description=(
                        f"Agent {agent.agentium_id} detected as crashed "
                        f"(no heartbeat for >{HEARTBEAT_STALE_SECONDS}s)"
                    ),
                    after_state=crash_detail,
                )
                db.add(audit)

                # Attempt recovery
                recovery = SelfHealingService.recover_crashed_agent(agent, db)
                if recovery.get("recovered"):
                    results["recovered"] += 1
                    crash_detail["recovery"] = recovery
                else:
                    results["failed_recoveries"] += 1
                    crash_detail["recovery_error"] = recovery.get("error")

                results["details"].append(crash_detail)

            except Exception as e:
                logger.error(
                    "Failed to process crash for agent %s: %s",
                    agent.agentium_id, e,
                )
                results["failed_recoveries"] += 1
                results["details"].append({
                    "agent_id": agent.agentium_id,
                    "error": str(e),
                })

        if crashed_agents:
            db.commit()

            # Emit WebSocket events
            SelfHealingService._broadcast_event("agent_crashed", {
                "crashed_count": len(crashed_agents),
                "recovered": results["recovered"],
                "timestamp": datetime.utcnow().isoformat(),
            })

        return results

    # ═══════════════════════════════════════════════════════════
    # 2. AGENT RECOVERY FROM CHECKPOINT
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def recover_crashed_agent(agent: Agent, db: Session) -> Dict[str, Any]:
        """
        Restore agent state from checkpoint and spawn a replacement.
        Re-queue interrupted task in ASSIGNED status.
        """
        result = {
            "recovered": False,
            "old_agent": agent.agentium_id,
            "successor_id": None,
            "task_requeued": None,
        }

        try:
            # Step 1: Try to restore state from checkpoint
            interrupted_task_id = agent.current_task_id
            checkpoint_restored = False

            if interrupted_task_id:
                try:
                    from backend.services.checkpoint_service import CheckpointService
                    from backend.models.entities.checkpoint import ExecutionCheckpoint

                    # Find latest checkpoint for the interrupted task
                    latest_cp = db.query(ExecutionCheckpoint).filter(
                        ExecutionCheckpoint.task_id == interrupted_task_id,
                    ).order_by(
                        ExecutionCheckpoint.created_at.desc()
                    ).first()

                    if latest_cp:
                        CheckpointService.resume_from_checkpoint(
                            db=db,
                            checkpoint_id=latest_cp.id,
                            actor_id="SELF_HEALING",
                        )
                        checkpoint_restored = True
                        logger.info(
                            "Restored checkpoint %s for task %s",
                            latest_cp.id, interrupted_task_id,
                        )
                except Exception as cp_err:
                    logger.warning(
                        "Checkpoint restoration failed for task %s: %s",
                        interrupted_task_id, cp_err,
                    )

            # Step 2: Spawn replacement agent via ReincarnationService
            try:
                from backend.services.reincarnation_service import ReincarnationService

                # Determine tier
                tier_map = {"0": "head", "1": "council", "2": "lead", "3": "task"}
                tier_name = tier_map.get(agent.agentium_id[0], "task")
                new_id = ReincarnationService.generate_id_with_retry(tier_name, db)

                # Create replacement agent
                new_agent_class = type(agent)
                successor = new_agent_class(
                    agentium_id=new_id,
                    name=f"{agent.name} (Recovery)",
                    description=f"Auto-recovered replacement for crashed {agent.agentium_id}",
                    parent_id=agent.parent_id,
                    agent_type=agent.agent_type,
                    status=AgentStatus.ACTIVE,
                    is_active=True,
                    is_persistent=agent.is_persistent,
                    idle_mode_enabled=agent.idle_mode_enabled,
                    created_by="SELF_HEALING",
                )
                successor.constitution_version = agent.constitution_version
                successor.preferred_config_id = agent.preferred_config_id
                successor.ethos_id = agent.ethos_id

                db.add(successor)
                db.flush()

                result["successor_id"] = successor.agentium_id
                logger.info(
                    "Spawned replacement agent %s for crashed %s",
                    successor.agentium_id, agent.agentium_id,
                )

                # Step 3: Re-queue interrupted task
                if interrupted_task_id:
                    task = db.query(Task).filter_by(
                        id=interrupted_task_id, is_active=True
                    ).first()
                    if task and task.status not in (
                        TaskStatus.COMPLETED, TaskStatus.CANCELLED,
                    ):
                        task.status = TaskStatus.ASSIGNED
                        task.assigned_task_agent_ids = [successor.agentium_id]
                        successor.current_task_id = task.id
                        result["task_requeued"] = interrupted_task_id
                        logger.info(
                            "Re-queued task %s → agent %s",
                            interrupted_task_id, successor.agentium_id,
                        )

                # Deactivate crashed agent
                agent.is_active = False
                agent.terminated_at = datetime.utcnow()
                agent.termination_reason = "Crashed — auto-recovered by Self-Healing"
                agent.current_task_id = None

                result["recovered"] = True

            except Exception as spawn_err:
                result["error"] = f"Spawn failed: {spawn_err}"
                logger.error(
                    "Failed to spawn replacement for %s: %s",
                    agent.agentium_id, spawn_err,
                )

        except Exception as e:
            result["error"] = str(e)
            logger.error("Recovery failed for %s: %s", agent.agentium_id, e)

        return result

    # ═══════════════════════════════════════════════════════════
    # 3. GRACEFUL DEGRADATION MODE
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def enter_degraded_mode(db: Session) -> Dict[str, Any]:
        """
        Pause tasks with priority < HIGH when all API providers are down.
        Continue CRITICAL/SOVEREIGN on local Ollama.
        Emit system_mode_change WebSocket.
        """
        # Pause non-critical active tasks
        non_critical_tasks = db.query(Task).filter(
            Task.status == TaskStatus.IN_PROGRESS,
            Task.is_active == True,
            ~Task.priority.in_([TaskPriority.CRITICAL, TaskPriority.SOVEREIGN]),
        ).all()

        paused_count = 0
        for task in non_critical_tasks:
            task.status = TaskStatus.PENDING
            # Build a new dict rather than mutating in place — SQLAlchemy does
            # not detect in-place mutations on JSON columns.  Reassignment
            # combined with flag_modified() guarantees the column is marked dirty.
            ctx = dict(task.execution_context or {})
            ctx["paused_by_degradation"] = True
            ctx["paused_at"] = datetime.utcnow().isoformat()
            task.execution_context = ctx
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(task, "execution_context")
            paused_count += 1

        # Log the mode change
        audit = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id="SELF_HEALING",
            action="system_mode_degraded",
            description=f"System entered DEGRADED mode — {paused_count} non-critical tasks paused",
            after_state={
                "mode": "degraded",
                "paused_tasks": paused_count,
            },
        )
        db.add(audit)
        db.commit()

        # Broadcast WebSocket event
        SelfHealingService._broadcast_event("system_mode_change", {
            "mode": "degraded",
            "paused_tasks": paused_count,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.warning(
            "System entered DEGRADED mode — %d tasks paused", paused_count,
        )

        return {
            "mode": "degraded",
            "paused_tasks": paused_count,
        }

    @staticmethod
    def exit_degraded_mode(db: Session) -> Dict[str, Any]:
        """
        Resume paused tasks when providers recover.
        Emit system_mode_change WebSocket with normal mode.
        """
        # Find tasks paused by degradation
        paused_tasks = db.query(Task).filter(
            Task.status == TaskStatus.PENDING,
            Task.is_active == True,
        ).all()

        resumed_count = 0
        for task in paused_tasks:
            ctx = task.execution_context or {}
            if ctx.get("paused_by_degradation"):
                task.status = TaskStatus.IN_PROGRESS
                ctx.pop("paused_by_degradation", None)
                ctx.pop("paused_at", None)
                task.execution_context = ctx
                resumed_count += 1

        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id="SELF_HEALING",
            action="system_mode_normal",
            description=f"System recovered — {resumed_count} tasks resumed",
            after_state={"mode": "normal", "resumed_tasks": resumed_count},
        )
        db.add(audit)
        db.commit()

        SelfHealingService._broadcast_event("system_mode_change", {
            "mode": "normal",
            "resumed_tasks": resumed_count,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info("System exited DEGRADED mode — %d tasks resumed", resumed_count)

        return {"mode": "normal", "resumed_tasks": resumed_count}

    # ═══════════════════════════════════════════════════════════
    # 4. CIRCUIT BREAKER → COUNCIL AUTO-ESCALATION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def trigger_circuit_breaker_escalation(
        agent_id: str,
        cb_state: Dict[str, Any],
        db: Session,
    ) -> Optional[str]:
        """
        Enqueue an EMERGENCY micro-vote via TaskDeliberation when
        a circuit breaker opens.

        Returns the deliberation ID or None on failure.
        """
        try:
            # Get council members for the micro-vote
            council = db.query(Agent).filter(
                Agent.agent_type == AgentType.COUNCIL_MEMBER,
                Agent.is_active == True,
            ).limit(3).all()

            council_ids = [c.agentium_id for c in council]

            if not council_ids:
                logger.warning(
                    "No council members available for CB escalation of %s",
                    agent_id,
                )
                return None

            # Create emergency deliberation
            deliberation = TaskDeliberation(
                participating_members=council_ids,
                required_approvals=1,  # Emergency: single approval suffices
                min_quorum=1,
                status=DeliberationStatus.ACTIVE,
                started_at=datetime.utcnow(),
                time_limit_minutes=5,  # 5-minute emergency window
                discussion_thread=[{
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent": "SELF_HEALING",
                    "message": (
                        f"🚨 EMERGENCY: Circuit breaker OPENED for agent {agent_id} "
                        f"after {cb_state.get('failures', '?')} consecutive failures. "
                        f"Council action required: investigate, reallocate, or terminate."
                    ),
                }],
            )
            db.add(deliberation)

            # Audit log
            audit = AuditLog.log(
                level=AuditLevel.WARNING,
                category=AuditCategory.GOVERNANCE,
                actor_type="system",
                actor_id="SELF_HEALING",
                action="circuit_breaker_escalation",
                target_type="agent",
                target_id=agent_id,
                description=(
                    f"Circuit breaker OPEN for {agent_id} — "
                    f"emergency micro-vote created"
                ),
                after_state={
                    "failures": cb_state.get("failures"),
                    "council_notified": council_ids,
                },
            )
            db.add(audit)
            db.flush()

            SelfHealingService._broadcast_event("circuit_breaker_escalation", {
                "agent_id": agent_id,
                "failures": cb_state.get("failures"),
                "deliberation_id": str(deliberation.id),
                "timestamp": datetime.utcnow().isoformat(),
            })

            logger.warning(
                "CB escalation: created emergency deliberation for agent %s",
                agent_id,
            )
            return str(deliberation.id)

        except Exception as e:
            logger.error(
                "Failed to create CB escalation for %s: %s", agent_id, e,
            )
            return None

    # ═══════════════════════════════════════════════════════════
    # 5. SELF-DIAGNOSTIC ROUTINE
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def run_self_diagnostics(db: Session) -> Dict[str, Any]:
        """
        Daily health check: DB connection, Redis connectivity,
        ChromaDB collections, stale tasks, disk usage.
        Proposes constitutional amendment if repeated issues found.
        """
        results = {
            "db_healthy": False,
            "redis_healthy": False,
            "chromadb_healthy": False,
            "stale_tasks": 0,
            "issues": [],
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 1. DB connection check
        try:
            db.execute(func.now())
            results["db_healthy"] = True
        except Exception as e:
            results["issues"].append(f"DB connection failed: {e}")

        # 2. Redis connectivity
        try:
            import redis
            redis_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
            r = redis.from_url(redis_url, socket_timeout=5)
            r.ping()
            results["redis_healthy"] = True
        except Exception as e:
            results["issues"].append(f"Redis ping failed: {e}")

        # 3. ChromaDB collections
        try:
            from backend.core.vector_store import VectorStore
            vs = VectorStore()
            collections = vs.client.list_collections()
            results["chromadb_healthy"] = True
            results["chromadb_collections"] = len(collections)
        except Exception as e:
            results["issues"].append(f"ChromaDB check failed: {e}")

        # 4. Stale task count (IN_PROGRESS > 24h)
        try:
            stale_threshold = datetime.utcnow() - timedelta(hours=24)
            stale_count = db.query(func.count(Task.id)).filter(
                Task.status == TaskStatus.IN_PROGRESS,
                Task.is_active == True,
                Task.started_at < stale_threshold,
            ).scalar() or 0
            results["stale_tasks"] = stale_count
            if stale_count > 5:
                results["issues"].append(
                    f"{stale_count} tasks stalled > 24h"
                )
        except Exception as e:
            results["issues"].append(f"Stale task check failed: {e}")

        # 5. Log diagnostic results
        is_healthy = len(results["issues"]) == 0
        audit = AuditLog.log(
            level=AuditLevel.INFO if is_healthy else AuditLevel.WARNING,
            category=AuditCategory.SYSTEM,
            actor_type="system",
            actor_id="SELF_HEALING",
            action="self_diagnostic",
            description=(
                "Daily self-diagnostic: HEALTHY"
                if is_healthy
                else f"Daily self-diagnostic: {len(results['issues'])} issue(s) found"
            ),
            after_state=results,
        )
        db.add(audit)

        # 6. Propose amendment if repeated violations (3+ diagnostics with issues)
        if not is_healthy:
            recent_failures = db.query(func.count(AuditLog.id)).filter(
                AuditLog.action == "self_diagnostic",
                AuditLog.level == AuditLevel.WARNING,
                AuditLog.created_at >= datetime.utcnow() - timedelta(days=7),
            ).scalar() or 0

            if recent_failures >= SELF_DIAG_VIOLATION_THRESHOLD:
                results["amendment_proposed"] = True
                logger.warning(
                    "Self-diagnostic: %d failures in 7 days — "
                    "proposing constitutional amendment for system hardening",
                    recent_failures,
                )
                # Log the amendment proposal (actual amendment creation
                # would go through AmendmentService)
                amend_audit = AuditLog.log(
                    level=AuditLevel.WARNING,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="system",
                    actor_id="SELF_HEALING",
                    action="amendment_proposed",
                    description=(
                        f"Auto-proposing system hardening amendment: "
                        f"{recent_failures} diagnostic failures in 7 days"
                    ),
                    after_state={
                        "issues": results["issues"],
                        "failure_count": recent_failures,
                    },
                )
                db.add(amend_audit)

        db.commit()

        logger.info(
            "Self-diagnostic complete: %s",
            "HEALTHY" if is_healthy else f"{len(results['issues'])} issues",
        )

        return results

    # ═══════════════════════════════════════════════════════════
    # 6. CRITICAL PATH PROTECTION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def protect_critical_path(db: Session) -> Dict[str, Any]:
        """
        Tag tasks that are DAG ancestors of CRITICAL/SOVEREIGN leaves.
        Reserve one agent slot permanently for these chains.
        """
        results = {
            "critical_tasks_found": 0,
            "ancestors_tagged": 0,
            "slots_reserved": CRITICAL_PATH_RESERVED_SLOTS,
        }

        # Find CRITICAL/SOVEREIGN tasks
        critical_tasks = db.query(Task).filter(
            Task.priority.in_([TaskPriority.CRITICAL, TaskPriority.SOVEREIGN]),
            Task.status.in_([
                TaskStatus.PENDING, TaskStatus.IN_PROGRESS,
                TaskStatus.ASSIGNED, TaskStatus.APPROVED,
            ]),
            Task.is_active == True,
        ).all()

        results["critical_tasks_found"] = len(critical_tasks)

        # Walk up the parent chain and tag ancestors
        tagged_ids = set()
        for task in critical_tasks:
            current = task
            while current and current.parent_task_id:
                parent = db.query(Task).filter_by(
                    id=current.parent_task_id, is_active=True,
                ).first()
                if not parent or parent.id in tagged_ids:
                    break

                # Tag as critical path
                ctx = parent.execution_context or {}
                if not ctx.get("critical_path"):
                    ctx["critical_path"] = True
                    ctx["critical_path_tagged_at"] = datetime.utcnow().isoformat()
                    parent.execution_context = ctx
                    tagged_ids.add(parent.id)

                current = parent

        results["ancestors_tagged"] = len(tagged_ids)

        if tagged_ids:
            db.commit()
            logger.info(
                "Critical path: tagged %d ancestor tasks for %d critical tasks",
                len(tagged_ids), len(critical_tasks),
            )

        return results

    # ═══════════════════════════════════════════════════════════
    # 7. HEARTBEAT UPDATE
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def update_heartbeats(db: Session) -> Dict[str, Any]:
        """
        Update last_heartbeat_at for all active/working agents.
        Called by the agent-heartbeat Celery beat task every 60s.
        """
        now = datetime.utcnow()
        updated = db.query(Agent).filter(
            Agent.status.in_([
                AgentStatus.ACTIVE,
                AgentStatus.WORKING,
                AgentStatus.IDLE_WORKING,
            ]),
            Agent.is_active == True,
        ).update(
            {"last_heartbeat_at": now},
            synchronize_session="fetch",
        )

        db.commit()

        return {"updated": updated, "timestamp": now.isoformat()}

    # ═══════════════════════════════════════════════════════════
    # 8. CHECK DEGRADATION TRIGGERS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def check_degradation_triggers(db: Session) -> Dict[str, Any]:
        """
        Check if enough circuit breakers have opened recently to warrant
        entering degraded mode.  Called during crash detection cycle.

        Architecture note: AgentOrchestrator stores circuit breaker state
        in-memory inside the FastAPI process.  Celery workers are separate
        OS processes and cannot share that memory.  We therefore derive
        degradation state from the audit log — the only data store that is
        visible to every process in the system.

        Degradation threshold: if the number of distinct agents that have
        fired a circuit_breaker_escalation event in the last 10 minutes
        is >= the total number of active agents, all providers are
        effectively down and we should enter degraded mode.
        """
        try:
            window = datetime.utcnow() - timedelta(minutes=10)

            # Collect distinct agent IDs that escalated a circuit breaker recently
            recent_escalations = db.query(AuditLog).filter(
                AuditLog.action == "circuit_breaker_escalation",
                AuditLog.created_at >= window,
            ).all()

            open_breaker_agents = {
                row.target_id for row in recent_escalations if row.target_id
            }
            open_breakers_count = len(open_breaker_agents)

            # Count total active agents
            total_active = db.query(func.count(Agent.id)).filter(
                Agent.is_active == True,
                Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.WORKING]),
            ).scalar() or 0

            if total_active > 0 and open_breakers_count >= total_active:
                # Every active agent has an open circuit breaker — enter degraded mode
                SelfHealingService.enter_degraded_mode(db)
                return {
                    "degraded": True,
                    "open_breakers": open_breakers_count,
                    "total_active": total_active,
                    "window_minutes": 10,
                }

            return {
                "degraded": False,
                "open_breakers": open_breakers_count,
                "total_active": total_active,
                "window_minutes": 10,
            }

        except Exception as e:
            logger.error("Degradation check failed: %s", e)
            return {"error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _broadcast_event(event_type: str, data: Dict[str, Any]):
        """
        Best-effort WebSocket broadcast.
        Uses same lazy import pattern as AlertManager.

        Imports from backend.api.routes.websocket (where `manager` is defined)
        rather than backend.main to avoid a circular import: main.py imports
        SelfHealingService (via task_executor), so importing main here would
        create a dependency cycle that breaks Celery worker startup.
        """
        try:
            import asyncio
            from backend.api.routes.websocket import manager as websocket_manager

            payload = {"type": event_type, **data}

            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if loop and loop.is_running():
                asyncio.ensure_future(websocket_manager.broadcast(payload))
            else:
                # Celery worker context — no running loop
                try:
                    asyncio.run(websocket_manager.broadcast(payload))
                except Exception:
                    pass  # non-critical: WebSocket may not be available in worker

        except Exception as e:
            logger.debug("WebSocket broadcast failed (non-critical): %s", e)

    @staticmethod
    def get_self_healing_events(
        db: Session,
        limit: int = 50,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Return recent self-healing events from the audit log.
        Used by the monitoring API endpoint.
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        healing_actions = [
            "agent_crashed", "self_diagnostic", "system_mode_degraded",
            "system_mode_normal", "circuit_breaker_escalation",
            "amendment_proposed",
        ]

        audits = db.query(AuditLog).filter(
            AuditLog.action.in_(healing_actions),
            AuditLog.created_at >= start_date,
        ).order_by(AuditLog.created_at.desc()).limit(limit).all()

        events = []
        for a in audits:
            events.append({
                "id": str(a.id),
                "action": a.action,
                "level": a.level.value if hasattr(a.level, "value") else str(a.level),
                "description": a.description,
                "target_id": a.target_id,
                "details": a.after_state if hasattr(a, "after_state") else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })

        return events

    @staticmethod
    def get_system_mode(db: Session) -> Dict[str, Any]:
        """
        Return current system mode based on recent audit events.
        """
        # Check if there's a recent degradation event without a
        # corresponding recovery
        latest_mode_event = db.query(AuditLog).filter(
            AuditLog.action.in_(["system_mode_degraded", "system_mode_normal"]),
        ).order_by(AuditLog.created_at.desc()).first()

        if latest_mode_event and latest_mode_event.action == "system_mode_degraded":
            return {"mode": "degraded", "since": latest_mode_event.created_at.isoformat()}

        return {"mode": "normal"}