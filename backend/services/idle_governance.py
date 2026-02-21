"""
Enhanced Idle Governance Service with Metrics Tracking.
Adds scheduled auto-liquidation, resource rebalancing, and comprehensive metrics.
"""

import asyncio
import random
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

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
    
    async def start(self, db: Session):
        """Start the eternal idle governance loop with scheduled tasks."""
        if self.is_running:
            return
        
        self.is_running = True
        self.idle_session_start = datetime.utcnow()
        self.metrics.session_start = self.idle_session_start
        
        print("🌙 ENHANCED IDLE GOVERNANCE ENGINE STARTED")
        print("   Persistent Council is now eternally active...")
        print("   Scheduled tasks enabled:")
        print(f"     - Idle detection: every {self.IDLE_DETECTION_INTERVAL / 3600} hours")
        print(f"     - Auto-liquidation: every {self.AUTO_LIQUIDATE_INTERVAL / 3600} hours")
        print(f"     - Resource rebalancing: every {self.REBALANCING_INTERVAL / 3600} hours")
        
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
        
        print("🛑 ENHANCED IDLE GOVERNANCE ENGINE STOPPED")
        print(f"   Session duration: {(datetime.utcnow() - self.idle_session_start).total_seconds() / 3600:.2f} hours")
        print(f"   Metrics summary: {self.metrics.to_dict()}")
        
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
                print(f"❌ Error in idle loop: {e}")
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
                Agent.status == 'active',  # lowercase string
                Agent.is_persistent == False,  # Don't auto-terminate persistent agents
                Agent.last_idle_action_at < threshold
            )
        ).all()
        
        idle_ids = [agent.agentium_id for agent in idle_agents]
        
        if idle_ids:
            print(f"🔍 Idle Agent Detection: Found {len(idle_ids)} agents idle for >{self.IDLE_THRESHOLD_DAYS} days")
            print(f"   Idle agents: {', '.join(idle_ids)}")
            
            # Log the detection
            from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
            AuditLog.log(
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
                Agent.status == 'active',  # lowercase string
                Agent.is_persistent == False,
                Agent.last_idle_action_at < threshold
            )
        ).all()
        
        liquidated = []
        skipped = []
        
        # Get Head agent for liquidation authority
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        
        if not head:
            print("⚠️ Auto-liquidation skipped: Head of Council not found")
            return {"liquidated": [], "skipped": [], "reason": "no_head"}
        
        for agent in idle_agents:
            # Check if agent has any active tasks
            active_tasks = db.query(Task).filter(
                Task.assigned_task_agent_ids.contains([agent.agentium_id]),
                Task.status.in_(['pending', 'in_progress', 'deliberating']),  # lowercase strings
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
                print(f"⚠️ Failed to liquidate {agent.agentium_id}: {e}")
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
            print(f"🔻 Auto-Liquidation Complete: {len(liquidated)} agents terminated")
            print(f"   Terminated: {', '.join(liquidated)}")
        
        if skipped:
            print(f"   Skipped: {len(skipped)} agents (have active tasks or errors)")
        
        return summary
    
    async def resource_rebalancing(self, db: Session) -> Dict[str, Any]:
        """
        Redistribute work from overloaded agents to underutilized ones.
        Returns rebalancing summary.
        """
        # Get all active agents (excluding persistent ones)
        agents = db.query(Agent).filter(
            Agent.is_active == True,
            Agent.status == 'active',  # lowercase string
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
                Task.status.in_(['pending', 'in_progress', 'deliberating']),  # lowercase strings
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
                Task.status.in_(['pending', 'deliberating']),  # lowercase strings - only pending/deliberating
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
            print(f"⚖️ Resource Rebalancing Complete: {tasks_moved} tasks redistributed")
            print(f"   Improvement: {improvement:.1f}%")
        
        return summary
    
    # ═══════════════════════════════════════════════════════════
    # EXISTING IDLE WORK METHODS (from original implementation)
    # ═══════════════════════════════════════════════════════════
    
    def _get_pending_user_tasks(self, db: Session) -> List[Task]:
        """Get non-idle tasks that need attention."""
        return db.query(Task).filter(
            Task.is_idle_task == False,
            Task.status.in_([
                'pending',           # lowercase
                'deliberating',      # lowercase
                'in_progress'        # lowercase
            ]),
            Task.is_active == True
        ).all()
    
    def _get_available_persistent_agents(self, db: Session) -> List[Agent]:
        """Get persistent agents ready for idle work."""
        return db.query(Agent).filter(
            Agent.is_persistent == True,
            Agent.is_active == True,
            Agent.status.in_(['active', 'idle_working'])  # lowercase strings
        ).order_by(Agent.last_idle_action_at).all()
    
    async def _assign_idle_work(self, db: Session, agent: Agent):
        """Assign appropriate idle work to agent based on role."""
        # Skip if this agent already has an active idle task
        if agent.agentium_id in self.current_idle_tasks:
            return
        
        # Determine task type based on agent role
        if agent.agentium_id == '00001':
            task_type = random.choice([
                TaskType.CONSTITUTION_REFINE,
                TaskType.CONSTITUTION_READ,
                TaskType.PREDICTIVE_PLANNING,
                TaskType.ETHOS_OPTIMIZATION
            ])
        else:
            task_type = random.choice([
                TaskType.VECTOR_MAINTENANCE,
                TaskType.STORAGE_DEDUPE,
                TaskType.AUDIT_ARCHIVAL,
                TaskType.AGENT_HEALTH_SCAN,
                TaskType.CACHE_OPTIMIZATION
            ])
        
        # Create idle task (simplified - full implementation in original file)
        # This is a placeholder for the actual task creation logic
        pass
    
    async def _execute_idle_work(self, db: Session, agents: List[Agent]):
        """Execute assigned idle work."""
        # Placeholder - full implementation in original file
        pass
    
    async def _pause_idle_work(self, db: Session, reason: str):
        """Pause all idle work when user tasks arrive."""
        for task_id in self.current_idle_tasks.values():
            task = db.query(Task).filter_by(id=task_id).first()
            if task:
                task.pause_for_user_task()
        
        print(f"⏸️ Idle work paused: {reason}")
    
    async def _broadcast(self, message: Dict):
        """Broadcast status via WebSocket."""
        try:
            from backend.main import manager
            await manager.broadcast(message)
        except:
            pass
    
    # ═══════════════════════════════════════════════════════════
    # AUTO-SCALING GOVERNANCE (NEW - Add to EnhancedIdleGovernanceEngine)
    # ═══════════════════════════════════════════════════════════
    
    async def auto_scale_check(self, db: Session) -> Dict[str, Any]:
        """
        Monitor queue depth and trigger auto-scaling if needed.
        If pending tasks exceed threshold, request Council micro-vote to spawn additional agents.
        """
        # Count pending tasks
        pending_count = db.query(Task).filter(
            Task.status.in_([
                'pending',           # lowercase
                'deliberating',      # lowercase
                'approved',          # lowercase
                'assigned'           # lowercase
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
            print(f"📈 Auto-scaling triggered: {pending_count} pending tasks exceeds threshold {threshold}")
            
            # Get Head for authority
            head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            
            if head:
                # Log scaling decision in audit trail
                from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
                
                AuditLog.log(
                    db=db,
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="agent",
                    actor_id="IDLE_GOVERNANCE",
                    action="auto_scale_triggered",
                    description=f"Auto-scaling triggered: {pending_count} pending tasks",
                    after_state={
                        "pending_count": pending_count,
                        "threshold": threshold,
                        "recommended_agents": 3,  # Spawn 3 new 3xxxx agents
                        "triggered_by": "queue_depth"
                    }
                )
                
                # In production: Request Council micro-vote and spawn agents
                # For now, log the recommendation
                print(f"   Council micro-vote recommended: Spawn 3 additional Task Agents (3xxxx)")
                
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
                status='idle_completed'  # lowercase
            ).count()
            
            # Get capacity info
            capacity = reincarnation_service.get_available_capacity(db)
            
            return {
                'is_running': self.is_running,
                'session_duration_hours': ((datetime.utcnow() - self.idle_session_start).total_seconds() / 3600) if self.idle_session_start else 0,
                'completed_idle_tasks': completed_idle,
                'current_idle_tasks': self.current_idle_tasks,
                'agent_statistics': agent_stats,
                'token_budget_status': idle_budget.get_status(),
                'token_optimizer_status': token_optimizer.get_status(),
                
                # NEW: Enhanced metrics
                'metrics': self.metrics.to_dict(),
                'capacity_status': capacity,
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


# Singleton instance
idle_governance = EnhancedIdleGovernanceEngine()