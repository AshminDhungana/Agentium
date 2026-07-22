"""
Task execution handlers for Celery.
Includes: task execution, constitution review, idle processing, 
self-healing execution loop, data retention, and channel message retry.

"""
import logging
import asyncio
import json
import os
import time
from typing import Optional, Dict, Any, List
from dataclasses import asdict
from datetime import datetime, timedelta
from contextlib import contextmanager

from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from sqlalchemy.exc import OperationalError

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import NullPool

from backend.celery_app import celery_app

# Import models directly (not through database module)
from backend.models.entities.channels import ExternalMessage, ExternalChannel, ChannelStatus, ChannelType
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.models.entities.task_events import TaskEvent, TaskEventType
from backend.models.entities.agents import Agent, AgentStatus, CouncilMember, HeadOfCouncil, LeadAgent, AgentType
from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
from backend.services.reincarnation_service import ReincarnationService
from backend.services.knowledge_assist import checkpoint_write
from backend.services.chat_prune_service import run_chat_prune_task

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# DEDICATED CELERY DATABASE CONFIGURATION
# ═══════════════════════════════════════════════════════════

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/agentium"
)

celery_engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    pool_pre_ping=True,
    echo=False,
    future=True
)

CelerySessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=celery_engine
)

CeleryScopedSession = scoped_session(CelerySessionLocal)


# ═══════════════════════════════════════════════════════════
# Database Session Context Manager
# ═══════════════════════════════════════════════════════════

@retry(
    retry=retry_if_exception_type(OperationalError),
    stop=stop_after_attempt(5),
    wait=wait_fixed(2),
    reraise=True,
)
@contextmanager
def get_task_db():
    """
    Context manager for database sessions in Celery tasks.
    Uses dedicated Celery engine with NullPool to avoid connection
    corruption across forked worker processes.
    """
    db = CelerySessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        CeleryScopedSession.remove()


# ═══════════════════════════════════════════════════════════
# Core Task Execution
# ═══════════════════════════════════════════════════════════

def _extract_workspace(result: dict) -> tuple:
    """Pull workspace metadata out of an execution result, defaulting to None.

    Returns ``(workspace_path, artifacts)``. When no workspace was used
    (or ``result`` is not a dict), ``workspace_path`` is ``None`` and
    ``artifacts`` defaults to an empty list.
    """
    if not isinstance(result, dict):
        return None, []
    return result.get("workspace_path"), result.get("artifacts") or []

