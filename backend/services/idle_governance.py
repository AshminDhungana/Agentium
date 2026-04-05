"""
Enhanced Idle Governance Service with Metrics Tracking.
Adds scheduled auto-liquidation, resource rebalancing, and comprehensive metrics.
"""

import asyncio
import random
import time
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import logging

logger = logging.getLogger(__name__)

from backend.models.database import get_db_context
from backend.models.entities.agents import Agent, HeadOfCouncil, CouncilMember, AgentStatus, PersistentAgentRole
from backend.models.entities.task import Task, TaskType, TaskStatus, TaskPriority
from backend.services.persistent_council import persistent_council
from backend.services.token_optimizer import token_optimizer, idle_budget
from backend.services.reincarnation_service import reincarnation_service


class IdleGovernanceMetrics:
    """
    Tracks metrics for idle governance operations.
    """
    
    def __init__(self):
        self.session_start = None
        self.total_idle_tasks_completed = 0
        self.total_tokens_saved = 0
        self.agent_lifetimes: Dict[str, timedelta] = {}
        self.idle_terminations = 0
        self.resource_rebalancing_count = 0
        self.last_rebalancing_improvement = 0.0
    
    def record_idle_task_completion(self, tokens_saved: int):
        """Record completion of an idle task."""
        self.total_idle_tasks_completed += 1
        self.total_tokens_saved += tokens_saved
    
    def record_agent_lifetime(self, agentium_id: str, created_at: datetime, terminated_at: datetime):
        """Record agent lifetime for averaging."""
        lifetime = terminated_at - created_at
        self.agent_lifetimes[agentium_id] = lifetime
    
    def record_idle_termination(self):
        """Record an idle agent termination."""
        self.idle_terminations += 1
    
    def record_rebalancing(self, improvement_percentage: float):
        """Record resource rebalancing operation."""
        self.resource_rebalancing_count += 1
        self.last_rebalancing_improvement = improvement_percentage
    
    def get_average_agent_lifetime(self) -> Dict[str, Any]:
        """Calculate average agent lifetime."""
        if not self.agent_lifetimes:
            return {
                "average_hours": 0,
                "average_days": 0,
                "sample_size": 0
            }
        
        total_seconds = sum(td.total_seconds() for td in self.agent_lifetimes.values())
        avg_seconds = total_seconds / len(self.agent_lifetimes)
        
        return {
            "average_hours": round(avg_seconds / 3600, 2),
            "average_days": round(avg_seconds / 86400, 2),
            "sample_size": len(self.agent_lifetimes),
            "shortest_hours": round(min(td.total_seconds() for td in self.agent_lifetimes.values()) / 3600, 2),
            "longest_hours": round(max(td.total_seconds() for td in self.agent_lifetimes.values()) / 3600, 2)
        }
    
    def get_idle_termination_rate(self) -> Dict[str, Any]:
        """Calculate idle termination rate."""
        if not self.session_start:
            return {"rate_per_day": 0, "total": 0}
        
        session_duration = (datetime.utcnow() - self.session_start).total_seconds()
        days = session_duration / 86400
        
        rate = self.idle_terminations / days if days > 0 else 0
        
        return {
            "rate_per_day": round(rate, 2),
            "total": self.idle_terminations,
            "session_days": round(days, 2)
        }
    
    def get_resource_utilization(self) -> Dict[str, Any]:
        """Get resource utilization metrics."""
        return {
            "rebalancing_operations": self.resource_rebalancing_count,
            "last_improvement_percentage": round(self.last_rebalancing_improvement, 2),
            "tokens_saved_total": self.total_tokens_saved,
            "idle_tasks_completed": self.total_idle_tasks_completed
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Export all metrics as dict."""
        return {
            "agent_lifetime": self.get_average_agent_lifetime(),
            "idle_termination_rate": self.get_idle_termination_rate(),
            "resource_utilization": self.get_resource_utilization()
        }


class EnhancedIdleGovernanceEngine:
    """
    Enhanced idle governance with scheduled tasks and metrics.
    """
    
    def __init__(self):
        self.is_running = False
        self.idle_loop_task: Optional[asyncio.Task] = None
        self.check_interval = 10  # Check for work every 10 seconds
        self.current_idle_tasks: Dict[str, str] = {}
        self.last_idle_summary = None
        self.idle_session_start = None
        
        # Metrics tracker
        self.metrics = IdleGovernanceMetrics()
        
        # Scheduled task intervals (in seconds)
        self.IDLE_DETECTION_INTERVAL = 86400  # 24 hours
        self.AUTO_LIQUIDATE_INTERVAL = 21600   # 6 hours
        self.REBALANCING_INTERVAL = 3600       # 1 hour
        
        # Last execution times
        self.last_idle_detection = None
        self.last_auto_liquidate = None
        self.last_rebalancing = None
        
        # Configuration
        self.IDLE_THRESHOLD_DAYS = 7  # Agents idle for >7 days are candidates for termination

        # ── FIX 3 & 4: Per-agent cooldown tracking ──────────────────────────────
        # Tracks the last time each agent completed an idle task (any type).
        # Prevents re-assignment until cooldown expires.
        self._agent_last_completed: Dict[str, datetime] = {}   # key: agent_id
        self.IDLE_TASK_COOLDOWN_SECONDS = 60  # minimum gap between idle tasks per agent

        # Tracks the last time preference_optimization ran per agent.
        # Used to pass real elapsed minutes to should_run() instead of hardcoded 30.
        self._last_pref_opt_run: Dict[str, datetime] = {}      # key: agent_id
        self.PREF_OPT_COOLDOWN_MINUTES = 30
        self._recent_system_tasks: Dict[str, datetime] = {}   # task_type.value -> last_completed
        self.SYSTEM_TASK_COOLDOWN_SECONDS = 300  # 5 min between same system task
        # ────────────────────────────────────────────────────────────────────────
    
    async def start(self, db: Session):
        """Start the eternal idle governance loop with scheduled tasks."""
        if self.is_running:
            return
        
        self.is_running = True
        self.idle_session_start = datetime.utcnow()
        self.metrics.session_start = self.idle_session_start
        
        logger.info("🌙 ENHANCED IDLE GOVERNANCE ENGINE STARTED")
        logger.info("   Persistent Council is now eternally active...")
        logger.info("   Scheduled tasks enabled:")
        logger.info(f"     - Idle detection: every {self.IDLE_DETECTION_INTERVAL / 3600} hours")
        logger.info(f"     - Auto-liquidation: every {self.AUTO_LIQUIDATE_INTERVAL / 3600} hours")
        logger.info(f"     - Resource rebalancing: every {self.REBALANCING_INTERVAL / 3600} hours")
        logger.info(f"     - Per-agent cooldown: {self.IDLE_TASK_COOLDOWN_SECONDS}s between tasks")
        logger.info(f"     - Preference-opt cooldown: {self.PREF_OPT_COOLDOWN_MINUTES}min per agent")
        
        # Start the main loop
        self.idle_loop_task = asyncio.create_task(self._idle_loop())
        
        # Broadcast that idle mode is operational
        await self._broadcast({
            'type': 'idle_engine',
            'event': 'started',
            'message': 'Enhanced Persistent Council now active with scheduled optimization',
            'council_members': ['00001', '10001', '10002'],
            'timestamp': datetime.utcnow().isoformat()
        })
        
    
    async def stop(self):
        """Stop the idle governance engine."""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.idle_loop_task:
            self.idle_loop_task.cancel()
            try:
                await self.idle_loop_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 ENHANCED IDLE GOVERNANCE ENGINE STOPPED")
        logger.info(f"   Session duration: {(datetime.utcnow() - self.idle_session_start).total_seconds() / 3600:.2f} hours")
        logger.info(f"   Metrics summary: {self.metrics.to_dict()}")
        
        await self._broadcast({
            'type': 'idle_engine',
            'event': 'stopped',
            'metrics': self.metrics.to_dict(),
            'timestamp': datetime.utcnow().isoformat()
        })
    
    async def _idle_loop(self):
        """Main eternal loop with scheduled task execution."""
        while self.is_running:
            db = None
            try:
                with get_db_context() as db:
                    # Execute scheduled tasks
                    await self._run_scheduled_tasks(db)
                    
                    # Check if there are user tasks pending
                    user_tasks = self._get_pending_user_tasks(db)
                    
                    if user_tasks:
                        # Pause idle work until user tasks are handled
                        await self._pause_idle_work(db, reason=f"{len(user_tasks)} user tasks pending")
                        await asyncio.sleep(5)
                        continue
                    
                    # Get available persistent agents
                    available_agents = self._get_available_persistent_agents(db)
                    
                    if not available_agents:
                        await asyncio.sleep(self.check_interval)
                        continue
                    
                    # Assign work to each available agent
                    for agent in available_agents:
                        await self._assign_idle_work(db, agent)
                    
                    # Execute the work
                    await self._execute_idle_work(db, available_agents)
                    
                    # Small delay to prevent CPU spinning
                    await asyncio.sleep(self.check_interval)
                    
            except Exception as e:
                logger.error(f"❌ Error in idle loop: {e}")
                if db:
                    try:
                        db.rollback()
                    except:
                        pass
                await asyncio.sleep(self.check_interval)
    
    # ═══════════════════════════════════════════════════════════
    # SCHEDULED TASKS
    # ═══════════════════════════════════════════════════════════
    
    async def _run_scheduled_tasks(self, db: Session):
        """Execute scheduled maintenance tasks."""
        now = datetime.utcnow()
        
        # Task 1: Idle Agent Detection (daily)
        if (self.last_idle_detection is None or 
            (now - self.last_idle_detection).total_seconds() >= self.IDLE_DETECTION_INTERVAL):
            await self.detect_idle_agents(db)
            self.last_idle_detection = now
        
        # Task 2: Auto-Liquidation (every 6 hours)
        if (self.last_auto_liquidate is None or 
            (now - self.last_auto_liquidate).total_seconds() >= self.AUTO_LIQUIDATE_INTERVAL):
            await self.auto_liquidate_expired(db)
            self.last_auto_liquidate = now
        
        # Task 3: Resource Rebalancing (hourly)
        if (self.last_rebalancing is None or 
            (now - self.last_rebalancing).total_seconds() >= self.REBALANCING_INTERVAL):
            await self.resource_rebalancing(db)
            self.last_rebalancing = now
    
    async def detect_idle_agents(self, db: Session) -> List[str]:
        """
        Detect agents that have been idle for >7 days.
        Returns list of idle agent IDs.
        """
        threshold = datetime.utcnow() - timedelta(days=self.IDLE_THRESHOLD_DAYS)
        
        # Find agents with no activity in threshold period
        idle_agents = db.query(Agent).filter(
            and_(
                Agent.is_active == True,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_persistent == False,  # Don't auto-terminate persistent agents
                Agent.last_idle_action_at < threshold
            )
        ).all()
        
        idle_ids = [agent.agentium_id for agent in idle_agents]
        
        if idle_ids:
            logger.info(f"🔍 Idle Agent Detection: Found {len(idle_ids)} agents idle for >{self.IDLE_THRESHOLD_DAYS} days")
            logger.info(f"   Idle agents: {', '.join(idle_ids)}")
            
            # Log the detection
            from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
            audit = AuditLog.log(
                level=AuditLevel.INFO,
                category=AuditCategory.GOVERNANCE,
                actor_type="system",
                actor_id="IDLE_GOVERNANCE",
                action="idle_agents_detected",
                description=f"Detected {len(idle_ids)} idle agents for potential liquidation",
                meta_data={
                    "idle_agents": idle_ids,
                    "threshold_days": self.IDLE_THRESHOLD_DAYS,
                    "detection_time": datetime.utcnow().isoformat()
                }
            )
            db.add(audit)
        
        return idle_ids
    
    async def auto_liquidate_expired(self, db: Session) -> Dict[str, Any]:
        """
        Auto-liquidate agents that have been idle for >7 days with no assigned tasks.
        Returns liquidation summary.
        """
        threshold = datetime.utcnow() - timedelta(days=self.IDLE_THRESHOLD_DAYS)
        
        # Find idle agents with NO active tasks
        idle_agents = db.query(Agent).filter(
            and_(
                Agent.is_active == True,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_persistent == False,
                Agent.last_idle_action_at < threshold
            )
        ).all()
        
        liquidated = []
        skipped = []
        
        # Get Head agent for liquidation authority
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        
        if not head:
            # We don't want to spam warnings if Genesis hasn't run yet.
            if not getattr(self, '_head_missing_logged', False):
                logger.info("ℹ️ Auto-liquidation skipped: Head of Council not found (Genesis likely hasn't run yet)")
                self._head_missing_logged = True
            return {"liquidated": [], "skipped": [], "reason": "no_head"}
        
        for agent in idle_agents:
            # Check if agent has any active tasks
            active_tasks = db.query(Task).filter(
                Task.assigned_task_agent_ids.contains([agent.agentium_id]),
                Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.DELIBERATING]),
                Task.is_active == True
            ).count()
            
            if active_tasks > 0:
                skipped.append({
                    "agentium_id": agent.agentium_id,
                    "reason": f"has {active_tasks} active tasks"
                })
                continue
            
            # Liquidate the agent
            try:
                result = reincarnation_service.liquidate_agent(
                    agent_id=agent.agentium_id,
                    liquidated_by=head,
                    reason=f"Auto-liquidation: idle for >{self.IDLE_THRESHOLD_DAYS} days with no active tasks",
                    db=db
                )
                
                liquidated.append(agent.agentium_id)
                
                # Record metrics
                if agent.created_at:
                    self.metrics.record_agent_lifetime(
                        agent.agentium_id,
                        agent.created_at,
                        datetime.utcnow()
                    )
                self.metrics.record_idle_termination()
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to liquidate {agent.agentium_id}: {e}")
                skipped.append({
                    "agentium_id": agent.agentium_id,
                    "reason": f"error: {str(e)}"
                })
        
        summary = {
            "liquidated": liquidated,
            "liquidated_count": len(liquidated),
            "skipped": skipped,
            "skipped_count": len(skipped),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if liquidated:
            logger.info(f"🔻 Auto-Liquidation Complete: {len(liquidated)} agents terminated")
            logger.info(f"   Terminated: {', '.join(liquidated)}")
        
        if skipped:
            logger.info(f"   Skipped: {len(skipped)} agents (have active tasks or errors)")
        
        return summary
    
    async def resource_rebalancing(self, db: Session) -> Dict[str, Any]:
        """
        Redistribute work from overloaded agents to underutilized ones.
        Returns rebalancing summary.
        """
        # Get all active agents (excluding persistent ones)
        agents = db.query(Agent).filter(
            Agent.is_active == True,
            Agent.status == AgentStatus.ACTIVE,
            Agent.is_persistent == False
        ).all()
        
        if len(agents) < 2:
            return {
                "rebalanced": False,
                "reason": "insufficient_agents",
                "agent_count": len(agents)
            }
        
        # Calculate task load per agent
        agent_loads = []
        
        for agent in agents:
            active_tasks = db.query(Task).filter(
                Task.assigned_task_agent_ids.contains([agent.agentium_id]),
                Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.DELIBERATING]),
                Task.is_active == True
            ).count()
            
            agent_loads.append({
                "agent": agent,
                "agentium_id": agent.agentium_id,
                "task_count": active_tasks
            })
        
        # Sort by task count
        agent_loads.sort(key=lambda x: x["task_count"], reverse=True)
        
        # Identify overloaded (top 25%) and underutilized (bottom 25%)
        total = len(agent_loads)
        overloaded = agent_loads[:max(1, total // 4)]
        underutilized = agent_loads[-max(1, total // 4):]
        
        # Calculate average load
        avg_load = sum(a["task_count"] for a in agent_loads) / total if total > 0 else 0
        
        # Only rebalance if there's significant imbalance (>50% deviation)
        max_load = overloaded[0]["task_count"] if overloaded else 0
        min_load = underutilized[0]["task_count"] if underutilized else 0
        
        if avg_load == 0 or (max_load - min_load) / avg_load < 0.5:
            return {
                "rebalanced": False,
                "reason": "balanced_already",
                "max_load": max_load,
                "min_load": min_load,
                "avg_load": round(avg_load, 2)
            }
        
        # Rebalance: move tasks from overloaded to underutilized
        tasks_moved = 0
        
        for overloaded_agent_info in overloaded:
            if not underutilized:
                break
            
            overloaded_agent = overloaded_agent_info["agent"]
            
            # Get this agent's tasks
            tasks = db.query(Task).filter(
                Task.assigned_task_agent_ids.contains([overloaded_agent.agentium_id]),
                Task.status.in_([TaskStatus.PENDING, TaskStatus.DELIBERATING]),
                Task.is_active == True
            ).limit(2).all()  # Move max 2 tasks per agent
            
            for task in tasks:
                if not underutilized:
                    break
                
                # Assign to underutilized agent
                underutilized_agent_info = underutilized.pop(0)
                underutilized_agent = underutilized_agent_info["agent"]
                
                # Update task assignment
                if task.assigned_task_agent_ids and overloaded_agent.agentium_id in task.assigned_task_agent_ids:
                    task.assigned_task_agent_ids.remove(overloaded_agent.agentium_id)
                    task.assigned_task_agent_ids.append(underutilized_agent.agentium_id)
                    
                    # Log the reassignment
                    task._log_status_change(
                        "rebalanced",
                        "IDLE_GOVERNANCE",
                        f"Task rebalanced: {overloaded_agent.agentium_id} → {underutilized_agent.agentium_id}"
                    )
                    
                    tasks_moved += 1
                
                # Re-add to underutilized if they still have capacity
                underutilized_agent_info["task_count"] += 1
                if underutilized_agent_info["task_count"] < avg_load:
                    underutilized.append(underutilized_agent_info)
        
        db.commit()
        
        # Calculate improvement
        improvement = (tasks_moved / max_load * 100) if max_load > 0 else 0
        self.metrics.record_rebalancing(improvement)
        
        summary = {
            "rebalanced": True,
            "tasks_moved": tasks_moved,
            "improvement_percentage": round(improvement, 2),
            "before": {
                "max_load": max_load,
                "min_load": min_load,
                "avg_load": round(avg_load, 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if tasks_moved > 0:
            logger.info(f"⚖️ Resource Rebalancing Complete: {tasks_moved} tasks redistributed")
            logger.info(f"   Improvement: {improvement:.1f}%")
        
        return summary
    
    # ═══════════════════════════════════════════════════════════
    # EXISTING IDLE WORK METHODS (from original implementation)
    # ═══════════════════════════════════════════════════════════
    
    def _get_pending_user_tasks(self, db: Session) -> List[Task]:
        """Get non-idle tasks that need attention."""
        return db.query(Task).filter(
            Task.is_idle_task == False,
            Task.status.in_([
                TaskStatus.PENDING,
                TaskStatus.DELIBERATING,
                TaskStatus.IN_PROGRESS
            ]),
            Task.is_active == True
        ).all()
    
    def _get_available_persistent_agents(self, db: Session) -> List[Agent]:
        """
        Get persistent agents ready for idle work.

        FIX 1: Only return ACTIVE agents — agents already in IDLE_WORKING status
        have a task in progress and must NOT be assigned another one.
        """
        return db.query(Agent).filter(
            Agent.is_persistent == True,
            Agent.is_active == True,
            Agent.status == AgentStatus.ACTIVE  # FIXED: was .in_([ACTIVE, IDLE_WORKING])
        ).order_by(Agent.last_idle_action_at).all()
    
    async def _assign_idle_work(self, db: Session, agent: Agent):
        """
        Assign appropriate idle work to agent based on role.
        One idle task per agent enforced at both in-memory and DB level.
        
        FIX 5: System-wide tasks (audit, storage, health, cache, vector) now run
        only once globally per cooldown period, not per agent.
        """
        # ── Guard 1: in-memory tracking ─────────────────────────────────────────
        if agent.agentium_id in self.current_idle_tasks:
            return

        # ── Guard 2: cooldown since last completion ─────────────────────────────
        last_completed = self._agent_last_completed.get(agent.agentium_id)
        if last_completed:
            elapsed_since_completion = (datetime.utcnow() - last_completed).total_seconds()
            if elapsed_since_completion < self.IDLE_TASK_COOLDOWN_SECONDS:
                logger.debug(
                    f"Agent {agent.agentium_id} on cooldown "
                    f"({elapsed_since_completion:.0f}s / {self.IDLE_TASK_COOLDOWN_SECONDS}s)"
                )
                return

        # ── Guard 3: DB-level hard check ────────────────────────────────────────
        existing_active = db.query(Task).filter(
            Task.is_idle_task == True,
            Task.is_active == True,
            Task.status == TaskStatus.IN_PROGRESS,
        ).all()

        for existing in existing_active:
            if existing.assigned_task_agent_ids and agent.agentium_id in existing.assigned_task_agent_ids:
                logger.debug(
                    f"Agent {agent.agentium_id} already has active idle task "
                    f"({existing.agentium_id}) in DB — skipping"
                )
                self.current_idle_tasks[agent.agentium_id] = str(existing.id)
                return

        # ── Import idle tasks ────────────────────────────────────────────────────
        from backend.services.idle_tasks.preference_optimizer import preference_optimizer_task

        # ── Define task categories ───────────────────────────────────────────────
        PER_AGENT_TASKS = [
            TaskType.CONSTITUTION_REFINE,
            TaskType.CONSTITUTION_READ,
            TaskType.PREDICTIVE_PLANNING,
            TaskType.ETHOS_OPTIMIZATION,
        ]
        
        SYSTEM_WIDE_TASKS = [
            TaskType.VECTOR_MAINTENANCE,
            TaskType.STORAGE_DEDUPE,
            TaskType.AUDIT_ARCHIVAL,
            TaskType.AGENT_HEALTH_SCAN,
            TaskType.CACHE_OPTIMIZATION,
        ]

        # ── Determine task type based on agent role ──────────────────────────────
        if agent.agentium_id == '00001':
            # Head gets preference optimization if due, otherwise per-agent tasks
            last_pref_run = self._last_pref_opt_run.get(agent.agentium_id)
            if last_pref_run:
                elapsed_pref_minutes = int(
                    (datetime.utcnow() - last_pref_run).total_seconds() / 60
                )
            else:
                elapsed_pref_minutes = 9999

            if preference_optimizer_task.should_run(elapsed_pref_minutes):
                task_type = TaskType.PREFERENCE_OPTIMIZATION
            else:
                task_type = random.choice(PER_AGENT_TASKS)
        else:
            # Council members get preference optimization if due
            last_pref_run = self._last_pref_opt_run.get(agent.agentium_id)
            if last_pref_run:
                elapsed_pref_minutes = int(
                    (datetime.utcnow() - last_pref_run).total_seconds() / 60
                )
            else:
                elapsed_pref_minutes = 9999

            if preference_optimizer_task.should_run(elapsed_pref_minutes):
                task_type = TaskType.PREFERENCE_OPTIMIZATION
            else:
                # Check if any system-wide task is available (not recently run)
                available_system = self._get_available_system_tasks()
                
                if available_system:
                    task_type = available_system[0]  # Take first available
                    # ❌ REMOVED: Don't mark as assigned here — do it after DB check
                else:
                    # All system tasks on cooldown, assign per-agent task
                    task_type = random.choice(PER_AGENT_TASKS)

        # ── FIX 5: Check if this system task is already assigned to another agent ─
        if task_type in SYSTEM_WIDE_TASKS:
            # First check: is this task type on global cooldown?
            last_run = self._recent_system_tasks.get(task_type.value)
            if last_run:
                elapsed = (datetime.utcnow() - last_run).total_seconds()
                if elapsed < self.SYSTEM_TASK_COOLDOWN_SECONDS:
                    logger.debug(
                        f"System task {task_type.value} on global cooldown "
                        f"({elapsed:.0f}s / {self.SYSTEM_TASK_COOLDOWN_SECONDS}s), "
                        f"skipping for {agent.agentium_id}"
                    )
                    return

            # Second check: is there an active task in DB?
            existing_system_task = db.query(Task).filter(
                Task.is_idle_task == True,
                Task.is_active == True,
                Task.task_type == task_type,
                Task.status.in_([TaskStatus.IN_PROGRESS, TaskStatus.PENDING])
            ).first()
            
            if existing_system_task:
                logger.debug(
                    f"System task {task_type.value} already assigned to "
                    f"{existing_system_task.assigned_task_agent_ids}, skipping for {agent.agentium_id}"
                )
                return

            self._recent_system_tasks[task_type.value] = datetime.utcnow()

        # ── Create the idle task in the database ─────────────────────────────────
        try:
            unique_suffix = uuid.uuid4().hex[:12]
            idempotency_key = f"idle_{agent.agentium_id}_{task_type.value}_{unique_suffix}"

            # Generate unique agentium_id for task using UUID
            task_agentium_id = f"T{uuid.uuid4().hex[:8].upper()}"

            idle_task = Task(
                agentium_id=task_agentium_id,
                title=f"[Idle] {task_type.value}",
                description=f"[Idle] {task_type.value} by {agent.agentium_id}",
                task_type=task_type,
                status=TaskStatus.IN_PROGRESS,
                priority=TaskPriority.LOW,
                supervisor_id=agent.agentium_id,
                created_by=agent.agentium_id,
                assigned_task_agent_ids=[agent.agentium_id],
                is_idle_task=True,
                idempotency_key=idempotency_key,
                is_active=True,
            )
            db.add(idle_task)
            db.flush()

            # Update in-memory tracking and agent state
            self.current_idle_tasks[agent.agentium_id] = str(idle_task.id)
            agent.status = AgentStatus.IDLE_WORKING
            agent.current_task_id = str(idle_task.id)
            agent.last_idle_action_at = datetime.utcnow()

            logger.info(
                f"🌙 Idle work assigned: {agent.agentium_id} → "
                f"{task_type.value} (Task ID: {task_agentium_id})"
            )

        except Exception as e:
            db.rollback()
            logger.warning(f"⚠️ Failed to assign idle work to {agent.agentium_id}: {e}")
            self.current_idle_tasks.pop(agent.agentium_id, None)
            if task_type in SYSTEM_WIDE_TASKS:
                self._recent_system_tasks.pop(task_type.value, None)

    def _get_available_system_tasks(self) -> List[TaskType]:
        """
        Get system-wide tasks that haven't been run recently.
        Returns list of available task types, sorted by oldest first.
        """
        now = datetime.utcnow()
        available = []
        
        SYSTEM_TASKS = [
            TaskType.VECTOR_MAINTENANCE,
            TaskType.STORAGE_DEDUPE,
            TaskType.AUDIT_ARCHIVAL,
            TaskType.AGENT_HEALTH_SCAN,
            TaskType.CACHE_OPTIMIZATION,
        ]
        
        for sys_task in SYSTEM_TASKS:
            last_run = self._recent_system_tasks.get(sys_task.value)
            if not last_run:
                # Never run - highest priority
                available.append((sys_task, datetime.min))
            else:
                elapsed = (now - last_run).total_seconds()
                if elapsed >= self.SYSTEM_TASK_COOLDOWN_SECONDS:
                    available.append((sys_task, last_run))
        
        # Sort by last run time (oldest first) so we rotate through all tasks
        available.sort(key=lambda x: x[1])
        return [task for task, _ in available]

    async def _execute_idle_work(self, db: Session, agents: List[Agent]):
        """
        Execute assigned idle work for each agent with an active idle task.
        Dispatches to the appropriate handler based on task type.
        
        FIX 5: System-wide tasks execute once and mark completion globally.
        """
        from backend.services.idle_tasks.preference_optimizer import preference_optimizer_task
        
        # Track which system tasks were completed this cycle to avoid duplicates
        system_tasks_completed_this_cycle: set = set()
        
        for agent in agents:
            task_id = self.current_idle_tasks.get(agent.agentium_id)
            if not task_id:
                continue
            
            task = db.query(Task).filter_by(id=task_id, is_active=True).first()
            if not task or task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.PENDING):
                self.current_idle_tasks.pop(agent.agentium_id, None)
                continue
            
            # Skip if this system task was already completed by another agent this cycle
            if task.task_type in [
                TaskType.VECTOR_MAINTENANCE,
                TaskType.STORAGE_DEDUPE,
                TaskType.AUDIT_ARCHIVAL,
                TaskType.AGENT_HEALTH_SCAN,
                TaskType.CACHE_OPTIMIZATION,
            ]:
                if task.task_type.value in system_tasks_completed_this_cycle:
                    logger.debug(
                        f"System task {task.task_type.value} already completed this cycle, "
                        f"skipping for {agent.agentium_id}"
                    )
                    # Mark as completed without executing
                    task.status = TaskStatus.IDLE_COMPLETED
                    task.completed_at = datetime.utcnow()
                    task.is_active = False
                    self.current_idle_tasks.pop(agent.agentium_id, None)
                    agent.status = AgentStatus.ACTIVE
                    agent.current_task_id = None
                    self._agent_last_completed[agent.agentium_id] = datetime.utcnow()
                    continue
            
            try:
                tokens_saved = 0
                
                if task.task_type == TaskType.PREFERENCE_OPTIMIZATION:
                    result = preference_optimizer_task.execute()
                    tokens_saved = result.get('tokens_saved', 0) if isinstance(result, dict) else 0
                    self._last_pref_opt_run[agent.agentium_id] = datetime.utcnow()
                    
                elif task.task_type == TaskType.VECTOR_MAINTENANCE:
                    await self.run_maintenance(db)
                    system_tasks_completed_this_cycle.add(task.task_type.value)
                    
                elif task.task_type == TaskType.AUDIT_ARCHIVAL:
                    from backend.models.entities.audit import AuditLog
                    cutoff = datetime.utcnow() - timedelta(days=90)
                    archived = db.query(AuditLog).filter(
                        AuditLog.created_at < cutoff
                    ).count()
                    logger.info(f"📦 Audit archival scan: {archived} records eligible")
                    system_tasks_completed_this_cycle.add(task.task_type.value)
                    
                elif task.task_type == TaskType.AGENT_HEALTH_SCAN:
                    all_agents = db.query(Agent).filter_by(is_active=True).all()
                    unhealthy = [a for a in all_agents if a.status == AgentStatus.SUSPENDED]
                    if unhealthy:
                        logger.info(f"🏥 Health scan: {len(unhealthy)} suspended agents found")
                    else:
                        logger.info(f"🏥 Health scan: all agents healthy")
                    system_tasks_completed_this_cycle.add(task.task_type.value)
                    
                elif task.task_type == TaskType.CACHE_OPTIMIZATION:
                    logger.info(f"🗄️ Cache optimization cycle by {agent.agentium_id}")
                    system_tasks_completed_this_cycle.add(task.task_type.value)
                    
                elif task.task_type == TaskType.STORAGE_DEDUPE:
                    logger.info(f"🔍 Storage dedup scan by {agent.agentium_id}")
                    system_tasks_completed_this_cycle.add(task.task_type.value)
                        
                elif task.task_type in (TaskType.CONSTITUTION_REFINE, TaskType.CONSTITUTION_READ):
                    agent.read_and_align_constitution(db)
                    
                elif task.task_type == TaskType.ETHOS_OPTIMIZATION:  # FIXED: was ETHOS_OPTIMIMIZATION
                    agent.compress_ethos(db)
                    
                elif task.task_type == TaskType.PREDICTIVE_PLANNING:
                    logger.info(f"🔮 Predictive planning cycle by {agent.agentium_id}")
                
                # Mark idle task as completed
                task.status = TaskStatus.IDLE_COMPLETED
                task.completed_at = datetime.utcnow()
                task.is_active = False
                
                # Clean up tracking
                self.current_idle_tasks.pop(agent.agentium_id, None)
                agent.status = AgentStatus.ACTIVE
                agent.current_task_id = None
                
                # Record completion time — cooldown clock starts now
                self._agent_last_completed[agent.agentium_id] = datetime.utcnow()

                # Update system task tracking
                if task.task_type in [
                    TaskType.VECTOR_MAINTENANCE,
                    TaskType.STORAGE_DEDUPE,
                    TaskType.AUDIT_ARCHIVAL,
                    TaskType.AGENT_HEALTH_SCAN,
                    TaskType.CACHE_OPTIMIZATION,
                ]:
                    self._recent_system_tasks[task.task_type.value] = datetime.utcnow()

                # Record metrics
                self.metrics.record_idle_task_completion(tokens_saved)
                
                logger.info(f"✅ Idle work completed: {agent.agentium_id} → {task.task_type.value}")
                
            except Exception as e:
                logger.warning(f"⚠️ Idle work error for {agent.agentium_id}: {e}")
                self.current_idle_tasks.pop(agent.agentium_id, None)
                agent.status = AgentStatus.ACTIVE
                agent.current_task_id = None
                self._agent_last_completed[agent.agentium_id] = datetime.utcnow()
        
        # Commit all changes
        try:
            db.commit()
        except Exception as e:
            logger.error(f"❌ Failed to commit idle work results: {e}")
            db.rollback()
    
    async def _pause_idle_work(self, db: Session, reason: str):
        """Pause all idle work when user tasks arrive."""
        for task_id in self.current_idle_tasks.values():
            task = db.query(Task).filter_by(id=task_id).first()
            if task:
                task.pause_for_user_task()
        
        logger.info(f"⏸️ Idle work paused: {reason}")
    
    async def _broadcast(self, message: Dict):
        """Broadcast status via WebSocket."""
        try:
            from backend.main import manager
            await manager.broadcast(message)
        except:
            pass
    
    # ═══════════════════════════════════════════════════════════
    # AUTO-SCALING GOVERNANCE
    # ═══════════════════════════════════════════════════════════
    
    async def auto_scale_check(self, db: Session) -> Dict[str, Any]:
        """
        Monitor queue depth and trigger auto-scaling if needed.
        If pending tasks exceed threshold, request Council micro-vote to spawn additional agents.
        """
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
        
        result = {
            "pending_count": pending_count,
            "threshold": threshold,
            "scaled": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if pending_count > threshold:
            logger.info(f"📈 Auto-scaling triggered: {pending_count} pending tasks exceeds threshold {threshold}")
            
            # Get Head for authority
            head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            
            if head:
                from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
                
                audit = AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="agent",
                    actor_id="IDLE_GOVERNANCE",
                    action="auto_scale_triggered",
                    description=f"Auto-scaling triggered: {pending_count} pending tasks",
                    after_state={
                        "pending_count": pending_count,
                        "threshold": threshold,
                        "recommended_agents": 3,
                        "triggered_by": "queue_depth"
                    }
                )
                db.add(audit)
                
                logger.info(f"   Council micro-vote recommended: Spawn 3 additional Task Agents (3xxxx)")
                
                result.update({
                    "scaled": True,
                    "council_vote_required": True,
                    "recommended_agents": 3,
                    "action": "micro_vote_requested"
                })
        
        return result

    # ═══════════════════════════════════════════════════════════
    # METRICS & STATISTICS
    # ═══════════════════════════════════════════════════════════
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive idle governance statistics with metrics."""
        with get_db_context() as db:
            # Get agent stats
            agents = persistent_council.get_persistent_agents(db)
            agent_stats = {
                aid: {
                    'idle_tasks': agent.idle_task_count if hasattr(agent, 'idle_task_count') else 0,
                    'tokens_saved': agent.idle_tokens_saved if hasattr(agent, 'idle_tokens_saved') else 0,
                    'last_action': agent.last_idle_action_at.isoformat() if agent.last_idle_action_at else None
                }
                for aid, agent in agents.items()
            }
            
            # Get task stats
            completed_idle = db.query(Task).filter_by(
                is_idle_task=True,
                status=TaskStatus.IDLE_COMPLETED
            ).count()
            
            # Get capacity info
            capacity = reincarnation_service.get_available_capacity(db)

            # Build cooldown status per agent for observability
            now = datetime.utcnow()
            cooldown_status = {}
            for agent_id, last_done in self._agent_last_completed.items():
                elapsed = (now - last_done).total_seconds()
                remaining = max(0, self.IDLE_TASK_COOLDOWN_SECONDS - elapsed)
                cooldown_status[agent_id] = {
                    "on_cooldown": remaining > 0,
                    "seconds_remaining": round(remaining, 1)
                }
            
            return {
                'is_running': self.is_running,
                'session_duration_hours': ((datetime.utcnow() - self.idle_session_start).total_seconds() / 3600) if self.idle_session_start else 0,
                'completed_idle_tasks': completed_idle,
                'current_idle_tasks': self.current_idle_tasks,
                'agent_statistics': agent_stats,
                'token_budget_status': idle_budget.get_status(),
                'token_optimizer_status': token_optimizer.get_status(),
                'metrics': self.metrics.to_dict(),
                'capacity_status': capacity,
                # Cooldown visibility for debugging
                'agent_cooldown_status': cooldown_status,
                'scheduled_tasks': {
                    'idle_detection': {
                        'interval_hours': self.IDLE_DETECTION_INTERVAL / 3600,
                        'last_run': self.last_idle_detection.isoformat() if self.last_idle_detection else None,
                        'next_run': (self.last_idle_detection + timedelta(seconds=self.IDLE_DETECTION_INTERVAL)).isoformat() if self.last_idle_detection else None
                    },
                    'auto_liquidation': {
                        'interval_hours': self.AUTO_LIQUIDATE_INTERVAL / 3600,
                        'last_run': self.last_auto_liquidate.isoformat() if self.last_auto_liquidate else None,
                        'next_run': (self.last_auto_liquidate + timedelta(seconds=self.AUTO_LIQUIDATE_INTERVAL)).isoformat() if self.last_auto_liquidate else None
                    },
                    'resource_rebalancing': {
                        'interval_hours': self.REBALANCING_INTERVAL / 3600,
                        'last_run': self.last_rebalancing.isoformat() if self.last_rebalancing else None,
                        'next_run': (self.last_rebalancing + timedelta(seconds=self.REBALANCING_INTERVAL)).isoformat() if self.last_rebalancing else None
                    }
                }
            }

    async def run_maintenance(self, db: Session) -> Dict[str, Any]:
        """
        Run vector store maintenance tasks for idle governance.
        """
        logger.info("🔧 Running vector store maintenance (VECTOR_MAINTENANCE idle task)")
        
        results = {
            "maintenance_tasks": [],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            from backend.core.vector_store import get_vector_store
            vector_store = get_vector_store()
            
            # List all collections — must match keys in VectorStore.COLLECTIONS
            collections = ["constitution", "ethos", "task_patterns", "sovereign_prefs"]
            
            for collection_name in collections:
                try:
                    collection = vector_store.get_collection(collection_name)
                    count = collection.count()
                    results["maintenance_tasks"].append(f"{collection_name}: {count} entries")
                    logger.info(f"   📊 {collection_name}: {count} entries")
                except Exception as e:
                    logger.warning(f"Could not check {collection_name}: {e}")
            
            logger.info(f"✅ Vector store maintenance complete: checked {len(collections)} collections")
            
        except Exception as e:
            logger.error(f"❌ Error during vector store maintenance: {e}")
            results["error"] = str(e)
        
        return results

# Singleton instance
idle_governance = EnhancedIdleGovernanceEngine()