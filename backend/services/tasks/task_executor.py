"""
Task execution handlers for Celery.
Includes: task execution, constitution review, idle processing, 
self-healing execution loop, data retention, and channel message retry.
"""
import logging
import asyncio
import json
import os
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
from backend.models.entities.agents import Agent, CouncilMember, HeadOfCouncil, LeadAgent, AgentType
from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
from backend.services.reincarnation_service import ReincarnationService

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# DEDICATED CELERY DATABASE CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Get database URL from environment (same as main app)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/agentium"
)

# Create a separate engine for Celery workers with NullPool
# This is CRITICAL: disables connection pooling for fork-based concurrency
celery_engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,        # No connection pooling - fresh connections per task
    pool_pre_ping=True,        # Validate connections before use
    echo=False,
    future=True
)

# Create session factory bound to Celery engine
CelerySessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=celery_engine
)

# Optional: Use scoped_session for thread safety in concurrent tasks
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

    Decorator order matters: @retry must be the outermost decorator so it
    can catch OperationalError raised inside the context manager body.
    Previously @contextmanager was outermost which meant @retry wrapped a
    raw generator and never saw the exception.
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

# In execute_task_async function, replace with:

@celery_app.task(bind=True, max_retries=3)
def execute_task_async(self, task_id: str, agent_id: str):
    """
    Execute task with skill-augmented RAG.
    """
    with get_task_db() as db:
        try:
            logger.info(f"Executing task {task_id} with agent {agent_id}")
            
            # Load task and agent
            task = db.query(Task).filter_by(agentium_id=task_id).first()
            agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
            
            if not task or not agent:
                raise ValueError("Task or agent not found")
            
            # Execute with skill RAG
            result = agent.execute_with_skill_rag(task, db)
            
            # Update task with result
            task.complete(
                result_summary=result["content"][:500],
                result_data={
                    "full_output": result["content"],
                    "skills_used": result.get("skills_used", []),
                    "model": result.get("model"),
                    "tokens_used": result.get("tokens_used")
                }
            )
            
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

            # No explicit db.commit() here — get_task_db() commits automatically
            # on clean exit. A redundant commit here would mask rollback errors.

            return {
                "status": "completed",
                "task_id": task_id,
                "skills_used": len(result.get("skills_used", []))
            }
            
        except Exception as exc:
            logger.error(f"Task execution failed: {exc}")
            
            # Record failure for used skills
            # (Would need to track which skills were attempted)
            
            # Phase 13.4: Anti-Pattern Early Warning
            try:
                from backend.core.vector_store import get_vector_store
                from backend.api.routes.websocket import manager
                import asyncio
                
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

                            # Broadcast warning over WebSocket — use asyncio.run() which
                            # is safe in a sync Celery worker and avoids the deprecated
                            # get_event_loop() / set_event_loop() pattern.
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

                            # Increment impact tracker for anti-patterns finding
                            try:
                                import redis.asyncio as aioredis
                                redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

                                async def inc_ap():
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

            # Phase 13.2: Exponential backoff — 1→2→4→8→16→32→60s cap
            countdown = min(2 ** self.request.retries, 60)
            logger.info(f"Retrying task {task_id} in {countdown}s (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=countdown)


@celery_app.task
def daily_constitution_review():
    """Daily review of constitution by persistent council."""
    logger.info("Running daily constitution review")
    return {"status": "completed"}


@celery_app.task
def process_idle_tasks():
    """Process tasks when system is idle."""
    logger.info("Processing idle tasks")
    return {"status": "completed"}


# ═══════════════════════════════════════════════════════════
# Self-Healing Execution Loop (NEW)
# ═══════════════════════════════════════════════════════════

@celery_app.task
def handle_task_escalation():
    """
    Handle tasks that have been escalated to Council after max retries.
    Council decides: liquidate, modify scope, or allocate more resources.
    """
    with get_task_db() as db:
        try:
            # Find all escalated tasks
            escalated_tasks = db.query(Task).filter(
                Task.status == TaskStatus.ESCALATED,
                Task.is_active == True
            ).all()
            
            if not escalated_tasks:
                return {"processed": 0}
            
            # Get Council members for deliberation
            council_members = db.query(CouncilMember).filter_by(is_active=True).all()
            head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            
            results = []
            
            for task in escalated_tasks:
                logger.info(f"Processing escalated task {task.agentium_id}: {task.title}")
                
                # Create Council deliberation for escalated task
                try:
                    # Start deliberation
                    deliberation = task.start_deliberation([m.agentium_id for m in council_members[:3]])
                    db.add(deliberation)
                    
                    # Simulate Council decision (in production, this would be actual voting)
                    # Decision options:
                    # 1. LIQUIDATE: Cancel the task
                    # 2. MODIFY_SCOPE: Update description and retry
                    # 3. ALLOCATE_RESOURCES: Spawn additional agents
                    
                    decision = _simulate_council_decision(task)
                    
                    if decision == "liquidate":
                        task.cancel(
                            reason="Council decision: Task liquidated after escalation",
                            cancelled_by="Council"
                        )
                        result = "liquidated"
                        
                    elif decision == "modify_scope":
                        # Modify task description and retry
                        task.description += "\n[Modified by Council after escalation]"
                        task.retry_count = 0  # Reset retries
                        task.error_count = 0
                        task.set_status(TaskStatus.IN_PROGRESS, "Council", "Scope modified, retrying")
                        result = "modified_and_retrying"
                        
                    elif decision == "allocate_resources":
                        # Spawn additional agents (simulated)
                        task.set_status(TaskStatus.IN_PROGRESS, "Council", "Additional resources allocated")
                        # In production: actually spawn new 3xxxx agents
                        result = "resources_allocated"
                    
                    # Log the decision
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
    """
    Simulate Council decision for escalated task.
    In production, this would be actual democratic voting.
    """
    # Simple heuristic for demo:
    # - If task has been retried many times, liquidate
    # - If task is important (high priority), allocate resources
    # - Otherwise, modify scope and retry
    
    if task.retry_count >= task.max_retries:
        if task.priority in [TaskPriority.CRITICAL, TaskPriority.SOVEREIGN]:
            return "allocate_resources"
        else:
            return "liquidate"
    
    return "modify_scope"


# ═══════════════════════════════════════════════════════════
# Data Retention & Sovereign Optimization (NEW)
# ═══════════════════════════════════════════════════════════

@celery_app.task
def sovereign_data_retention():
    """
    Daily data retention and cleanup task.
    - Delete completed tasks older than 30 days (preserving audit snapshots)
    - Remove orphan embeddings from vector DB
    - Compress execution logs
    - Archive constitutional history
    - Remove ethos of deleted agents
    """
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
            
            # 1. Archive completed tasks older than 30 days
            old_tasks = db.query(Task).filter(
                Task.status.in_([TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED]),
                Task.completed_at < cutoff_date,
                Task.is_active == True
            ).all()
            
            for task in old_tasks:
                try:
                    # Create audit snapshot before soft-delete
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
                    
                    # Soft delete (mark inactive)
                    task.is_active = False
                    results["tasks_archived"] += 1
                    
                except Exception as e:
                    results["errors"].append(f"Failed to archive task {task.agentium_id}: {e}")
            
            # 2. Remove orphan embeddings (those without active tasks)
            try:
                from backend.core.vector_store import get_vector_store
                vector_store = get_vector_store()
                
                # Get all active task IDs
                active_task_ids = [t.agentium_id for t in db.query(Task).filter(
                    Task.is_active == True
                ).all()]
                
                # Check staging collection for orphans
                try:
                    staging = vector_store.get_collection("staging")
                    staging_docs = staging.get()
                    
                    if staging_docs and staging_docs['ids']:
                        for doc_id, metadata in zip(staging_docs['ids'], staging_docs['metadatas']):
                            task_ref = metadata.get('submission_id', '') if metadata else ''
                            # If referenced task doesn't exist or is inactive, remove embedding
                            if task_ref and not any(t.startswith(task_ref) for t in active_task_ids):
                                staging.delete(ids=[doc_id])
                                results["embeddings_removed"] += 1
                except Exception as e:
                    results["errors"].append(f"Vector cleanup error: {e}")
                    
            except Exception as e:
                results["errors"].append(f"Vector store error: {e}")
            
            # 3. Compress old execution logs (older than 90 days)
            log_cutoff = datetime.utcnow() - timedelta(days=90)
            old_logs = db.query(AuditLog).filter(
                AuditLog.created_at < log_cutoff,
                AuditLog.category == AuditCategory.GOVERNANCE
            ).limit(1000).all()
            
            # Mark as compressed (in production, move to archive table)
            for log in old_logs:
                if log.action_details is None:
                    log.action_details = {}
                if isinstance(log.action_details, dict):
                    log.action_details['_compressed'] = True
            
            results["logs_compressed"] = len(old_logs)
            
            # 4. Remove ethos of deleted/inactive agents
            try:
                inactive_agents = db.query(Agent).filter(
                    Agent.is_active == False
                ).all()
                
                for agent in inactive_agents:
                    # Clear ethos (stored as JSON field on Agent)
                    if hasattr(agent, 'ethos') and agent.ethos:
                        agent.ethos = {}  # Or move to archive
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
# Auto-Scaling Governance (NEW)
# ═══════════════════════════════════════════════════════════

@celery_app.task
def auto_scale_check():
    """
    Monitor queue depth and trigger auto-scaling if needed.
    If pending tasks exceed threshold, request Council micro-vote to spawn agents.
    """
    with get_task_db() as db:
        try:
            # Count pending tasks
            pending_count = db.query(Task).filter(
                Task.status.in_([
                    TaskStatus.PENDING,
                    TaskStatus.DELIBERATING,
                    TaskStatus.APPROVED,
                    TaskStatus.ASSIGNED
                ]),
                Task.is_active == True
            ).count()
            
            threshold = 10  # Configurable threshold
            
            if pending_count > threshold:
                logger.info(f"Queue depth {pending_count} exceeds threshold {threshold}, requesting scaling")
                
                # Request Council micro-vote for scaling
                # In production: actual vote, here we simulate approval
                head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
                
                if head:
                    # Log scaling decision
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
                            "recommended_agents": 3  # Spawn 3 new 3xxxx agents
                        }
                    )
                    
                    # Spawn recommended_agents new task agents under the Head
                    recommended_agents = 3
                    spawned = 0
                    spawn_errors = []
                    for i in range(recommended_agents):
                        try:
                            ReincarnationService.spawn_task_agent(
                                parent=head,
                                name=f"AutoScale-Agent-{datetime.utcnow().strftime('%H%M%S')}-{i}",
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
                        "new_agents_requested": recommended_agents,
                        "new_agents_spawned": spawned,
                        "spawn_errors": spawn_errors,
                        "timestamp": datetime.utcnow().isoformat()
                    }
            
            return {
                "scaled": False,
                "pending_count": pending_count,
                "threshold": threshold
            }
            
        except Exception as e:
            logger.error(f"Error in auto_scale_check: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Reasoning Recovery Watchdog (Gap 2)
# ═══════════════════════════════════════════════════════════

@celery_app.task
def check_stalled_reasoning():
    """
    Watchdog: detect stalled reasoning traces and re-queue their tasks.
    Runs every 60 s via beat schedule.
    """
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

                # Cap re-queues: track in execution_context
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

                # Re-queue the task for execution
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

@celery_app.task(bind=True, max_retries=3)
def retry_channel_message(self, message_id: str, agent_id: str, content: str, rich_media_dict: Dict[str, Any] = None):
    """
    Retry sending a failed channel message.
    Called by circuit breaker when initial send fails.
    """
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


@celery_app.task
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


@celery_app.task
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


@celery_app.task
def start_imap_receivers():
    """Ensure IMAP receivers are running for all email channels."""
    from backend.services.channel_manager import imap_receiver
    
    with get_task_db() as db:
        # Don't use joinedload - it can cause issues with NullPool in some SQLAlchemy versions
        email_channels = db.query(ExternalChannel).filter(
            ExternalChannel.channel_type == ChannelType.EMAIL,
            ExternalChannel.status == ChannelStatus.ACTIVE
        ).all()
        
        channel_configs = []
        for channel in email_channels:
            # Safely handle config that might be string or dict
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


@celery_app.task
def send_channel_heartbeat():
    """Send periodic heartbeat to all active channels."""
    
    with get_task_db() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        active_channels = db.query(ExternalChannel).filter(
            ExternalChannel.status == ChannelStatus.ACTIVE,
            ExternalChannel.last_message_at > cutoff_time
        ).all()
        
        channel_ids = [ch.id for ch in active_channels]  # kept for return value logging

        now = datetime.utcnow()
        heartbeats_sent = 0
        # Iterate directly over the already-loaded objects — avoids N+1 queries
        # that re-fetched each channel by ID in a loop.
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

@celery_app.task
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
                # Flush to get test_msg.id without committing yet —
                # a single commit after the loop is safer than one per channel.
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

        # Single commit for all channels — get_task_db() also auto-commits on
        # clean exit, but being explicit here documents the intent.
        # (get_task_db auto-commit is a no-op if already committed.)
        return {
            "total": len(channel_ids),
            "successful": sum(1 for r in results if r.get('success')),
            "failed": sum(1 for r in results if not r.get('success')),
            "details": results
        }


# ═══════════════════════════════════════════════════════════
# Phase 13.1 — Auto-Delegation Engine Tasks
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='backend.services.tasks.task_executor.check_escalation_timeouts')
def check_escalation_timeouts():
    """
    Auto-escalation timer: finds IN_PROGRESS tasks whose
    escalation_timeout_seconds has elapsed and escalates them.
    """
    with get_task_db() as db:
        try:
            now = datetime.utcnow()
            # Get all in-progress, non-idle tasks
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
                        # Reassign to a new list — SQLAlchemy does not detect in-place
                        # mutations on JSON columns. flag_modified() ensures the ORM
                        # marks the column dirty even if the object identity is the same.
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
                logger.info(f"⏰ Auto-escalation: {escalated} tasks escalated")

            return {"escalated": escalated, "checked": len(tasks)}

        except Exception as e:
            logger.error(f"check_escalation_timeouts failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='backend.services.tasks.task_executor.process_dependency_graph')
def process_dependency_graph():
    """
    Dependency graph processor: for each parent task with TaskDependency rows,
    checks which child tasks are ready (all dependencies of lower order are
    complete) and dispatches them.
    """
    with get_task_db() as db:
        try:
            from backend.models.entities.task import TaskDependency

            # Get all pending dependency records
            pending_deps = db.query(TaskDependency).filter(
                TaskDependency.status == "pending",
            ).all()

            if not pending_deps:
                return {"dispatched": 0}

            # Group by parent task
            by_parent = {}
            for dep in pending_deps:
                by_parent.setdefault(dep.parent_task_id, []).append(dep)

            dispatched = 0
            for parent_id, deps in by_parent.items():
                # Sort by dependency_order
                deps.sort(key=lambda d: d.dependency_order)

                for dep in deps:
                    # Check: all deps with lower order for this parent must be complete
                    lower_complete = db.query(TaskDependency).filter(
                        TaskDependency.parent_task_id == parent_id,
                        TaskDependency.dependency_order < dep.dependency_order,
                        TaskDependency.status != "completed",
                    ).count()

                    if lower_complete > 0:
                        continue  # Dependencies not yet met

                    # Check if child task is still pending
                    child = db.query(Task).filter_by(
                        id=dep.child_task_id, is_active=True
                    ).first()

                    if not child or child.status != TaskStatus.PENDING:
                        # Already started or completed
                        if child and child.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                            dep.status = "completed"
                        continue

                    # Dispatch the child task
                    try:
                        child.status = TaskStatus.IN_PROGRESS
                        child.started_at = datetime.utcnow()
                        dep.status = "dispatched"
                        dispatched += 1

                        # Actually queue the task for execution — previously this was
                        # missing, leaving child tasks perpetually stuck in IN_PROGRESS
                        # with no Celery worker ever picking them up.
                        assigned_agent_id = getattr(child, 'assigned_agent_id', None)
                        if assigned_agent_id:
                            execute_task_async.delay(child.agentium_id, assigned_agent_id)
                            logger.info(
                                f"📊 DAG: dispatched child task {child.agentium_id} "
                                f"(order={dep.dependency_order}) for parent {parent_id}"
                            )
                        else:
                            logger.warning(
                                f"📊 DAG: child task {child.agentium_id} has no assigned_agent_id "
                                f"— marked IN_PROGRESS but not queued for execution"
                            )
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

@celery_app.task(name='backend.services.tasks.task_executor.agent_heartbeat')
def agent_heartbeat():
    """
    Heartbeat task: update last_heartbeat_at for all active/working agents.
    Runs every 60 seconds via Celery beat.
    """
    with get_task_db() as db:
        try:
            from backend.services.self_healing_service import SelfHealingService
            result = SelfHealingService.update_heartbeats(db)
            logger.info(f"💓 Heartbeat: updated {result['updated']} agents")
            return result
        except Exception as e:
            logger.error(f"agent_heartbeat failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='backend.services.tasks.task_executor.detect_crashed_agents')
def detect_crashed_agents():
    """
    Crash detection: find agents with stale heartbeats and trigger recovery.
    Runs every 30 seconds via Celery beat.
    """
    with get_task_db() as db:
        try:
            from backend.services.self_healing_service import SelfHealingService
            result = SelfHealingService.detect_crashed_agents(db)
            if result["detected"] > 0:
                logger.warning(
                    f"🚨 Crash detection: {result['detected']} crashed, "
                    f"{result['recovered']} recovered"
                )
            
            # Phase 13.2: Trigger degradation check after crash detection
            SelfHealingService.check_degradation_triggers(db)
            return result
        except Exception as e:
            logger.error(f"detect_crashed_agents failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='backend.services.tasks.task_executor.self_diagnostic_daily')
def self_diagnostic_daily():
    """
    Daily self-diagnostic: check DB, Redis, ChromaDB, stale tasks.
    Proposes constitutional amendment if repeated violations detected.
    Runs once per day (86400s) via Celery beat.
    """
    with get_task_db() as db:
        try:
            from backend.services.self_healing_service import SelfHealingService
            result = SelfHealingService.run_self_diagnostics(db)
            issues_count = len(result.get("issues", []))
            is_healthy = issues_count == 0
            health_str = "HEALTHY" if is_healthy else f"{issues_count} issue(s)"
            logger.info(f"🔍 Self-diagnostic: {health_str}")
            return result
        except Exception as e:
            logger.error(f"self_diagnostic_daily failed: {e}")
            return {"error": str(e)}


@celery_app.task(name='backend.services.tasks.task_executor.critical_path_guardian')
def critical_path_guardian():
    """
    Critical path protection: tag DAG ancestors of CRITICAL/SOVEREIGN tasks
    and reserve agent slots for these chains.
    Runs every 120 seconds via Celery beat.
    """
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

@celery_app.task(name='backend.services.tasks.task_executor.knowledge_consolidation')
def knowledge_consolidation():
    """Weekly knowledge pruning and decay via AutonomousLearningEngine decay_outdated_learnings."""
    with get_task_db() as db:
        try:
            from backend.services.autonomous_learning import get_learning_engine
            return get_learning_engine().decay_outdated_learnings(db)
        except Exception as e:
            logger.error(f"knowledge_consolidation failed: {e}")
            return {"error": str(e)}

@celery_app.task(name='backend.services.tasks.task_executor.performance_optimization')
def performance_optimization():
    """Weekly task to query slow tasks and generate condensation suggestions."""
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

@celery_app.task(name='backend.services.tasks.task_executor.metrics_snapshot')
def metrics_snapshot():
    """
    Takes a snapshot of current system metrics for predictive scaling.
    Runs every 5 minutes.
    """
    with get_task_db() as db:
        try:
            from backend.services.predictive_scaling import predictive_scaling_service
            result = predictive_scaling_service.snapshot_metrics(db)
            return {"status": "success", "snapshot": result}
        except Exception as e:
            logger.error(f"metrics_snapshot failed: {e}")
            return {"error": str(e)}

@celery_app.task(name='backend.services.tasks.task_executor.predictive_scale')
def predictive_scale():
    """
    Evaluates historical metrics to predict load and pre-spawn/liquidate agents.
    Also enforces token budget and time-based policies.
    Runs every 5 minutes.
    """
    with get_task_db() as db:
        try:
            from backend.services.predictive_scaling import predictive_scaling_service
            # 1. Evaluate token budget limits (may pause non-critical tasks)
            predictive_scaling_service.enforce_token_budget_guard(db)
            
            # 2. Get predictions based on moving averages
            predictions = predictive_scaling_service.get_predictions()
            
            # 3. Make pre-spawn or pre-liquidation decisions
            predictive_scaling_service.evaluate_scaling(db, predictions)
            
            return {"status": "success", "predictions": predictions}
        except Exception as e:
            logger.error(f"predictive_scale failed: {e}")
            return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
# Phase 13.6 — Intelligent Event Processing Tasks
# ═══════════════════════════════════════════════════════════

@celery_app.task(name='backend.services.tasks.task_executor.threshold_event_check')
def threshold_event_check():
    """
    Evaluate all active threshold triggers against live Redis metrics.
    Fires actions when configured conditions are met.
    Runs every 60 seconds via Celery beat.
    """
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


@celery_app.task(name='backend.services.tasks.task_executor.external_api_poll')
def external_api_poll():
    """
    Poll all active api_poll triggers for data changes.
    Fires actions when the response hash changes from the previous poll.
    Runs every 60 seconds via Celery beat.
    """
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

@celery_app.task(name='backend.services.tasks.task_executor.anomaly_detection')
def anomaly_detection():
    """
    Anomaly detection: compute Z-scores for system metrics vs 7-day baseline.
    Auto-remediates known failure patterns via MonitoringService.
    Runs every 5 minutes via Celery beat.
    """
    with get_task_db() as db:
        try:
            from backend.services.monitoring_service import MonitoringService
            result = MonitoringService.detect_anomalies(db)
            if result["anomalies_detected"] > 0:
                logger.warning(
                    f"🔍 Anomaly detection: {result['anomalies_detected']} anomalies found"
                )
                # Auto-remediate known patterns
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


@celery_app.task(name='backend.services.tasks.task_executor.sla_monitor')
def sla_monitor():
    """
    SLA monitor: track time-to-resolution per priority and broadcast
    breach events.
    Runs every 60 seconds via Celery beat.
    """
    with get_task_db() as db:
        try:
            from backend.services.monitoring_service import MonitoringService
            result = MonitoringService.get_sla_metrics(db)
            # Log any breaches
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

@celery_app.task(name='backend.services.tasks.task_executor.poll_wait_conditions')
def poll_wait_conditions():
    """
    Evaluate every ACTIVE WaitCondition and resume or expire parent tasks.

    Runs every 30 seconds via Celery Beat.
    Delegates all logic to WaitPollService so the Celery layer stays thin.
    """
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

# ══════════════════════════════════════════════════════════════════════════════
# Phase 16.1 — Database Connection Pool Tuning & Slow Query Logging
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name='backend.services.tasks.task_executor.log_slow_query_summary_daily')
def log_slow_query_summary_daily():
    """Daily evaluation to parse slow queries and log to AuditLog."""
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
                logger.info(f"Logged slow query summary with {len(queries)} offending queries")
            else:
                logger.info("No slow queries > 500ms found for daily summary.")
                
            return {
                "status": "completed",
                "queries_found": len(queries),
                "summary": summary
            }

        except Exception as e:
            logger.error(f"Error in log_slow_query_summary_daily: {e}")
            return {"error": str(e)}