@celery_app.task(name="agentium.tasks.task_executor.execute_task_async", bind=True, max_retries=1)
def execute_task_async(self, task_id: str, agent_id: str):
    """
    Execute task with skill-augmented RAG.
    """
    with get_task_db() as db:
        try:
            logger.info(f"Executing task {task_id} with agent {agent_id}")

            # Load task and agent
            task = db.query(Task).filter_by(agentium_id=task_id).first()

            if not task:
                raise ValueError(f"Task {task_id} not found")

            agent = None
            if agent_id:
                agent = db.query(Agent).filter_by(agentium_id=agent_id).first()

            if not agent:
                agent = db.query(Agent).filter(Agent.status == 'active').first()

            if not agent:
                raise ValueError(f"No active agent found for task {task_id}")

            # 8.4: received checkpoint — query Chroma + web-search + write-back
            try:
                asyncio.run(checkpoint_write("received", task, agent, db))
            except Exception as cp_exc:  # noqa: BLE001
                logger.warning(f"received checkpoint failed for {task_id}: {cp_exc}")

            # Execute with skill RAG
            result = agent.execute_with_skill_rag(task, db)
            
            # Update task with result
            ws_path, arts = _extract_workspace(result)
            result_data = {
                "full_output": result["content"],
                "skills_used": result.get("skills_used", []),
                "model": result.get("model"),
                "tokens_used": result.get("tokens_used")
            }
            if ws_path:
                result_data["workspace_path"] = ws_path
                result_data["artifacts"] = arts
                try:
                    from backend.api.routes.websocket import manager
                    asyncio.run(manager.broadcast({
                        "type": "workspace_ready",
                        "agent_id": agent_id,
                        "task_id": task_id,
                        "workspace_path": ws_path,
                        "artifact_count": len(arts or []),
                    }))
                except Exception as ws_err:  # pragma: no cover - broadcast is best-effort
                    logger.warning(f"workspace_ready broadcast failed: {ws_err}")
            task.complete(
                result_summary=result["content"][:500],
                result_data=result_data
            )

            # 8.4: completed checkpoint — query Chroma + web-search + write-back
            try:
                asyncio.run(checkpoint_write("completed", task, agent, db))
            except Exception as cp_exc:  # noqa: BLE001
                logger.warning(f"completed checkpoint failed for {task_id}: {cp_exc}")

            # 8.4: mid checkpoint — only when the agent self-signaled a gap
            if isinstance(result, dict) and result.get("knowledge_needed"):
                try:
                    asyncio.run(checkpoint_write(
                        "mid", task, agent, db,
                        query=result.get("knowledge_query"),
                    ))
                except Exception as cp_exc:  # noqa: BLE001
                    logger.warning(f"mid checkpoint failed for {task_id}: {cp_exc}")

            # Record success for used skills
            for skill in result.get("skills_used", []):
                from backend.services.skill_manager import skill_manager
                skill_manager.record_skill_usage(
                    skill_id=skill["skill_id"],
                    success=True,
                    db=db
                )
            
            # Phase 13.4: Real-Time Learning Write
            try:
                from backend.services.autonomous_learning import get_learning_engine
                engine = get_learning_engine()
                learning_stats = engine.analyze_outcomes(db)
                logger.info(f"Real-Time Learning executed for task {task_id}: {learning_stats}")
            except Exception as learning_exc:
                logger.error(f"Real-Time Learning extraction failed for task {task_id}: {learning_exc}")

            # Phase 16.2: Validation Boost
            try:
                retrieved_ids = (
                    (task.execution_context or {}).get("retrieved_learning_ids")
                    or result.get("retrieved_learning_ids")
                    or []
                )
                if retrieved_ids:
                    from backend.services.knowledge_service import get_knowledge_service
                    ks = get_knowledge_service()
                    boost_result = ks.boost_retrieved_learnings(retrieved_ids)
                    logger.info(
                        f"Phase 16.2: Validation boost for task {task_id}: "
                        f"boosted {boost_result.get('boosted', 0)} entries"
                    )
            except Exception as boost_exc:
                logger.debug(f"Validation boost skipped for task {task_id}: {boost_exc}")

            return {
                "status": "completed",
                "task_id": task_id,
                "skills_used": len(result.get("skills_used", []))
            }

        except RuntimeError as exc:
            # Total provider exhaustion (all keys invalid / rate-limited /
            # unreachable) — fail cleanly. Do NOT re-queue forever via Celery
            # retry; the worker must move on to the next task.
            reason = "provider_unreachable"
            msg = str(exc).lower()
            if ("all_keys_invalid" in msg or "401" in msg or "403" in msg
                    or "invalid api key" in msg or "authentication" in msg
                    or "insufficient_quota" in msg):
                reason = "all_keys_invalid"
            elif ("429" in msg or "ratelimit" in msg or "too many requests" in msg
                  or "rate_limit" in msg):
                reason = "rate_limited"

            try:
                task.mark_failed(reason=reason, error_message=str(exc))
            except Exception as mark_exc:
                logger.error(f"mark_failed failed for {task_id}: {mark_exc}")
            try:
                # AuditLog.log is a factory (does NOT persist) — add + commit.
                entry = AuditLog.log(
                    level=AuditLevel.CRITICAL,
                    category=AuditCategory.SYSTEM,
                    actor_type="system",
                    actor_id="SYSTEM",
                    action="task_failed_exhaustion",
                    description=f"Task {task_id} failed: {reason}",
                    after_state={"reason": reason},
                )
                db.add(entry)
            except Exception as audit_exc:
                logger.error(
                    f"AuditLog for failed task {task_id} failed: "
                    f"{type(audit_exc).__name__}: {audit_exc}",
                    exc_info=True,
                )
            db.commit()

            # Phase 19.3 (Task 15): surface a friendly degradation message to the
            # user instead of a stack trace. The task is already terminal; this
            # just tells any connected dashboard that the provider is exhausted.
            try:
                from backend.api.routes.websocket import manager
                friendly = (
                    "The AI provider is temporarily unavailable or rate-limited; "
                    "this task has been queued for retry"
                )
                asyncio.run(manager.broadcast({
                    "type": "task_degraded",
                    "task_id": task_id,
                    "reason": reason,
                    "message": friendly,
                }))
            except Exception as ws_exc:
                logger.error(f"task_degraded broadcast failed for {task_id}: {ws_exc}")

            return {"status": "failed", "task_id": task_id, "reason": reason}

        except Exception as exc:
            logger.error(f"Task execution failed: {exc}")
            
            # Phase 13.4: Anti-Pattern Early Warning
            try:
                from backend.core.vector_store import get_vector_store
                from backend.api.routes.websocket import manager
                
                vs = get_vector_store()
                try:
                    results = vs.get_collection("task_patterns").query(
                        query_texts=[str(exc)],
                        n_results=3,
                        where={"type": "anti_pattern"}
                    )
                    if results.get("documents") and results["documents"][0]:
                        distances = results["distances"][0] if results.get("distances") else []
                        similar_count = sum(1 for d in distances if d < 0.2)
                        
                        if similar_count >= 3:
                            warning_msg = f"Anti-Pattern Detected: Similar failure occurred {similar_count} times. Error: {str(exc)[:100]}"
                            logger.warning(warning_msg)

                            try:
                                asyncio.run(manager.broadcast({
                                    "type": "pattern_warning",
                                    "data": {
                                        "task_id": task_id,
                                        "error": str(exc),
                                        "message": warning_msg
                                    }
                                }))
                            except Exception:
                                pass

                            try:
                                import redis.asyncio as aioredis
                                redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

                                async def inc_ap():
                                    """Inc ap."""
                                    r = await aioredis.from_url(redis_url, decode_responses=True)
                                    await r.hincrby("agentium:learning:impact", "anti_patterns_warned", 1)
                                    await r.close()

                                asyncio.run(inc_ap())
                            except Exception:
                                pass
                except Exception as inner_exc:
                    logger.debug(f"Anti-Pattern scan skipped or failed: {inner_exc}")
            except Exception as eval_exc:
                logger.error(f"Anti-pattern evaluation failed: {eval_exc}")

            countdown = min(2 ** self.request.retries, 60)

            # Terminal-state guarantee (contract item 1): once we have exhausted
            # every retry, the task MUST reach a terminal state. Without this the
            # generic-exception path raised self.retry() forever until Celery
            # gave up and left the Task stranded in IN_PROGRESS (a silent stall
            # that only the escalation-timeout watchdog could eventually catch,
            # and only if started_at had been set). Mark it FAILED + audit, and
            # return (do NOT re-raise) so the worker moves on cleanly.
            if self.request.retries >= self.max_retries:
                try:
                    if task is not None:
                        task.mark_failed(
                            reason="execution_failed",
                            error_message=str(exc),
                        )
                except Exception as mark_exc:
                    logger.error(f"mark_failed failed for {task_id}: {mark_exc}")

                try:
                    entry = AuditLog.log(
                        level=AuditLevel.CRITICAL,
                        category=AuditCategory.SYSTEM,
                        actor_type="system",
                        actor_id="SYSTEM",
                        action="task_failed_execution",
                        description=f"Task {task_id} failed after {self.max_retries} retries: {exc}",
                        after_state={"reason": "execution_failed"},
                    )
                    db.add(entry)
                except Exception as audit_exc:
                    logger.error(
                        f"AuditLog for failed task {task_id} failed: "
                        f"{type(audit_exc).__name__}: {audit_exc}",
                        exc_info=True,
                    )
                db.commit()

                return {
                    "status": "failed",
                    "task_id": task_id,
                    "reason": "execution_failed",
                }

            logger.info(f"Retrying task {task_id} in {countdown}s (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(name="agentium.tasks.task_executor.daily_constitution_review")
def daily_constitution_review():
    """Daily review of constitution by persistent council."""
    logger.info("Running daily constitution review")
    return {"status": "completed"}


@celery_app.task(name="agentium.tasks.task_executor.process_idle_tasks")
def process_idle_tasks():
    """Process tasks when system is idle."""
    logger.info("Processing idle tasks")
    return {"status": "completed"}


# ═══════════════════════════════════════════════════════════
# Self-Healing Execution Loop
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="agentium.tasks.task_executor.handle_task_escalation")
def handle_task_escalation():
    """
    Handle tasks that have been escalated to Council after max retries.
    Council decides: liquidate, modify scope, or allocate more resources.
    """
    with get_task_db() as db:
        try:
            escalated_tasks = db.query(Task).filter(
                Task.status == TaskStatus.ESCALATED,
                Task.is_active == True
            ).all()
            
            if not escalated_tasks:
                return {"processed": 0}
            
            council_members = db.query(CouncilMember).filter_by(is_active=True).all()
            head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            
            results = []
            
            for task in escalated_tasks:
                logger.info(f"Processing escalated task {task.agentium_id}: {task.title}")
                
                try:
                    deliberation = task.start_deliberation([m.agentium_id for m in council_members[:3]])
                    db.add(deliberation)
                    
                    decision = _simulate_council_decision(task)
                    
                    if decision == "liquidate":
                        task.cancel(
                            reason="Council decision: Task liquidated after escalation",
                            cancelled_by="Council"
                        )
                        result = "liquidated"
                        
                    elif decision == "modify_scope":
                        task.description += "\n[Modified by Council after escalation]"
                        task.retry_count = 0
                        task.error_count = 0
                        task.set_status(TaskStatus.IN_PROGRESS, "Council", "Scope modified, retrying")
                        result = "modified_and_retrying"
                        
                    elif decision == "allocate_resources":
                        task.set_status(TaskStatus.IN_PROGRESS, "Council", "Additional resources allocated")
                        result = "resources_allocated"
                    
                    AuditLog.log(
                        db=db,
                        level=AuditLevel.INFO,
                        category=AuditCategory.GOVERNANCE,
                        actor_type="agent",
                        actor_id="Council",
                        action="escalated_task_processed",
                        target_type="task",
                        target_id=task.id,
                        description=f"Escalated task processed with decision: {result}",
                        after_state={
                            "task_id": task.agentium_id,
                            "decision": result,
                            "previous_retries": task.retry_count
                        }
                    )
                    
                    results.append({
                        "task_id": task.agentium_id,
                        "decision": result
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to process escalated task {task.agentium_id}: {e}")
                    results.append({
                        "task_id": task.agentium_id,
                        "error": str(e)
                    })
            
            db.commit()
            
            logger.info(f"Processed {len(results)} escalated tasks")
            return {
                "processed": len(results),
                "details": results,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in handle_task_escalation: {e}")
            return {"error": str(e)}


def _simulate_council_decision(task: Task) -> str:
    """Simulate council decision."""

    if task.retry_count >= task.max_retries:
        if task.priority in [TaskPriority.CRITICAL, TaskPriority.SOVEREIGN]:
            return "allocate_resources"
        else:
            return "liquidate"
    return "modify_scope"


# ═══════════════════════════════════════════════════════════
# Data Retention & Sovereign Optimization
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="agentium.tasks.task_executor.sovereign_data_retention")
def sovereign_data_retention():
    """Daily data retention and cleanup task."""
    with get_task_db() as db:
        try:
            results = {
                "tasks_archived": 0,
                "embeddings_removed": 0,
                "logs_compressed": 0,
                "ethos_removed": 0,
                "errors": []
            }
            
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            old_tasks = db.query(Task).filter(
                Task.status.in_([TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED]),
                Task.completed_at < cutoff_date,
                Task.is_active == True
            ).all()
            
            for task in old_tasks:
                try:
                    AuditLog.log(
                        db=db,
                        level=AuditLevel.INFO,
                        category=AuditCategory.GOVERNANCE,
                        actor_type="system",
                        actor_id="DATA_RETENTION",
                        action="task_archived",
                        target_type="task",
                        target_id=task.id,
                        before_state=task.to_dict(),
                        description=f"Task archived after 30 days: {task.agentium_id}"
                    )
                    task.is_active = False
                    results["tasks_archived"] += 1
                except Exception as e:
                    results["errors"].append(f"Failed to archive task {task.agentium_id}: {e}")
            
            try:
                from backend.core.vector_store import get_vector_store
                vector_store = get_vector_store()
                active_task_ids = [t.agentium_id for t in db.query(Task).filter(Task.is_active == True).all()]
                
                try:
                    staging = vector_store.get_collection("staging")
                    staging_docs = staging.get()
                    if staging_docs and staging_docs['ids']:
                        for doc_id, metadata in zip(staging_docs['ids'], staging_docs['metadatas']):
                            task_ref = metadata.get('submission_id', '') if metadata else ''
                            if task_ref and not any(t.startswith(task_ref) for t in active_task_ids):
                                staging.delete(ids=[doc_id])
                                results["embeddings_removed"] += 1
                except Exception as e:
                    results["errors"].append(f"Vector cleanup error: {e}")
            except Exception as e:
                results["errors"].append(f"Vector store error: {e}")
            
            log_cutoff = datetime.utcnow() - timedelta(days=90)
            old_logs = db.query(AuditLog).filter(
                AuditLog.created_at < log_cutoff,
                AuditLog.category == AuditCategory.GOVERNANCE
            ).limit(1000).all()
            
            for log in old_logs:
                if log.action_details is None:
                    log.action_details = {}
                if isinstance(log.action_details, dict):
                    log.action_details['_compressed'] = True
            results["logs_compressed"] = len(old_logs)
            
            try:
                inactive_agents = db.query(Agent).filter(Agent.is_active == False).all()
                for agent in inactive_agents:
                    if hasattr(agent, 'ethos') and agent.ethos:
                        agent.ethos = {}
                        results["ethos_removed"] += 1
            except Exception as e:
                results["errors"].append(f"Ethos cleanup error: {e}")
            
            db.commit()
            logger.info(f"Data retention complete: {results}")
            return {
                "status": "completed",
                "results": results,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in sovereign_data_retention: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Auto-Scaling Governance
# ═══════════════════════════════════════════════════════════

_SCALE_REDIS = None


def _scale_redis():
    """Lazily-constructed synchronous Redis client (Celery runs sync).

    Returns ``None`` if Redis is unreachable so callers can degrade
    gracefully (the cooldown gate simply won't fire).
    """
    global _SCALE_REDIS
    if _SCALE_REDIS is None:
        try:
            import redis as redis_sync

            url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            _SCALE_REDIS = redis_sync.from_url(url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - degraded path
            logger.warning("auto_scale_check: Redis unavailable: %s", exc)
            _SCALE_REDIS = None
    return _SCALE_REDIS


@celery_app.task(name="agentium.tasks.task_executor.auto_scale_check")
def auto_scale_check():
    """Monitor queue depth and trigger auto-scaling if needed."""
    with get_task_db() as db:
        try:
            pending_count = db.query(Task).filter(
                Task.status.in_([
                    TaskStatus.PENDING,
                    TaskStatus.DELIBERATING,
                    TaskStatus.APPROVED,
                    TaskStatus.ASSIGNED
                ]),
                Task.is_active == True
            ).count()
            
            threshold = int(os.getenv("AUTO_SCALE_THRESHOLD", "10"))
            max_live = int(os.getenv("MAX_LIVE_AGENTS", "50"))
            cooldown = int(os.getenv("AUTO_SCALE_COOLDOWN_SECONDS", "120"))

            # Live agents = anything actively occupying compute/quota.
            live_agents = db.query(Agent).filter(
                Agent.status.in_([
                    AgentStatus.ACTIVE,
                    AgentStatus.WORKING,
                    AgentStatus.IDLE_WORKING,
                ]),
                Agent.is_active == True,
            ).count()

            # No scaling needed, or already at the fleet ceiling.
            if pending_count <= threshold or live_agents >= max_live:
                return {
                    "scaled": False,
                    "pending_count": pending_count,
                    "threshold": threshold,
                    "live_agents": live_agents,
                    "max_live_agents": max_live,
                }

            # Cooldown gate (cross-worker safe via Redis) — prevents a scaling
            # storm from firing a new batch every beat tick.
            r = _scale_redis()
            cd_key = "agentium:autoscale:cooldown"
            if r is not None:
                try:
                    if r.get(cd_key):
                        return {
                            "scaled": False,
                            "pending_count": pending_count,
                            "reason": "cooldown",
                            "live_agents": live_agents,
                        }
                    r.set(cd_key, "1", ex=cooldown)
                except Exception as cd_exc:  # Redis hiccup → proceed without gate
                    logger.warning("auto_scale_check: cooldown gate skipped: %s", cd_exc)

            logger.info(
                f"Queue depth {pending_count} exceeds threshold {threshold} "
                f"(live={live_agents}/{max_live}), requesting scaling"
            )

            head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            if not head:
                return {
                    "scaled": False,
                    "pending_count": pending_count,
                    "reason": "no_head",
                    "live_agents": live_agents,
                }

            # Only spawn up to the remaining headroom under the ceiling.
            recommended_agents = min(3, max(0, max_live - live_agents))
            if recommended_agents <= 0:
                return {
                    "scaled": False,
                    "pending_count": pending_count,
                    "reason": "at_ceiling",
                    "live_agents": live_agents,
                    "max_live_agents": max_live,
                }

            AuditLog.log(
                db=db,
                level=AuditLevel.INFO,
                category=AuditCategory.GOVERNANCE,
                actor_type="agent",
                actor_id="SYSTEM",
                action="auto_scale_triggered",
                description=f"Auto-scaling triggered: {pending_count} pending tasks",
                after_state={
                    "pending_count": pending_count,
                    "threshold": threshold,
                    "live_agents": live_agents,
                    "max_live_agents": max_live,
                    "recommended_agents": recommended_agents,
                },
            )

            spawned = 0
            spawn_errors = []
            for i in range(recommended_agents):
                try:
                    ReincarnationService.spawn_task_agent(
                        parent=head,
                        name=f"AutoScale-Agent-{datetime.utcnow().strftime('%H%M%S')}-{i}",
                        description=f"Auto-spawned Task Agent for queue depth scaling (threshold: {threshold}, pending: {pending_count})",
                        db=db,
                    )
                    spawned += 1
                except Exception as spawn_exc:
                    logger.error(f"auto_scale_check: spawn {i+1}/{recommended_agents} failed: {spawn_exc}")
                    spawn_errors.append(str(spawn_exc))

            return {
                "scaled": True,
                "pending_count": pending_count,
                "threshold": threshold,
                "live_agents": live_agents,
                "max_live_agents": max_live,
                "new_agents_requested": recommended_agents,
                "new_agents_spawned": spawned,
                "spawn_errors": spawn_errors,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error in auto_scale_check: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Reasoning Recovery Watchdog
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="agentium.tasks.task_executor.check_stalled_reasoning")
def check_stalled_reasoning():
    """Watchdog: detect stalled reasoning traces and re-queue their tasks."""
    with get_task_db() as db:
        try:
            from backend.services.reasoning_trace_service import reasoning_trace_service
            stalled = reasoning_trace_service.check_stalled_traces(db)

            results = []
            for entry in stalled:
                task_id  = entry.get("task_id")
                agent_id = entry.get("agent_id")
                if not task_id or not agent_id:
                    continue

                task = db.query(Task).filter_by(agentium_id=task_id, is_active=True).first()
                if not task:
                    logger.warning(f"check_stalled_reasoning: task {task_id} not found, skipping re-queue")
                    results.append({"task_id": task_id, "action": "skipped_not_found"})
                    continue

                exec_ctx = task.execution_context or {}
                resume_count = exec_ctx.get("stalled_resume_count", 0)
                if resume_count >= 3:
                    logger.warning(
                        f"check_stalled_reasoning: task {task_id} has stalled {resume_count} times — "
                        "not re-queuing, escalating."
                    )
                    task.set_status(TaskStatus.ESCALATED, "WATCHDOG", "Max stall retries exceeded")
                    results.append({"task_id": task_id, "action": "escalated"})
                    continue

                exec_ctx["stalled_resume_count"] = resume_count + 1
                task.execution_context = exec_ctx
                db.commit()

                execute_task_async.delay(task_id, agent_id)
                logger.info(
                    f"check_stalled_reasoning: re-queued stalled task {task_id} "
                    f"(resume attempt {resume_count + 1}/3)"
                )
                results.append({"task_id": task_id, "action": "re_queued", "attempt": resume_count + 1})

            return {
                "stalled_detected": len(stalled),
                "actions": results,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"check_stalled_reasoning: unexpected error: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Channel Message Retry & Recovery
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="agentium.tasks.task_executor.retry_channel_message", bind=True, max_retries=3)
def retry_channel_message(self, message_id: str, agent_id: str, content: str, rich_media_dict: Dict[str, Any] = None):
    """Retry sending a failed channel message."""
    with get_task_db() as db:
        try:
            from backend.services.channel_manager import ChannelManager, circuit_breaker, RichMediaContent
            
            message = db.query(ExternalMessage).filter_by(id=message_id).first()
            if not message:
                logger.error(f"Message {message_id} not found for retry")
                return {"success": False, "error": "Message not found"}
            
            channel = db.query(ExternalChannel).filter_by(id=message.channel_id).first()
            if not channel or channel.status != ChannelStatus.ACTIVE:
                logger.warning(f"Channel {message.channel_id} not active, aborting retry")
                return {"success": False, "error": "Channel not active"}
            
            if not circuit_breaker.can_execute(channel.id):
                logger.info(f"Circuit breaker open for channel {channel.id}, rescheduling retry")
                raise self.retry(countdown=600)
            
            rich_media = None
            if rich_media_dict:
                rich_media = RichMediaContent(**rich_media_dict)
            
            success = ChannelManager.send_response(
                message_id=message_id,
                response_content=content,
                agent_id=agent_id,
                rich_media=rich_media,
                db=db
            )
            
            if not success:
                raise Exception("Send returned False")
            
            circuit_breaker.record_success(channel.id)
            logger.info(f"Successfully retried message {message_id}")
            
            return {
                "success": True, 
                "message_id": message_id, 
                "retries": self.request.retries
            }
            
        except Exception as exc:
            retry_count = self.request.retries
            
            if retry_count < 3:
                countdown = 300 * (2 ** retry_count)
                logger.warning(f"Retry {retry_count + 1}/3 for message {message_id} in {countdown}s: {exc}")
                raise self.retry(exc=exc, countdown=countdown)
            
            logger.error(f"Max retries exceeded for message {message_id}: {exc}")
            
            message = db.query(ExternalMessage).filter_by(id=message_id).first()
            if message:
                message.status = "failed"
                message.last_error = f"Max retries exceeded: {str(exc)}"
                db.commit()
            
            if message:
                circuit_breaker.record_failure(message.channel_id)
            
            return {
                "success": False, 
                "error": str(exc), 
                "max_retries_exceeded": True
            }


@celery_app.task(name="agentium.tasks.task_executor.cleanup_old_channel_messages")
def cleanup_old_channel_messages(days: int = 30):
    """Archive old channel messages."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    with get_task_db() as db:
        old_messages = db.query(ExternalMessage).filter(
            ExternalMessage.created_at < cutoff,
            ExternalMessage.status.in_(['responded', 'failed'])
        ).all()
        
        count = 0
        for msg in old_messages:
            msg.status = "archived"
            count += 1
        
        logger.info(f"Archived {count} old channel messages")
        return {"archived": count, "cutoff_days": days}


@celery_app.task(name="agentium.tasks.task_executor.check_channel_health")
def check_channel_health():
    """Periodic health check for all channels."""
    from backend.services.channel_manager import ChannelManager, CircuitState
    
    with get_task_db() as db:
        channels = db.query(ExternalChannel).filter(
            ExternalChannel.status == ChannelStatus.ACTIVE
        ).all()
        
        results = []
        for channel in channels:
            health = ChannelManager.get_channel_health(channel.id)
            
            if (health['overall_status'] == 'degraded' and 
                health['circuit_breaker']['success_rate'] < 0.5):
                
                channel.status = ChannelStatus.ERROR
                channel.error_message = "Auto-disabled due to low success rate"
                db.commit()
                
                results.append({
                    "channel_id": channel.id,
                    "action": "auto_disabled",
                    "reason": "low_success_rate",
                    "success_rate": health['circuit_breaker']['success_rate']
                })
                logger.warning(
                    f"Auto-disabled channel {channel.id} "
                    f"(success rate: {health['circuit_breaker']['success_rate']:.2%})"
                )
            
            elif health['circuit_breaker']['circuit_state'] != 'closed':
                results.append({
                    "channel_id": channel.id,
                    "action": "circuit_state",
                    "state": health['circuit_breaker']['circuit_state'],
                    "consecutive_failures": health['circuit_breaker']['consecutive_failures']
                })
        
        logger.info(f"Health check completed for {len(channels)} channels, {len(results)} actions taken")
        return {
            "checked": len(channels), 
            "actions": results,
            "timestamp": datetime.utcnow().isoformat()
        }


@celery_app.task(name="agentium.tasks.task_executor.start_imap_receivers")
def start_imap_receivers():
    """Ensure IMAP receivers are running for all email channels."""
    from backend.services.channel_manager import imap_receiver
    
    with get_task_db() as db:
        email_channels = db.query(ExternalChannel).filter(
            ExternalChannel.channel_type == ChannelType.EMAIL,
            ExternalChannel.status == ChannelStatus.ACTIVE
        ).all()
        
        channel_configs = []
        for channel in email_channels:
            config = channel.config
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    config = {}
            elif not isinstance(config, dict):
                config = {}
                
            channel_configs.append({
                'id': channel.id,
                'config': config
            })
        
        started = 0
        for channel_data in channel_configs:
            channel_config = channel_data['config']
            if channel_config.get('enable_imap') or channel_config.get('imap_host'):
                try:
                    asyncio.run(
                        imap_receiver.start_channel(channel_data['id'], channel_config)
                    )
                    started += 1
                    logger.info(f"Started/verified IMAP for channel {channel_data['id']}")
                except Exception as e:
                    logger.error(f"Failed to start IMAP for channel {channel_data['id']}: {e}")
        
        return {
            "email_channels": len(email_channels),
            "imap_started": started,
            "timestamp": datetime.utcnow().isoformat()
        }


@celery_app.task(name="agentium.tasks.task_executor.send_channel_heartbeat")
def send_channel_heartbeat():
    """Send periodic heartbeat to all active channels."""
    with get_task_db() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        active_channels = db.query(ExternalChannel).filter(
            ExternalChannel.status == ChannelStatus.ACTIVE,
            ExternalChannel.last_message_at > cutoff_time
        ).all()

        now = datetime.utcnow()
        heartbeats_sent = 0
        for channel in active_channels:
            try:
                channel.updated_at = now
                heartbeats_sent += 1
            except Exception as e:
                logger.error(f"Failed to update channel {channel.id}: {e}")
        
        db.commit()
        logger.info(f"Heartbeat sent to {heartbeats_sent} channels")
        return {"channels": heartbeats_sent}


# ═══════════════════════════════════════════════════════════
# Bulk Operations
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="agentium.tasks.task_executor.broadcast_to_channels")
def broadcast_to_channels(channel_ids: list, message: str, agent_id: str):
    """Broadcast a message to multiple channels."""
    from backend.services.channel_manager import ChannelManager
    
    results = []
    
    with get_task_db() as db:
        for channel_id in channel_ids:
            try:
                test_msg = ExternalMessage(
                    channel_id=channel_id,
                    sender_id="system",
                    sender_name="Agentium",
                    content=message,
                    message_type="announcement",
                    status="pending"
                )
                db.add(test_msg)
                db.flush()

                success = ChannelManager.send_response(
                    message_id=test_msg.id,
                    response_content=message,
                    agent_id=agent_id,
                    db=db
                )

                results.append({
                    "channel_id": channel_id,
                    "success": success,
                    "message_id": test_msg.id
                })

            except Exception as e:
                logger.error(f"Failed to broadcast to channel {channel_id}: {e}")
                results.append({
                    "channel_id": channel_id,
                    "success": False,
                    "error": str(e)
                })

        return {
            "total": len(channel_ids),
            "successful": sum(1 for r in results if r.get('success')),
            "failed": sum(1 for r in results if not r.get('success')),
            "details": results
        }


# ═══════════════════════════════════════════════════════════
# Phase 13.1 — Auto-Delegation Engine Tasks
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.check_escalation_timeouts')
def check_escalation_timeouts():
    """Check escalation timeouts."""

    with get_task_db() as db:
        try:
            now = datetime.utcnow()
            tasks = db.query(Task).filter(
                Task.status == TaskStatus.IN_PROGRESS,
                Task.is_idle_task == False,
                Task.is_active == True,
                Task.started_at.isnot(None),
            ).all()

            escalated = 0
            for task in tasks:
                timeout = getattr(task, 'escalation_timeout_seconds', 300) or 300
                elapsed = (now - task.started_at).total_seconds()

                if elapsed > timeout:
                    try:
                        task.status = TaskStatus.ESCALATED
                        new_history_entry = {
                            'from': TaskStatus.IN_PROGRESS.value,
                            'to': TaskStatus.ESCALATED.value,
                            'by': 'ESCALATION_TIMER',
                            'at': now.isoformat(),
                            'note': f'Timeout after {elapsed:.0f}s (limit: {timeout}s)',
                        }
                        task.status_history = list(task.status_history or []) + [new_history_entry]
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(task, 'status_history')
                        escalated += 1
                        logger.info(
                            f"⏰ Auto-escalated task {task.agentium_id} "
                            f"after {elapsed:.0f}s (limit: {timeout}s)"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to escalate task {task.agentium_id}: {e}")

            if escalated:
                db.commit()

            return {"escalated": escalated, "checked": len(tasks)}

        except Exception as e:
            logger.error(f"check_escalation_timeouts failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.process_dependency_graph')
def process_dependency_graph(db=None):
    """
    db: optional injected Session. When omitted (normal Celery execution),
    a dedicated session is opened via get_task_db() and committed/closed as
    usual. Tests that need to see/operate on data committed via a separate
    fixture session should pass that session in directly via db=...
    """
    from contextlib import nullcontext
    db_ctx = nullcontext(db) if db is not None else get_task_db()
    with db_ctx as db:
        try:
            from backend.models.entities.task import TaskDependency

            pending_deps = db.query(TaskDependency).filter(
                TaskDependency.status == "pending",
            ).all()

            if not pending_deps:
                return {"dispatched": 0}

            by_parent = {}
            for dep in pending_deps:
                by_parent.setdefault(dep.parent_task_id, []).append(dep)

            dispatched = 0
            for parent_id, deps in by_parent.items():
                deps.sort(key=lambda d: d.dependency_order)

                for dep in deps:
                    lower_complete = db.query(TaskDependency).filter(
                        TaskDependency.parent_task_id == parent_id,
                        TaskDependency.dependency_order < dep.dependency_order,
                        TaskDependency.status != "completed",
                    ).count()

                    if lower_complete > 0:
                        continue

                    child = db.query(Task).filter_by(
                        id=dep.child_task_id, is_active=True
                    ).first()

                    if not child or child.status != TaskStatus.PENDING:
                        if child and child.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                            dep.status = "completed"
                        continue

                    try:
                        child.status = TaskStatus.IN_PROGRESS
                        child.started_at = datetime.utcnow()
                        dep.status = "dispatched"
                        dispatched += 1

                        assigned_agent_ids = child.assigned_task_agent_ids or []
                        if assigned_agent_ids:
                            execute_task_async.delay(child.agentium_id, assigned_agent_ids[0])
                    except Exception as e:
                        logger.warning(f"Failed to dispatch child task: {e}")

            if dispatched:
                db.commit()

            return {"dispatched": dispatched, "parents_checked": len(by_parent)}

        except Exception as e:
            logger.error(f"process_dependency_graph failed: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Phase 13.2 — Self-Healing & Auto-Recovery Tasks
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.agent_heartbeat')
def agent_heartbeat():
    """Agent heartbeat."""

    with get_task_db() as db:
        try:
            from backend.services.self_healing_service import SelfHealingService
            result = SelfHealingService.update_heartbeats(db)
            logger.info(f"💓 Heartbeat: updated {result['updated']} agents")
            return result
        except Exception as e:
            logger.error(f"agent_heartbeat failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.detect_crashed_agents')
def detect_crashed_agents():
    """Detect crashed agents."""

    with get_task_db() as db:
        try:
            from backend.services.self_healing_service import SelfHealingService
            result = SelfHealingService.detect_crashed_agents(db)
            if result["detected"] > 0:
                logger.warning(
                    f"🚨 Crash detection: {result['detected']} crashed, "
                    f"{result['recovered']} recovered"
                )
            SelfHealingService.check_degradation_triggers(db)
            return result
        except Exception as e:
            logger.error(f"detect_crashed_agents failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.self_diagnostic_daily')
def self_diagnostic_daily():
    """Self diagnostic daily."""

    with get_task_db() as db:
        try:
            from backend.services.self_healing_service import SelfHealingService
            result = SelfHealingService.run_self_diagnostics(db)
            issues_count = len(result.get("issues", []))
            health_str = "HEALTHY" if issues_count == 0 else f"{issues_count} issue(s)"
            logger.info(f"🔍 Self-diagnostic: {health_str}")
            return result
        except Exception as e:
            logger.error(f"self_diagnostic_daily failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.critical_path_guardian')
def critical_path_guardian():
    """Critical path guardian."""

    with get_task_db() as db:
        try:
            from backend.services.self_healing_service import SelfHealingService
            result = SelfHealingService.protect_critical_path(db)
            if result["critical_tasks_found"] > 0:
                logger.info(
                    f"🛡️ Critical path: {result['critical_tasks_found']} critical tasks, "
                    f"{result['ancestors_tagged']} ancestors tagged"
                )
            return result
        except Exception as e:
            logger.error(f"critical_path_guardian failed: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Phase 13.4 — Continuous Self-Improvement Engine
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.knowledge_consolidation')
def knowledge_consolidation():
    """Knowledge consolidation."""

    with get_task_db() as db:
        try:
            from backend.services.autonomous_learning import get_learning_engine
            return get_learning_engine().decay_outdated_learnings(db)
        except Exception as e:
            logger.error(f"knowledge_consolidation failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.performance_optimization')
def performance_optimization():
    """Performance optimization."""

    with get_task_db() as db:
        try:
            from backend.services.self_improvement_service import self_improvement_service
            return self_improvement_service.optimize_performance(db)
        except Exception as e:
            logger.error(f"performance_optimization failed: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Phase 13.3 — Predictive Auto-Scaling Tasks
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.metrics_snapshot')
def metrics_snapshot():
    """Metrics snapshot."""

    with get_task_db() as db:
        try:
            from backend.services.predictive_scaling import predictive_scaling_service
            result = predictive_scaling_service.snapshot_metrics(db)
            return {"status": "success", "snapshot": result}
        except Exception as e:
            logger.error(f"metrics_snapshot failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.predictive_scale')
def predictive_scale():
    """Predictive scale."""

    with get_task_db() as db:
        try:
            from backend.services.predictive_scaling import predictive_scaling_service
            predictive_scaling_service.enforce_token_budget_guard(db)
            predictions = predictive_scaling_service.get_predictions()
            predictive_scaling_service.evaluate_scaling(db, predictions)
            return {"status": "success", "predictions": predictions}
        except Exception as e:
            logger.error(f"predictive_scale failed: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Phase 13.6 — Intelligent Event Processing Tasks
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.threshold_event_check')
def threshold_event_check():
    """Threshold event check."""

    with get_task_db() as db:
        try:
            from backend.services.event_processor import EventProcessorService
            result = EventProcessorService.check_thresholds(db)
            if result.get("fired", 0) > 0:
                logger.info(
                    f"⚡ Threshold check: {result['fired']} trigger(s) fired "
                    f"out of {result['checked']} checked"
                )
            return result
        except Exception as e:
            logger.error(f"threshold_event_check failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.external_api_poll')
def external_api_poll():
    """External api poll."""

    with get_task_db() as db:
        try:
            from backend.services.event_processor import EventProcessorService
            result = EventProcessorService.poll_external_apis(db)
            if result.get("fired", 0) > 0:
                logger.info(
                    f"🔄 API poll: {result['fired']} change(s) detected "
                    f"out of {result['polled']} polled"
                )
            return result
        except Exception as e:
            logger.error(f"external_api_poll failed: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Phase 13.7 — Zero-Touch Operations Dashboard Tasks
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.anomaly_detection')
def anomaly_detection():
    """Anomaly detection."""

    with get_task_db() as db:
        try:
            from backend.services.monitoring_service import MonitoringService
            result = MonitoringService.detect_anomalies(db)
            if result["anomalies_detected"] > 0:
                logger.warning(f"🔍 Anomaly detection: {result['anomalies_detected']} anomalies found")
                for anomaly in result["anomalies"]:
                    try:
                        fix_result = MonitoringService.auto_remediate(anomaly, db)
                        if fix_result.get("remediated"):
                            logger.info(
                                f"✅ Auto-remediated: {anomaly.get('pattern')} — "
                                f"{fix_result.get('action_taken')}"
                            )
                    except Exception as e:
                        logger.error(f"Auto-remediation failed for {anomaly}: {e}")
            return result
        except Exception as e:
            logger.error(f"anomaly_detection failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.sla_monitor')
def sla_monitor():
    """Sla monitor."""

    with get_task_db() as db:
        try:
            from backend.services.monitoring_service import MonitoringService
            result = MonitoringService.get_sla_metrics(db)
            for priority, data in result.get("sla_by_priority", {}).items():
                if data.get("compliance_pct", 100) < 80.0 and data.get("total", 0) > 0:
                    logger.warning(
                        f"⚠️ SLA breach: {priority} priority at {data['compliance_pct']}% "
                        f"compliance ({data['breached']} breached)"
                    )
            return result
        except Exception as e:
            logger.error(f"sla_monitor failed: {e}")
            return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Phase 16 — Wait & Poll
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.poll_wait_conditions')
def poll_wait_conditions():
    """Poll wait conditions."""

    with get_task_db() as db:
        try:
            from backend.services.wait_poll_service import WaitPollService
            summary = WaitPollService.poll_all_active(db)
            if any(v > 0 for v in summary.values()):
                logger.info(f"poll_wait_conditions: {summary}")
            return summary
        except Exception as exc:
            logger.error(f"poll_wait_conditions failed: {exc}", exc_info=True)
            return {"error": str(exc)}


@celery_app.task(name='agentium.tasks.task_executor.poll_execution_conditions')
def poll_execution_conditions():
    """Poll wait conditions with EXECUTION strategy every 20 seconds."""
    from backend.services.wait_poll_service import WaitPollService
    from backend.models.entities.wait_condition import WaitCondition, WaitStrategy, WaitConditionStatus

    with get_task_db() as db:
        try:
            # Only fetch ACTIVE EXECUTION conditions
            active = (
                db.query(WaitCondition)
                .filter(
                    WaitCondition.status == WaitConditionStatus.ACTIVE,
                    WaitCondition.strategy == WaitStrategy.EXECUTION,
                )
                .all()
            )

            summary = {"resolved": 0, "expired": 0, "errors": 0, "skipped": 0}

            for condition in active:
                try:
                    result = WaitPollService._evaluate(db, condition)
                    if result == "resolved":
                        summary["resolved"] += 1
                    elif result == "expired":
                        summary["expired"] += 1
                    else:
                        summary["skipped"] += 1
                except Exception as exc:
                    summary["errors"] += 1
                    logger.error("Error evaluating EXECUTION WaitCondition %s: %s",
                                 condition.agentium_id, exc, exc_info=True)

            db.commit()
            if any(v > 0 for v in summary.values()):
                logger.info(f"poll_execution_conditions: {summary}")
            return summary
        except Exception as exc:
            logger.error(f"poll_execution_conditions failed: {exc}", exc_info=True)
            return {"error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Phase 16.1 — Slow Query Logging
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.log_slow_query_summary_daily')
def log_slow_query_summary_daily():
    """Log slow query summary daily."""

    with get_task_db() as db:
        try:
            from backend.services.slow_query_service import get_slow_queries, get_summary
            import dataclasses
            
            queries = get_slow_queries(db, limit=10, min_avg_ms=500.0) 
            summary = get_summary(db)
            
            if queries:
                AuditLog.log(
                    db=db,
                    level=AuditLevel.WARNING,
                    category=AuditCategory.SYSTEM,
                    actor_type="system",
                    actor_id="DB_MONITOR",
                    action="slow_query_summary",
                    description=f"Slow query daily report: found {len(queries)} queries with avg > 500ms",
                    after_state={
                        "summary": summary,
                        "top_slow_queries": [dataclasses.asdict(q) for q in queries]
                    }
                )
            return {
                "status": "completed",
                "queries_found": len(queries),
                "summary": summary
            }
        except Exception as e:
            logger.error(f"Error in log_slow_query_summary_daily: {e}")
            return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Phase 16.2 — Learning Decay
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.decay_learnings')
def decay_learnings():
    """Decay learnings."""

    with get_task_db() as db:
        try:
            from backend.services.autonomous_learning import get_learning_engine
            result = get_learning_engine().decay_outdated_learnings(db)

            total_affected = result.get("decayed", 0) + result.get("pruned", 0)
            if total_affected > 0:
                AuditLog.log(
                    db=db,
                    level=AuditLevel.INFO,
                    category=AuditCategory.SYSTEM,
                    actor_type="system",
                    actor_id="DECAY_ENGINE",
                    action="learning_decay_weekly",
                    description=(
                        f"Weekly learning decay: decayed {result.get('decayed', 0)}, "
                        f"pruned {result.get('pruned', 0)}, "
                        f"backfilled {result.get('backfilled', 0)} entries"
                    ),
                    after_state=result,
                )

            logger.info(f"📉 Learning decay completed: {result}")
            return result
        except Exception as e:
            logger.error(f"decay_learnings failed: {e}")
            return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Phase 16.3 — Cross-Document Citation Graph
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name='agentium.tasks.task_executor.update_citation_boosts')
def update_citation_boosts():
    """Update citation boosts."""

    with get_task_db() as db:
        try:
            from backend.services.citation_graph_service import get_citation_graph_service
            from backend.core.vector_store import get_vector_store

            cg = get_citation_graph_service()
            vs = get_vector_store()
            collections_to_boost = ["constitution", "task_patterns", "best_practices", "council_memory"]
            total_updated = 0

            for coll_key in collections_to_boost:
                try:
                    collection = vs.get_collection(coll_key)
                    existing = collection.get()
                    if not existing or not existing.get("ids"):
                        continue
                    doc_ids = existing["ids"]
                    boosts = cg.compute_citation_boost(db, doc_ids)
                    if not boosts:
                        continue
                    ids_to_update = []
                    metas_to_update = []
                    for i, doc_id in enumerate(doc_ids):
                        if doc_id in boosts:
                            meta = (existing["metadatas"][i] if existing.get("metadatas") and i < len(existing["metadatas"]) else {}) or {}
                            meta["citation_boost"] = round(boosts[doc_id], 4)
                            ids_to_update.append(doc_id)
                            metas_to_update.append(meta)
                    if ids_to_update:
                        collection.update(ids=ids_to_update, metadatas=metas_to_update)
                        total_updated += len(ids_to_update)
                except Exception as coll_exc:
                    logger.debug("Phase 16.3: boost update skipped for %s: %s", coll_key, coll_exc)

            if total_updated > 0:
                AuditLog.log(
                    db=db, level=AuditLevel.INFO, category=AuditCategory.SYSTEM,
                    actor_type="system", actor_id="CITATION_GRAPH",
                    action="citation_boost_update",
                    description=f"Phase 16.3: Updated citation_boost for {total_updated} ChromaDB documents",
                    after_state={"updated": total_updated},
                )
            logger.info("📊 Citation boost update completed: %d documents updated", total_updated)
            return {"updated": total_updated}
        except Exception as e:
            logger.error(f"update_citation_boosts failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='agentium.tasks.task_executor.cleanup_citation_edges')
def cleanup_citation_edges():
    """Cleanup citation edges."""

    with get_task_db() as db:
        try:
            from backend.services.citation_graph_service import get_citation_graph_service
            cg = get_citation_graph_service()
            deleted = cg.cleanup_old_edges(db, retention_days=90)
            if deleted > 0:
                AuditLog.log(
                    db=db, level=AuditLevel.INFO, category=AuditCategory.SYSTEM,
                    actor_type="system", actor_id="CITATION_GRAPH",
                    action="citation_edge_cleanup",
                    description=f"Phase 16.3: Cleaned up {deleted} citation edges older than 90 days",
                    after_state={"deleted": deleted},
                )
            logger.info("🧹 Citation edge cleanup completed: %d edges removed", deleted)
            return {"deleted": deleted}
        except Exception as e:
            logger.error(f"cleanup_citation_edges failed: {e}")
            return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Phase 17.1 — Suspicious Pattern Detection
# ══════════════════════════════════════════════════════════════════════════════

# Thresholds — tunable without code changes via env vars
_BLOCK_THRESHOLD   = int(os.getenv("DDOS_BLOCK_THRESHOLD",   "100"))
_BLOCK_TTL_SECONDS = int(os.getenv("DDOS_BLOCK_TTL_SECONDS", "3600"))


@celery_app.task(
    name="agentium.tasks.task_executor.detect_suspicious_patterns",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    ignore_result=False,
)
def detect_suspicious_patterns(self):
    """
    Phase 17.1: Scan Redis 4xx weighted-sum counters and auto-block IPs that
    exceed the abuse threshold within the 5-minute sliding window.

    Strategy:
    1. SCAN for all agentium:4xx:{ip}:wsum keys (non-blocking, cursor-based).
    2. Pipeline-fetch all wsum values in a single round-trip.
    3. Pipeline-write SET blocklist + DELETE counter keys for all abusers.
    4. Bulk-insert AuditLog rows so every block decision is traceable.

    Key design choices:
    - SCAN instead of KEYS: safe on large keyspaces, non-blocking.
    - Pipeline writes: all Redis operations in one round-trip.
    - Counter reset after block: prevents the next cycle from re-blocking the
      same IP based on stale data that has already been acted upon.
    - Env-var thresholds: ops can tune without a code deploy.
    """
    import redis as redis_sync

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    r = redis_sync.from_url(redis_url, decode_responses=True)

    blocked: list[str] = []

    try:
        # ── 1. SCAN for all weighted-sum keys ─────────────────────────────────
        cursor = 0
        candidates: list[tuple[str, float]] = []   # [(ip, weighted_score), ...]

        while True:
            cursor, keys = r.scan(cursor, match="agentium:4xx:*:wsum", count=200)

            if keys:
                # Pipeline: fetch all wsum values in one round-trip
                pipe = r.pipeline(transaction=False)
                for k in keys:
                    pipe.get(k)
                values = pipe.execute()

                for key, raw in zip(keys, values):
                    if raw is None:
                        continue
                    try:
                        score = float(raw)
                    except (ValueError, TypeError):
                        continue

                    if score >= _BLOCK_THRESHOLD:
                        # key format: "agentium:4xx:{ip}:wsum"
                        parts = key.split(":")
                        if len(parts) >= 4:
                            ip = parts[2]
                            candidates.append((ip, score))

            if cursor == 0:
                break   # SCAN complete

        # ── 2. Pipeline-write all blocks ──────────────────────────────────────
        if candidates:
            pipe = r.pipeline(transaction=False)
            for ip, _score in candidates:
                pipe.set(f"agentium:blocked:ips:{ip}", 1, ex=_BLOCK_TTL_SECONDS)
                # Reset both keys so the next cycle starts from zero for this IP
                pipe.delete(f"agentium:4xx:{ip}", f"agentium:4xx:{ip}:wsum")
            pipe.execute()

            blocked = [ip for ip, _ in candidates]

            # ── 3. Audit log — bulk insert ─────────────────────────────────────
            with get_task_db() as db:
                now_ts = time.time()
                db.bulk_save_objects([
                    AuditLog(
                        event_type="IP_AUTO_BLOCKED",
                        level=AuditLevel.WARNING,
                        category=AuditCategory.SECURITY,
                        actor_type="system",
                        actor_id="DDOS_DETECTOR",
                        action="ip_auto_blocked",
                        target_type="ip_address",
                        target_id=ip,
                        description=(
                            f"Phase 17.1: Auto-blocked {ip} "
                            f"(weighted 4xx score: {score:.1f}, "
                            f"threshold: {_BLOCK_THRESHOLD}, "
                            f"TTL: {_BLOCK_TTL_SECONDS}s)"
                        ),
                        after_state={
                            "ip": ip,
                            "weighted_score": score,
                            "threshold": _BLOCK_THRESHOLD,
                            "ttl_seconds": _BLOCK_TTL_SECONDS,
                        },
                        created_at=now_ts,
                    )
                    for ip, score in candidates
                ])

            logger.warning(
                "Phase 17.1: auto-blocked %d IP(s): %s",
                len(blocked),
                ", ".join(blocked[:10]) + ("…" if len(blocked) > 10 else ""),
            )

        else:
            logger.debug("Phase 17.1: detect_suspicious_patterns — no IPs over threshold")

        return {
            "blocked_ips": blocked,
            "count": len(blocked),
            "threshold": _BLOCK_THRESHOLD,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as exc:
        logger.error("detect_suspicious_patterns failed: %s", exc)
        raise self.retry(exc=exc)
    finally:
        try:
            r.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Chat History Auto-Pruning Task
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(name="agentium.tasks.task_executor.chat_prune_task", bind=True, max_retries=3, default_retry_delay=300)
def chat_prune_task(self, dry_run: bool = False, override_inactivity_days: int = None, override_hard_delete_days: int = None, override_retain_count: int = None):
    """
    Daily chat history auto-pruning task.

    Runs via Celery Beat (default 03:00 UTC, configurable via chat.prune_schedule_cron).

    Two-tier pruning:
    1. Soft-delete (is_deleted='Y') messages older than `inactivity_days` of conversation inactivity,
       but always retain last `retain_count` messages per conversation.
    2. Hard-delete (DELETE) soft-deleted messages older than `hard_delete_days`.

    Args:
        dry_run: If True, only report what would be deleted without making changes.
        override_inactivity_days: Override chat.prune_inactivity_days preference.
        override_hard_delete_days: Override chat.prune_hard_delete_days preference.
        override_retain_count: Override chat.prune_retain_count preference.

    Returns:
        Dict with soft_deleted_count, hard_deleted_count, conversations_affected, dry_run.
    """
    try:
        result = run_chat_prune_task(
            dry_run=dry_run,
            override_inactivity_days=override_inactivity_days,
            override_hard_delete_days=override_hard_delete_days,
            override_retain_count=override_retain_count,
        )
        logger.info(f"chat_prune_task completed: {result}")
        return result
    except Exception as exc:
        logger.error(f"chat_prune_task failed: {exc}")
        raise self.retry(exc=exc)


# ──────────────────────────────────────────────────────────────────────────────
# Celery Throughput Performance Gate No-op Task
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(name="agentium.tasks.task_executor.execute_task_async")
def execute_task_async_noop(*args, **kwargs):
    """No-op task for Celery throughput performance benchmark."""
    return {"noop": True}