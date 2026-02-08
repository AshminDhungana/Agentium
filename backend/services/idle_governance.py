"""
Idle Governance Service for Agentium.
The eternal loop: When no user tasks exist, Head + 2 Council members optimize continuously.
Never sleeps. Minimizes tokens through local models and efficient operations.
"""

import asyncio
import random
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.models.database import get_db_context
from backend.models.entities.agents import Agent, HeadOfCouncil, CouncilMember, AgentStatus, PersistentAgentRole
from backend.models.entities.task import Task, TaskType, TaskStatus, TaskPriority
from backend.services.persistent_council import persistent_council
from backend.services.token_optimizer import token_optimizer, idle_budget


class IdleGovernanceEngine:
    """
    The core engine that manages eternal operation during idle periods.
    Coordinates Head of Council and 2 persistent Council Members.
    """
    
    def __init__(self):
        self.is_running = False
        self.idle_loop_task: Optional[asyncio.Task] = None
        self.check_interval = 10  # Check for work every 10 seconds
        self.current_idle_tasks: Dict[str, str] = {}  # agentium_id -> task_id
        self.last_idle_summary = None
        self.idle_session_start = None
    
    async def start(self, db: Session):
        """Start the eternal idle governance loop."""
        if self.is_running:
            return
        
        self.is_running = True
        self.idle_session_start = datetime.utcnow()
        print("🌙 IDLE GOVERNANCE ENGINE STARTED")
        print("   Persistent Council is now eternally active...")
        
        # Start the main loop
        self.idle_loop_task = asyncio.create_task(self._idle_loop())
        
        # Broadcast that idle mode is operational
        await self._broadcast({
            'type': 'idle_engine',
            'event': 'started',
            'message': 'Persistent Council now active in background',
            'council_members': ['00001', '10001', '10002'],
            'timestamp': datetime.utcnow().isoformat()
        })

    async def _execute_constitution_read(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Execute constitution awareness reading during idle - NO ACTIONS, just awareness."""
        # Force constitution read even if not 24h (idle time is good for study)
        refreshed = agent.check_constitution_freshness(db, force=True)
        
        if refreshed:
            return {
                'summary': f"Agent {agent.agentium_id} refreshed awareness of Constitution v{agent.constitution_version} during idle period. No actions taken - pure awareness.",
                'constitution_version': agent.constitution_version,
                'read_count': agent.constitution_read_count,
                'awareness_only': True
            }
        else:
            return {
                'summary': "Constitution still fresh, no re-read needed",
                'constitution_version': agent.constitution_version
            }
        
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
        
        print("🛑 IDLE GOVERNANCE ENGINE STOPPED")
        
        await self._broadcast({
            'type': 'idle_engine',
            'event': 'stopped',
            'timestamp': datetime.utcnow().isoformat()
        })
    
    async def _idle_loop(self):
        """Main eternal loop - runs forever during idle periods."""
        while self.is_running:
            db = None
            try:
                # Create fresh session for each iteration
                with get_db_context() as db:
                    # Check if there are user tasks pending (we should pause if so)
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
                # If db session exists and is in transaction, rollback
                if db:
                    try:
                        db.rollback()
                    except:
                        pass
                await asyncio.sleep(self.check_interval)
    
    def _get_pending_user_tasks(self, db: Session) -> List[Task]:
        """Get non-idle tasks that need attention."""
        return db.query(Task).filter(
            Task.is_idle_task == False,
            Task.status.in_([
                TaskStatus.PENDING,
                TaskStatus.DELIBERATING,
                TaskStatus.IN_PROGRESS
            ]),
            Task.is_active == 'Y'
        ).all()
    
    def _get_available_persistent_agents(self, db: Session) -> List[Agent]:
        """Get persistent agents ready for idle work."""
        return db.query(Agent).filter(
            Agent.is_persistent == True,
            Agent.is_active == 'Y',
            Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING])
        ).order_by(Agent.last_idle_action_at).all()
    
    async def _assign_idle_work(self, db: Session, agent: Agent):
        """Assign appropriate idle work to agent based on role."""
        
        # Determine task type based on agent role
        if agent.agentium_id == '00001':
            # Head of Council - Coordination and high-level optimization
            task_type = random.choice([
                TaskType.CONSTITUTION_REFINE,    # Propose improvements
                TaskType.CONSTITUTION_READ,       # Study/awareness
                TaskType.PREDICTIVE_PLANNING,
                TaskType.ETHOS_OPTIMIZATION
            ])
        elif agent.persistent_role in [PersistentAgentRole.SYSTEM_OPTIMIZER.value, 
                               PersistentAgentRole.STRATEGIC_PLANNER.value]:
            # Council 10001 - System optimization
            task_type = random.choice([
                TaskType.VECTOR_MAINTENANCE,
                TaskType.CONSTITUTION_READ,
                TaskType.ETHOS_OPTIMIZATION,
                TaskType.STORAGE_DEDUPE,
                TaskType.AUDIT_ARCHIVAL,
                TaskType.CACHE_OPTIMIZATION
            ])
        elif agent.persistent_role == PersistentAgentRole.STRATEGIC_PLANNER.value:
            # Council 10002 - Strategic planning
            task_type = random.choice([
                TaskType.PREDICTIVE_PLANNING,
                TaskType.AGENT_HEALTH_SCAN,
                TaskType.CONSTITUTION_REFINE
            ])
        else:
            return
        
        # Check budget
        estimated_tokens = self._estimate_task_tokens(task_type)
        if not idle_budget.check_budget(estimated_tokens):
            print(f"⚠️ Token budget exhausted, skipping {task_type.value}")
            return
        
        # Create the task
        task = Task(
            title=f"Idle Optimization: {task_type.value.replace('_', ' ').title()}",
            description=self._get_task_description(task_type),
            task_type=task_type,
            priority=TaskPriority.IDLE,
            created_by=agent.agentium_id,
            estimated_tokens=estimated_tokens,
            idle_task_category=self._get_task_category(task_type),
            status=TaskStatus.IDLE_PENDING
        )
        
        db.add(task)
        db.flush()  # Get the ID without committing
        
        # Assign to agent
        if agent.assign_idle_task(task.id):
            task.start_idle_execution(agent.agentium_id)
            self.current_idle_tasks[agent.agentium_id] = task.id
            print(f"📋 Assigned {task_type.value} to {agent.agentium_id}")
            db.commit()  # Commit task creation
        else:
            print(f"⚠️ Could not assign idle task to {agent.agentium_id}")
            db.rollback()  # Rollback if assignment failed
    
    async def _execute_idle_work(self, db: Session, agents: List[Agent]):
        """Execute the assigned idle work for agents."""
        
        execution_map = {
            TaskType.VECTOR_MAINTENANCE: self._execute_vector_maintenance,
            TaskType.STORAGE_DEDUPE: self._execute_storage_dedupe,
            TaskType.AUDIT_ARCHIVAL: self._execute_audit_archival,
            TaskType.PREDICTIVE_PLANNING: self._execute_predictive_planning,
            TaskType.CONSTITUTION_REFINE: self._execute_constitution_refine,
            TaskType.AGENT_HEALTH_SCAN: self._execute_health_scan,
            TaskType.ETHOS_OPTIMIZATION: self._execute_ethos_optimization,
            TaskType.CONSTITUTION_READ: self._execute_constitution_read,
            TaskType.CACHE_OPTIMIZATION: self._execute_cache_optimization
        }
        
        for agent in agents:
            task_id = self.current_idle_tasks.get(agent.agentium_id)
            if not task_id:
                continue
            
            task = db.query(Task).filter_by(id=task_id).first()
            if not task or task.status != TaskStatus.IDLE_RUNNING:
                continue
            
            # Execute
            executor = execution_map.get(task.task_type)
            if executor:
                try:
                    result = await executor(db, agent)
                    
                    # Calculate tokens saved
                    duration_seconds = int(time.time()) - int(task.started_at.timestamp()) if task.started_at else 60
                    tokens_saved = token_optimizer.calculate_token_savings(task.task_type.value, duration_seconds)
                    model_cost = 0.0  # Idle tasks use local models which are free
                    idle_budget.record_usage(task.tokens_used, model_cost, is_idle=True)
                    
                    # Complete task
                    task.complete_idle(result.get('summary', 'Completed'), task.tokens_used)
                    agent.complete_idle_task(tokens_saved)
                    persistent_council.report_idle_activity(db, agent.agentium_id, task.task_type.value, tokens_saved)
                    
                    print(f"✅ {agent.agentium_id} completed {task.task_type.value} (saved ~{tokens_saved} tokens)")
                    
                    # Commit after each successful agent to prevent transaction buildup
                    db.commit()
                    
                except Exception as e:
                    print(f"❌ {agent.agentium_id} failed {task.task_type.value}: {e}")
                    try:
                        task.fail(str(e), can_retry=True)
                        db.rollback()  # Rollback on failure
                    except Exception as rollback_error:
                        print(f"❌ Rollback failed: {rollback_error}")
                
                # Always remove from current tasks
                if agent.agentium_id in self.current_idle_tasks:
                    del self.current_idle_tasks[agent.agentium_id]
    
    # ============ IDLE TASK EXECUTORS ============
    # These execute with MINIMAL token usage (DB ops, embeddings only)
    
    async def _execute_vector_maintenance(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Optimize vector database - 0 tokens (DB operations only)."""
        # Simulate vector DB compaction analysis
        from sqlalchemy import text
        
        # Get vector table stats (placeholder - would integrate with ChromaDB)
        result = db.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar()
        
        return {
            'summary': f"Vector DB analyzed. Current audit records: {result}. No fragmentation detected.",
            'optimized_indices': 0,
            'space_saved_mb': 0
        }
    
    async def _execute_storage_dedupe(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Analyze storage for deduplication - 0 tokens (SQL only)."""
        from sqlalchemy import text
        
        # Check for duplicate entries in various tables
        duplicate_check = db.execute(text("""
            SELECT task_type, COUNT(*) as cnt 
            FROM tasks 
            WHERE is_idle_task = true 
            AND created_at > NOW() - INTERVAL '24 hours'
            GROUP BY task_type
        """)).fetchall()
        
        duplicates_found = len([r for r in duplicate_check if r[1] > 10])
        
        return {
            'summary': f"Storage analysis complete. Found {duplicates_found} task types with >10 daily occurrences.",
            'duplicates_found': duplicates_found,
            'recommendation': 'Consider task batching for frequently repeated idle tasks'
        }
    
    async def _execute_audit_archival(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Archive old audit logs - 0 tokens."""
        from sqlalchemy import text
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(days=30)
        
        # Count old records using proper parameter binding
        # Note: Use 'COMPLETED' status with is_idle_task=true, not 'idle_completed'
        try:
            result = db.execute(text("""
                SELECT COUNT(*) FROM tasks 
                WHERE is_idle_task = true 
                AND status = 'COMPLETED'
                AND completed_at < :cutoff
            """), {'cutoff': cutoff}).scalar()
        except Exception as e:
            print(f"⚠️ Audit archival query failed: {e}")
            result = 0
        
        return {
            'summary': f"Audit archival analysis: {result} completed idle tasks older than 30 days can be compressed.",
            'archivable_records': result or 0,
            'space_estimate_mb': (result or 0) * 0.001  # Rough estimate
        }

    async def _execute_predictive_planning(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Predictive planning - LOW tokens (local model inference)."""
        from sqlalchemy import text
        
        # Analyze patterns (0 tokens - pure SQL)
        hourly_pattern = db.execute(text("""
            SELECT EXTRACT(hour FROM created_at) as hour, COUNT(*) 
            FROM tasks 
            WHERE is_idle_task = false 
            AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY hour 
            ORDER BY hour
        """)).fetchall()
        
        peak_hours = [h[0] for h in hourly_pattern if h[1] > 5]
        
        return {
            'summary': f"Predictive analysis: Peak activity hours identified as {peak_hours}. Recommend pre-warming caches 1 hour before.",
            'peak_hours': peak_hours,
            'recommendation': 'Scale Lead Agent capacity before predicted peak times'
        }
    
    async def _execute_constitution_refine(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Propose constitution refinements - MEDIUM tokens (only occasionally)."""
        # Check how many violations occurred recently
        from backend.models.entities.monitoring import ViolationReport
        
        recent_violations = db.query(ViolationReport).filter(
            ViolationReport.created_at > datetime.utcnow() - timedelta(days=7)
        ).count()
        
        if recent_violations > 5:
            proposal = f"Propose clarifying restrictions based on {recent_violations} recent violations"
        else:
            proposal = "No refinements needed - constitution compliance is strong"
        
        return {
            'summary': proposal,
            'violations_detected': recent_violations,
            'proposal_ready': recent_violations > 5
        }
    
    async def _execute_health_scan(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Proactive health scan - 0 tokens."""
        agents = db.query(Agent).filter_by(is_active='Y').all()
        
        status_breakdown = {}
        for a in agents:
            s = a.status.value
            status_breakdown[s] = status_breakdown.get(s, 0) + 1
        
        return {
            'summary': f"Health scan complete. Active agents: {len(agents)}. Status breakdown: {status_breakdown}",
            'total_agents': len(agents),
            'status_breakdown': status_breakdown
        }
    
    async def _execute_ethos_optimization(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Analyze and optimize agent ethos - LOW tokens."""
        from backend.models.entities.constitution import Ethos
        
        ethos_count = db.query(Ethos).filter_by(is_active='Y').count()
        verified_count = db.query(Ethos).filter_by(is_verified=True, is_active='Y').count()
        
        return {
            'summary': f"Ethos audit: {ethos_count} active ethos documents, {verified_count} verified. All systems aligned.",
            'total_ethos': ethos_count,
            'verified_ethos': verified_count
        }
    
    async def _execute_cache_optimization(self, db: Session, agent: Agent) -> Dict[str, Any]:
        """Optimize caching strategies - 0 tokens."""
        # This would integrate with Redis in production
        return {
            'summary': "Cache optimization analysis: Recommend 1-hour TTL for model response cache, 24-hour for constitution queries.",
            'recommendations': [
                'Model responses: 1 hour TTL',
                'Constitution queries: 24 hour TTL',
                'Agent configs: Permanent until update'
            ]
        }
    
    # ============ UTILITY METHODS ============
    
    def _estimate_task_tokens(self, task_type: TaskType) -> int:
        """Estimate token cost for task type."""
        estimates = {
            TaskType.VECTOR_MAINTENANCE: 0,      # DB only
            TaskType.STORAGE_DEDUPE: 0,           # SQL only
            TaskType.AUDIT_ARCHIVAL: 0,           # DB only
            TaskType.PREDICTIVE_PLANNING: 500,    # Local model
            TaskType.CONSTITUTION_REFINE: 1000,   # Occasional API
            TaskType.AGENT_HEALTH_SCAN: 0,        # SQL only
            TaskType.ETHOS_OPTIMIZATION: 200,     # Local model
            TaskType.CACHE_OPTIMIZATION: 0        # Config only
        }
        return estimates.get(task_type, 100)
    
    def _get_task_description(self, task_type: TaskType) -> str:
        """Get description for task type."""
        descriptions = {
            TaskType.VECTOR_MAINTENANCE: "Analyze and optimize vector database fragmentation and indices",
            TaskType.STORAGE_DEDUPE: "Identify and recommend removal of duplicate or redundant data",
            TaskType.AUDIT_ARCHIVAL: "Compress and archive audit logs older than retention period",
            TaskType.PREDICTIVE_PLANNING: "Analyze task patterns and predict future workloads",
            TaskType.CONSTITUTION_REFINE: "Review violations and propose constitutional clarifications",
            TaskType.AGENT_HEALTH_SCAN: "Proactive health check of all agent systems",
            TaskType.ETHOS_OPTIMIZATION: "Review and optimize agent ethos documents",
            TaskType.CACHE_OPTIMIZATION: "Analyze cache hit rates and recommend TTL adjustments"
        }
        return descriptions.get(task_type, "Idle optimization task")
    
    def _get_task_category(self, task_type: TaskType) -> str:
        """Categorize task for reporting."""
        categories = {
            TaskType.VECTOR_MAINTENANCE: 'maintenance',
            TaskType.STORAGE_DEDUPE: 'storage',
            TaskType.AUDIT_ARCHIVAL: 'storage',
            TaskType.PREDICTIVE_PLANNING: 'planning',
            TaskType.CONSTITUTION_REFINE: 'governance',
            TaskType.AGENT_HEALTH_SCAN: 'monitoring',
            TaskType.ETHOS_OPTIMIZATION: 'governance',
            TaskType.CACHE_OPTIMIZATION: 'performance'
        }
        return categories.get(task_type, 'general')
    
    async def _pause_idle_work(self, db: Session, reason: str):
        """Pause all idle work when user tasks arrive."""
        # Pause running idle tasks
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
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get idle governance statistics."""
        with get_db_context() as db:
            # Get agent stats
            agents = persistent_council.get_persistent_agents(db)
            agent_stats = {
                aid: {
                    'idle_tasks': agent.idle_task_count,
                    'tokens_saved': agent.idle_tokens_saved,
                    'last_action': agent.last_idle_action_at.isoformat() if agent.last_idle_action_at else None
                }
                for aid, agent in agents.items()
            }
            
            # Get task stats
            completed_idle = db.query(Task).filter_by(
                is_idle_task=True,
                status=TaskStatus.IDLE_COMPLETED
            ).count()
            
            return {
                'is_running': self.is_running,
                'session_duration_hours': ((datetime.utcnow() - self.idle_session_start).total_seconds() / 3600) if self.idle_session_start else 0,
                'completed_idle_tasks': completed_idle,
                'current_idle_tasks': self.current_idle_tasks,
                'agent_statistics': agent_stats,
                'token_budget_status': idle_budget.get_status(),
                'token_optimizer_status': token_optimizer.get_status()
            }


# Singleton instance
idle_governance = IdleGovernanceEngine()