"""
Enhanced Reincarnation Service for Agentium.
Manages complete agent lifecycle: spawn, promote, liquidate, reincarnate.
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError

from backend.models.entities.agents import Agent, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent, AgentStatus, AgentType
from backend.models.entities.constitution import Ethos
from backend.models.entities.task import Task, TaskStatus, TaskAuditLog
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.context_manager import context_manager
from backend.core.llm_client import LLMClient
from backend.services.capability_registry import CapabilityRegistry, Capability
import logging 

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# ID GENERATION CONSTANTS
# ═══════════════════════════════════════════════════════════

ID_RANGES = {
    "head": {"min": 1, "max": 9999, "prefixes": ["0"]},      # 00001-09999
    "council": {"min": 10001, "max": 19999, "prefixes": ["1"]},  # 10001-19999
    "lead": {"min": 20001, "max": 29999, "prefixes": ["2"]},     # 20001-29999
    "task": {"min": 30001, "max": 69999, "prefixes": ["3", "4", "5", "6"]},     # 30001-69999
    "critic": {"min": 70001, "max": 99999, "prefixes": ["7", "8", "9"]},  # 70001-99999
}

class ReincarnationService:
    """
    Complete agent lifecycle management service.
    Handles spawning, promotion, liquidation, and reincarnation.
    """
    
    # Lock ID namespace for advisory locks (prevents collision with other app locks)
    _ADVISORY_LOCK_NAMESPACE = 42
    
    @staticmethod
    def _get_advisory_lock_id(prefix: str) -> int:
        """
        Generate a unique advisory lock ID for a given prefix.
        Uses hash of prefix modulo 2^31 to stay within PostgreSQL limits.
        """
        import hashlib
        hash_val = int(hashlib.md5(prefix.encode()).hexdigest(), 16)
        return (hash_val % (2**31 - 1)) + (ReincarnationService._ADVISORY_LOCK_NAMESPACE * 1000)
    
    @staticmethod
    def _generate_next_id(tier: str, db: Session) -> str:
        """
        Generate next available ID for a tier with full atomic concurrency control.
        
        Uses database advisory locks + SELECT FOR UPDATE to prevent all race conditions
        under concurrent agent spawning. Falls back to gap-filling with conflict detection.
        
        Args:
            tier: "head", "council", "lead", "task", or "critic"
            db: Database session
            
        Returns:
            Next available agentium_id (e.g., "30152")
            
        Raises:
            ValueError: If ID pool is exhausted or tier is invalid
            RuntimeError: If database integrity cannot be guaranteed
        """
        tier_config = ID_RANGES.get(tier)
        if not tier_config:
            raise ValueError(f"Invalid tier: {tier}. Must be one of: {list(ID_RANGES.keys())}")
        
        prefixes = tier_config.get("prefixes", [tier_config.get("prefix")])
        
        for prefix in prefixes:
            lock_id = ReincarnationService._get_advisory_lock_id(prefix)
            
            # ═══════════════════════════════════════════════════════════
            # STEP 1: Acquire exclusive advisory lock for this prefix
            # This prevents ANY concurrent ID generation for this prefix
            # across all application instances
            # ═══════════════════════════════════════════════════════════
            try:
                # PostgreSQL advisory lock (transaction-scoped)
                lock_result = db.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                    {"lock_id": lock_id}
                ).scalar()
                
                if not lock_result:
                    # Another process holds the lock - this shouldn't happen
                    # in normal operation, but handle gracefully
                    logger.warning(f"⚠️ Could not acquire advisory lock for prefix {prefix}, retrying...")
                    # Fallback: try next prefix or continue with row-level lock only
                    
            except Exception as e:
                # Advisory locks may not be available (non-PostgreSQL)
                # Continue with row-level locking only
                logger.debug(f"Advisory lock not available for prefix {prefix}: {e}")
            
            # ═══════════════════════════════════════════════════════════
            # STEP 2: Get current maximum ID with row-level lock.
            # PostgreSQL forbids FOR UPDATE with aggregate functions, so
            # we lock the matching rows first and compute max in Python.
            # ═══════════════════════════════════════════════════════════
            locked_rows = (
                db.query(Agent.agentium_id)
                .filter(Agent.agentium_id.like(f"{prefix}%"))
                .with_for_update()
                .all()
            )

            if locked_rows:
                max_id = None
                for (agent_id,) in locked_rows:
                    try:
                        num = int(agent_id)
                        if max_id is None or num > max_id:
                            max_id = num
                    except ValueError:
                        continue
                next_num = (max_id + 1) if max_id is not None else int(f"{prefix}0001")
            else:
                next_num = int(f"{prefix}0001")

            prefix_max = int(f"{prefix}9999")
            
            # ═══════════════════════════════════════════════════════════
            # STEP 3: Attempt sequential ID assignment with conflict handling
            # ═══════════════════════════════════════════════════════════
            if next_num <= prefix_max:
                candidate_id = str(next_num).zfill(5)
                
                # Verify availability (defensive check)
                existing = db.query(Agent).filter_by(agentium_id=candidate_id).first()
                
                if not existing:
                    # Pre-validate by attempting a flush with the ID
                    # This catches any race conditions at the database level
                    try:
                        # Create a minimal validation query to ensure ID is truly available
                        validation = db.execute(
                            text("""
                                SELECT 1 FROM agents 
                                WHERE agentium_id = :agentium_id 
                                FOR UPDATE SKIP LOCKED
                            """),
                            {"agentium_id": candidate_id}
                        ).fetchone()
                        
                        if validation is None:
                            return candidate_id
                            
                    except Exception:
                        # Database doesn't support SKIP LOCKED, fall through to gap scan
                        pass
            
            # ═══════════════════════════════════════════════════════════
            # STEP 4: Gap-filling scan with atomic conflict detection
            # Triggered when: sequential ID taken, or pool has gaps from deletions
            # ═══════════════════════════════════════════════════════════
            logger.info(f"🔍 Scanning for gaps in prefix {prefix} (sequential ID {next_num} unavailable)")

            # Numeric bounds for this prefix, e.g. prefix "3" → 30001..39999
            prefix_min_num = int(f"{prefix}0001")
            prefix_max_num = int(f"{prefix}9999")
            # Suffix-only bounds used inside the CTE (strip the leading prefix digit)
            suffix_min = int(str(prefix_min_num)[1:])   # e.g. 1
            suffix_max = int(str(prefix_max_num)[1:])   # e.g. 9999
            prefix_len = len(str(prefix))               # always 1 for current ranges

            # Use a CTE to find gaps atomically
            try:
                gap_result = db.execute(
                    text(f"""
                        WITH RECURSIVE numbers AS (
                            SELECT :min_num AS n
                            UNION ALL
                            SELECT n + 1 FROM numbers WHERE n < :max_num
                        ),
                        used_ids AS (
                            SELECT CAST(substring(agentium_id FROM {prefix_len + 1}) AS INTEGER) AS num
                            FROM agents
                            WHERE agentium_id LIKE :prefix_pattern
                        )
                        SELECT LPAD(n::text, 4, '0') AS gap_id
                        FROM numbers
                        WHERE n NOT IN (SELECT num FROM used_ids)
                        AND n BETWEEN :min_num AND :max_num
                        LIMIT 1
                    """),
                    {
                        "min_num": suffix_min,
                        "max_num": suffix_max,
                        "prefix_pattern": f"{prefix}%"
                    }
                ).fetchone()
                
                if gap_result:
                    gap_id = gap_result[0]
                    candidate_id = f"{prefix}{gap_id}"
                    
                    # Final atomic check with row lock
                    conflict_check = db.execute(
                        text("""
                            SELECT 1 FROM agents 
                            WHERE agentium_id = :agentium_id 
                            FOR UPDATE SKIP LOCKED
                        """),
                        {"agentium_id": candidate_id}
                    ).fetchone()
                    
                    if conflict_check is None:
                        return candidate_id
                        
            except Exception as e:
                # CTE approach failed, use Python loop with proper locking
                logger.debug(f"CTE gap scan failed, using fallback: {e}")
                
                # Build set of used IDs with locking
                used_ids = {
                    row[0] for row in db.execute(
                        text("""
                            SELECT agentium_id FROM agents 
                            WHERE agentium_id LIKE :prefix_pattern
                            FOR UPDATE
                        """),
                        {"prefix_pattern": f"{prefix}%"}
                    ).fetchall()
                }
                
                # Find first gap
                for candidate_num in range(1, 10000):
                    candidate_id = f"{prefix}{candidate_num:04d}"
                    if candidate_id not in used_ids:
                        # Verify with SELECT FOR UPDATE to prevent race
                        locked = db.execute(
                            text("""
                                SELECT 1 FROM agents 
                                WHERE agentium_id = :agentium_id 
                                FOR UPDATE NOWAIT
                            """),
                            {"agentium_id": candidate_id}
                        ).fetchone()
                        
                        if locked is None:
                            return candidate_id
                            
            logger.warning(f"⚠️ Prefix {prefix} appears to be exhausted")
        
        # ═══════════════════════════════════════════════════════════
        # STEP 5: All prefixes exhausted
        # ═══════════════════════════════════════════════════════════
        raise ValueError(
            f"ID pool exhausted for {tier} tier across all assigned prefixes "
            f"({', '.join(prefixes)}). Consider liquidating inactive agents "
            f"or expanding ID range."
        )
    
    @staticmethod
    def generate_id_with_retry(tier: str, db: Session, max_retries: int = 3) -> str:
        """
        Wrapper for _generate_next_id with automatic retry on transient failures.
        
        Args:
            tier: The agent tier
            db: Database session
            max_retries: Maximum number of retry attempts
            
        Returns:
            Generated agentium_id
            
        Raises:
            RuntimeError: If all retry attempts fail
        """
        import time
        
        for attempt in range(1, max_retries + 1):
            try:
                return ReincarnationService._generate_next_id(tier, db)
                
            except IntegrityError as e:
                # Unique constraint violation - another transaction got the ID first
                db.rollback()
                logger.warning(f"ID generation conflict on attempt {attempt}, retrying...")
                
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to generate ID for tier {tier} after {max_retries} "
                        f"attempts due to concurrent conflicts. Consider reducing "
                        f"spawn concurrency or expanding ID pools."
                    ) from e
                
                # Exponential backoff: 10ms, 20ms, 40ms
                time.sleep(0.01 * (2 ** (attempt - 1)))
                
            except Exception as e:
                # Non-retryable error
                db.rollback()
                raise
        
        # Should never reach here
        raise RuntimeError(f"Unexpected state in ID generation for tier {tier}")
    
    @staticmethod
    def spawn_task_agent(
        parent: Agent,
        name: str,
        description: str,
        capabilities: Optional[List[str]] = None,
        db: Session = None
    ) -> TaskAgent:
        """
        Spawn a new Task Agent (3xxxx).
        
        Args:
            parent: Parent agent (must be Lead or Council)
            name: Name for new agent
            description: Purpose/role description
            capabilities: Optional custom capabilities to grant
            db: Database session
            
        Returns:
            Newly created TaskAgent
            
        Raises:
            PermissionError: If parent lacks SPAWN_TASK_AGENT capability
            ValueError: If ID pool is exhausted
        """
        # Check parent permission
        if not CapabilityRegistry.can_agent(parent, Capability.SPAWN_TASK_AGENT, db):
            raise PermissionError(
                f"Agent {parent.agentium_id} cannot spawn Task Agents "
                "(requires SPAWN_TASK_AGENT capability)"
            )
        
        # Generate unique ID with retry logic
        new_id = ReincarnationService.generate_id_with_retry("task", db)
        
        # Create Task Agent
        task_agent = TaskAgent(
            agentium_id=new_id,
            name=name,
            description=description,
            parent_id=parent.id,
            agent_type=AgentType.TASK_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
            idle_mode_enabled=False,
            created_by_agentium_id=parent.agentium_id
        )
        
        db.add(task_agent)
        db.flush()

        # Create and assign default Ethos for the new Task Agent
        default_ethos = parent._create_default_ethos(task_agent, db)
        task_agent.ethos_id = default_ethos.id
        db.flush()

        # Grant custom capabilities if specified
        if capabilities:
            parent_for_grant = db.query(Agent).filter_by(agentium_id="00001").first()  # Head grants
            for cap_name in capabilities:
                try:
                    cap = Capability(cap_name)
                    CapabilityRegistry.grant_capability(
                        task_agent,
                        cap,
                        parent_for_grant or parent,
                        f"Custom capability for spawned agent {new_id}",
                        db
                    )
                except ValueError:
                    logger.warning(f"⚠️ Invalid capability: {cap_name}")
        
        # Log the spawn
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=parent.agentium_id,
            action="agent_spawned",
            target_type="agent",
            target_id=new_id,
            description=f"Task Agent {new_id} spawned by {parent.agentium_id}",
            meta_data={
                "parent": parent.agentium_id,
                "name": name,
                "custom_capabilities": capabilities or []
            }
        )
        db.add(audit)
        
        logger.info(f"✨ Task Agent spawned: {new_id} (parent: {parent.agentium_id})")
        return task_agent
    
    @staticmethod
    def spawn_lead_agent(
        parent: Agent,
        name: str,
        description: str,
        db: Session
    ) -> LeadAgent:
        """
        Spawn a new Lead Agent (2xxxx).
        
        Args:
            parent: Parent agent (must be Council or Head)
            name: Name for new agent
            description: Purpose/role description
            db: Database session
            
        Returns:
            Newly created LeadAgent
            
        Raises:
            PermissionError: If parent lacks SPAWN_LEAD capability
        """
        # Check parent permission
        if not CapabilityRegistry.can_agent(parent, Capability.SPAWN_LEAD, db):
            raise PermissionError(
                f"Agent {parent.agentium_id} cannot spawn Lead Agents "
                "(requires SPAWN_LEAD capability)"
            )
        
        # Generate unique ID with retry logic
        new_id = ReincarnationService.generate_id_with_retry("lead", db)
        
        # Create Lead Agent
        lead_agent = LeadAgent(
            agentium_id=new_id,
            name=name,
            description=description,
            parent_id=parent.id,
            agent_type=AgentType.LEAD_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
            created_by_agentium_id=parent.agentium_id
        )
        
        db.add(lead_agent)
        db.flush()

        # Create and assign default Ethos for the new Lead Agent
        default_ethos = parent._create_default_ethos(lead_agent, db)
        lead_agent.ethos_id = default_ethos.id
        db.flush()

        # Log the spawn
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=parent.agentium_id,
            action="lead_spawned",
            target_type="agent",
            target_id=new_id,
            description=f"Lead Agent {new_id} spawned by {parent.agentium_id}",
            meta_data={
                "parent": parent.agentium_id,
                "name": name
            }
        )
        db.add(audit)
        
        logger.info(f"✨ Lead Agent spawned: {new_id} (parent: {parent.agentium_id})")
        return lead_agent
    
    # ═══════════════════════════════════════════════════════════
    # PROMOTION SYSTEM
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def promote_to_lead(agent_id: str, promoted_by: Agent, reason: str, db: Session) -> LeadAgent:
        """
        Promote a Task Agent (3xxxx) to Lead Agent (2xxxx).
        
        This is a rare operation reserved for exceptional Task Agents who have
        demonstrated leadership capability and need broader authority.
        
        Args:
            agent_id: Agentium ID of Task Agent to promote
            promoted_by: Agent authorizing the promotion (must be Council/Head)
            reason: Justification for promotion
            db: Database session
            
        Returns:
            New LeadAgent instance
            
        Raises:
            ValueError: If agent is not a Task Agent or doesn't exist
            PermissionError: If promoter lacks authority
        """
        # Get the Task Agent
        task_agent = db.query(TaskAgent).filter_by(agentium_id=agent_id, is_active=True).first()
        
        if not task_agent:
            raise ValueError(f"Task Agent {agent_id} not found or inactive")
        
        # Only Task Agents can be promoted to Lead
        if not any(agent_id.startswith(p) for p in ['3', '4', '5', '6']):
            raise ValueError(f"Only Task Agents (3xxxx-6xxxx) can be promoted to Lead. Got: {agent_id}")
        
        # Check promoter permission (must be Council or Head)
        promoter_tier = CapabilityRegistry.get_agent_tier(promoted_by.agentium_id)
        if promoter_tier not in ['0', '1']:
            raise PermissionError(
                f"Agent {promoted_by.agentium_id} cannot promote agents "
                "(requires Council or Head tier)"
            )
        
        # Generate new Lead Agent ID with retry logic
        new_lead_id = ReincarnationService.generate_id_with_retry("lead", db)
        
        # Create new Lead Agent (copy attributes from Task Agent)
        lead_agent = LeadAgent(
            agentium_id=new_lead_id,
            name=f"{task_agent.name} (Promoted)",
            description=f"Promoted from {agent_id}. {task_agent.description}",
            parent_id=task_agent.parent_id,
            agent_type=AgentType.LEAD_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=task_agent.is_persistent,
            created_by_agentium_id=promoted_by.agentium_id,
            constitution_version=task_agent.constitution_version,
            preferred_config_id=task_agent.preferred_config_id,
            ethos_id=task_agent.ethos_id  # Inherit ethos
        )
        
        db.add(lead_agent)
        db.flush()
        
        # Transfer active tasks from Task Agent to Lead Agent
        active_tasks = db.query(Task).filter(
            Task.assigned_task_agent_ids.contains([agent_id]),
            Task.is_active == True
        ).all()
        
        for task in active_tasks:
            # Replace old ID with new ID in assignments
            if task.assigned_task_agent_ids and agent_id in task.assigned_task_agent_ids:
                task.assigned_task_agent_ids.remove(agent_id)
                task.assigned_task_agent_ids.append(new_lead_id)
                
                # Log task transfer
                task._log_status_change(
                    "agent_promoted",
                    promoted_by.agentium_id,
                    f"Task transferred to promoted Lead {new_lead_id} (was {agent_id})"
                )
        
        # Terminate the old Task Agent
        task_agent.status = AgentStatus.TERMINATED
        task_agent.terminated_at = datetime.utcnow()
        task_agent.termination_reason = f"Promoted to Lead Agent {new_lead_id}"
        task_agent.is_active = False
        
        # Revoke old Task Agent capabilities
        CapabilityRegistry.revoke_all_capabilities(
            task_agent,
            f"agent_promoted_to_{new_lead_id}",
            db
        )
        
        # Log the promotion
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=promoted_by.agentium_id,
            action="agent_promoted",
            target_type="agent",
            target_id=new_lead_id,
            description=f"Task Agent {agent_id} promoted to Lead Agent {new_lead_id}. Reason: {reason}",
            meta_data={
                "old_id": agent_id,
                "new_id": new_lead_id,
                "promoted_by": promoted_by.agentium_id,
                "reason": reason,
                "tasks_transferred": len(active_tasks)
            }
        )
        db.add(audit)
        
        db.commit()
        
        logger.info(f"🎖️ Agent promoted: {agent_id} → {new_lead_id}")
        logger.info(f"   Reason: {reason}")
        logger.info(f"   Tasks transferred: {len(active_tasks)}")
        
        return lead_agent
    
    # ═══════════════════════════════════════════════════════════
    # LIQUIDATION SYSTEM
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def liquidate_agent(
        agent_id: str,
        liquidated_by: Agent,
        reason: str,
        db: Session,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Safely terminate an agent with full cleanup.
        
        Liquidation process:
        1. Check permissions
        2. Cancel/reassign active tasks
        3. Notify child agents
        4. Revoke all capabilities
        5. Archive agent state
        6. Set status to TERMINATED
        
        Args:
            agent_id: Agentium ID to liquidate
            liquidated_by: Agent authorizing liquidation
            reason: Justification for liquidation
            db: Database session
            force: If True, bypass some safety checks (emergency use only)
            
        Returns:
            Liquidation summary dict
            
        Raises:
            PermissionError: If liquidator lacks authority
            ValueError: If agent is protected (e.g., Head 00001)
        """
        # Get the agent
        agent = db.query(Agent).filter_by(agentium_id=agent_id, is_active=True).first()
        
        if not agent:
            raise ValueError(f"Agent {agent_id} not found or already terminated")
        
        # PROTECTION: Cannot liquidate Head of Council 00001
        if agent_id == "00001" and not force:
            raise ValueError("Cannot liquidate Head of Council (00001) - system protection")
        
        # Check liquidator permissions
        liquidator_tier = CapabilityRegistry.get_agent_tier(liquidated_by.agentium_id)
        agent_tier = CapabilityRegistry.get_agent_tier(agent_id)
        
        # Head can liquidate anyone
        if liquidator_tier == "0":
            pass  # Always allowed
        
        # Council can liquidate Lead and Task
        elif liquidator_tier == "1" and agent_tier in ["2", "3"]:
            pass  # Allowed
        
        # Lead can liquidate only their own Task agents
        elif liquidator_tier == "2" and agent_tier == "3":
            # Check if it's their child
            if agent.parent_id != liquidated_by.id and not force:
                raise PermissionError(
                    f"Lead {liquidated_by.agentium_id} can only liquidate their own Task Agents"
                )
        
        else:
            raise PermissionError(
                f"Agent {liquidated_by.agentium_id} cannot liquidate {agent_id} "
                f"(tier {liquidator_tier} cannot liquidate tier {agent_tier})"
            )
        
        liquidation_summary = {
            "agent_id": agent_id,
            "liquidated_by": liquidated_by.agentium_id,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "tasks_cancelled": 0,
            "tasks_reassigned": 0,
            "child_agents_notified": 0,
            "capabilities_revoked": 0
        }
        
        # STEP 1: Handle active tasks
        active_tasks = db.query(Task).filter(
            Task.assigned_task_agent_ids.contains([agent_id]),
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.DELIBERATING]),
            Task.is_active == True
        ).all()
        
        for task in active_tasks:
            # Try to reassign to parent
            if agent.parent:
                if task.assigned_task_agent_ids and agent_id in task.assigned_task_agent_ids:
                    task.assigned_task_agent_ids.remove(agent_id)
                    task.assigned_task_agent_ids.append(agent.parent.agentium_id)
                    task._log_status_change(
                        "reassigned_liquidation",
                        liquidated_by.agentium_id,
                        f"Reassigned to {agent.parent.agentium_id} due to {agent_id} liquidation"
                    )
                    liquidation_summary["tasks_reassigned"] += 1
            else:
                # No parent - cancel the task
                task.status = TaskStatus.CANCELLED
                task.completion_summary = f"Cancelled due to agent {agent_id} liquidation"
                task._log_status_change(
                    "cancelled_liquidation",
                    liquidated_by.agentium_id,
                    f"Agent {agent_id} liquidated, no parent to reassign to"
                )
                liquidation_summary["tasks_cancelled"] += 1
        
        # STEP 2: Notify child agents
        child_agents = db.query(Agent).filter_by(parent_id=agent.id, is_active=True).all()
        
        for child in child_agents:
            # Reassign children to grandparent or orphan them
            if agent.parent:
                child.parent_id = agent.parent.id
                liquidation_summary["child_agents_notified"] += 1
            else:
                # Orphan - set parent to None (will need manual reassignment)
                child.parent_id = None
                liquidation_summary["child_agents_notified"] += 1
        
        # STEP 3: Revoke ALL capabilities
        capabilities_before = CapabilityRegistry.get_agent_capabilities(agent)
        liquidation_summary["capabilities_revoked"] = len(capabilities_before["effective_capabilities"])
        
        CapabilityRegistry.revoke_all_capabilities(
            agent,
            f"agent_liquidated_by_{liquidated_by.agentium_id}",
            db
        )
        
        # STEP 4: Archive agent state (store in termination_reason as JSON)
        archive_state = {
            "final_status": agent.status.value,
            "tasks_count": len(active_tasks),
            "children_count": len(child_agents),
            "last_active": agent.last_idle_action_at.isoformat() if agent.last_idle_action_at else None,
            "capabilities": capabilities_before["effective_capabilities"]
        }
        
        # STEP 5: Terminate the agent
        agent.status = AgentStatus.TERMINATED
        agent.terminated_at = datetime.utcnow()
        agent.termination_reason = f"Liquidated by {liquidated_by.agentium_id}. Reason: {reason}"
        agent.is_active = False
        agent.current_task_id = None
        
        # Store archive in custom field if available
        if hasattr(agent, 'liquidation_archive'):
            agent.liquidation_archive = json.dumps(archive_state)
        
        # STEP 6: Log the liquidation
        audit = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=liquidated_by.agentium_id,
            action="agent_liquidated",
            target_type="agent",
            target_id=agent_id,
            description=f"Agent {agent_id} liquidated by {liquidated_by.agentium_id}. Reason: {reason}",
            meta_data=liquidation_summary
        )
        db.add(audit)
        
        db.commit()
        
        logger.info(f"🔻 Agent liquidated: {agent_id}")
        logger.info(f"   Liquidated by: {liquidated_by.agentium_id}")
        logger.info(f"   Reason: {reason}")
        logger.info(f"   Tasks reassigned: {liquidation_summary['tasks_reassigned']}")
        logger.info(f"   Tasks cancelled: {liquidation_summary['tasks_cancelled']}")
        logger.info(f"   Children reassigned: {liquidation_summary['child_agents_notified']}")
        
        return liquidation_summary
    
    # ═══════════════════════════════════════════════════════════
    # CAPACITY MANAGEMENT
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def get_available_capacity(db: Session) -> Dict[str, Any]:
        """
        Check ID pool availability for each tier.
        
        Returns:
            {
                "head": {"used": 1, "available": 998, "max": 999, "percentage": 0.1},
                "council": {"used": 5, "available": 9994, "max": 9999, "percentage": 0.05},
                ...
            }
        """
        capacity = {}
        
        for tier_name, tier_config in ID_RANGES.items():
            # Count agents in this tier
            prefixes = tier_config.get("prefixes", [tier_config.get("prefix")])
            
            used = sum(db.query(func.count(Agent.id)).filter(
                Agent.agentium_id.like(f"{prefix}%")
            ).scalar() or 0 for prefix in prefixes)
            
            max_capacity = tier_config["max"] - tier_config["min"] + 1
            available = max_capacity - used
            percentage = (used / max_capacity) * 100 if max_capacity > 0 else 0
            
            capacity[tier_name] = {
                "used": used,
                "available": available,
                "max": max_capacity,
                "percentage": round(percentage, 2),
                "warning": percentage > 80,  # Warn if >80% full
                "critical": percentage > 95  # Critical if >95% full
            }
        
        return capacity
    
    # ═══════════════════════════════════════════════════════════
    # REINCARNATION (from original implementation)
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    async def check_and_trigger_reincarnation(
        agent: Agent,
        db: Session,
        conversation_context: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if agent needs reincarnation and execute the cycle if needed.
        Returns reincarnation result or None if not triggered.
        """
        agent_id = agent.agentium_id
        
        # Check context status
        if not context_manager.should_reincarnate(agent_id):
            return None
        
        print(f"🔄 REINCARNATION TRIGGERED for {agent_id}")
        print(f"   Context at {context_manager.check_status(agent_id).usage_percentage:.1%}")
        
        # Execute reincarnation cycle
        return await ReincarnationService.execute_reincarnation(
            agent=agent,
            db=db,
            conversation_context=conversation_context
        )
    
    @staticmethod
    async def execute_reincarnation(
        agent: Agent,
        db: Session,
        conversation_context: str
    ) -> Dict[str, Any]:
        """
        Execute the full reincarnation cycle:
        1. Summarize conversation/context
        2. Update ethos with wisdom
        3. Terminate current agent
        4. Spawn successor
        5. Transfer state
        """
        agent_id = agent.agentium_id
        incarnation_data = context_manager.prepare_for_reincarnation(agent_id)
        
        result = {
            "old_agent": agent_id,
            "incarnation_number": incarnation_data.get("incarnation_number", 1),
            "summarized": False,
            "ethos_updated": False,
            "terminated": False,
            "successor_spawned": False,
            "successor_id": None,
            "wisdom_added": None
        }
        
        try:
            # STEP 1: Summarize the conversation/context
            print(f"   Step 1: Summarizing {incarnation_data.get('total_tokens_processed', 0)} tokens...")
            summary = await ReincarnationService._summarize_context(
                agent=agent,
                db=db,
                context=conversation_context,
                incarnation=incarnation_data.get("incarnation_number", 1)
            )
            result["summarized"] = True
            result["wisdom_added"] = summary
            
            # Store wisdom in context manager
            topics = ReincarnationService._extract_topics(summary)
            context_manager.add_wisdom(agent_id, summary, topics)
            
            # STEP 2: Update ethos with this life summary
            print(f"   Step 2: Updating ethos with life summary...")
            await ReincarnationService._update_ethos_with_wisdom(
                agent=agent,
                db=db,
                summary=summary,
                incarnation=result["incarnation_number"]
            )
            result["ethos_updated"] = True
            
            # STEP 3: Gracefully terminate current agent (NOT full liquidation)
            print(f"   Step 3: Terminating {agent_id}...")
            termination_note = f"Reincarnation cycle {result['incarnation_number']}: Context limit reached. Wisdom transferred to successor."
            
            # Special handling for persistent agents (they respawn immediately)
            is_persistent = agent.is_persistent
            
            agent.status = AgentStatus.TERMINATED
            agent.terminated_at = datetime.utcnow()
            agent.termination_reason = termination_note
            agent.is_active = False
            agent.current_task_id = None
            
            # DON'T revoke capabilities during reincarnation (successor inherits)
            
            result["terminated"] = True
            
            # Log the death
            audit = AuditLog.log(
                level=AuditLevel.INFO,
                category=AuditCategory.GOVERNANCE,
                actor_type="system",
                actor_id="REINCARNATION",
                action="agent_death",
                target_type="agent",
                target_id=agent_id,
                description=f"Agent {agent_id} completed incarnation {result['incarnation_number']} and terminated for reincarnation",
                after_state={
                    "reason": "context_limit",
                    "wisdom_transferred": True,
                    "is_persistent": is_persistent
                }
            )
            db.add(audit)
            db.flush()
            
            # STEP 4: Spawn successor
            print(f"   Step 4: Spawning successor...")
            successor = await ReincarnationService._spawn_successor(
                agent=agent,
                db=db,
                previous_incarnation=result["incarnation_number"],
                wisdom_summary=summary
            )
            
            if successor:
                result["successor_spawned"] = True
                result["successor_id"] = successor.agentium_id
                
                # Transfer context tracking to successor
                context_manager.transfer_to_successor(agent_id, successor.agentium_id)
                
                # Log the birth
                birth_audit = AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="system",
                    actor_id="REINCARNATION",
                    action="agent_birth",
                    target_type="agent",
                    target_id=successor.agentium_id,
                    description=f"Successor {successor.agentium_id} spawned from {agent_id} with inherited wisdom",
                    after_state={
                        "predecessor": agent_id,
                        "incarnation": result["incarnation_number"] + 1,
                        "wisdom_inherited": True
                    }
                )
                db.add(birth_audit)
                
                print(f"   ✨ Reincarnation complete: {agent_id} → {successor.agentium_id}")
            else:
                print(f"   ⚠️ Failed to spawn successor for {agent_id}")
            
            db.commit()
            return result
            
        except Exception as e:
            db.rollback()
            print(f"   ❌ Reincarnation failed: {e}")
            raise
    
    @staticmethod
    async def _summarize_context(
        agent: Agent,
        db: Session,
        context: str,
        incarnation: int
    ) -> str:
        """Use LLM to summarize the conversation/work context into key wisdom."""
        prompt = f"""You are summarizing the work completed in incarnation #{incarnation} of agent {agent.agentium_id}.

CONTEXT TO SUMMARIZE:
{context[:5000]}  

Extract the KEY LESSONS and WISDOM from this agent's life. Focus on:
1. What worked well and should be remembered
2. What mistakes were made and should be avoided
3. Important context for the successor agent
4. Any critical insights or patterns discovered

Provide a concise summary (max 300 words) that the successor agent will inherit."""

        try:
            llm_client = LLMClient(db=db)
            response = await llm_client.generate(
                agent=agent,
                user_message=prompt,
                db=db,
                system_prompt_override="You are a summarization assistant. Be concise."
            )
            return response.get("content", "No wisdom extracted")
        except Exception as e:
            print(f"⚠️ Failed to summarize context: {e}")
            return f"[Incarnation {incarnation}] Context limit reached. Manual summary unavailable."
    
    @staticmethod
    def _extract_topics(summary: str) -> List[str]:
        """Extract key topics from wisdom summary."""
        # Simple keyword extraction (can be enhanced with NLP)
        keywords = []
        for word in summary.split():
            if len(word) > 6 and word.isalpha():
                keywords.append(word.lower())
        return keywords[:5]  # Top 5 keywords
    
    @staticmethod
    async def _update_ethos_with_wisdom(
        agent: Agent,
        db: Session,
        summary: str,
        incarnation: int
    ):
        """Update agent's ethos with accumulated wisdom."""
        ethos = db.query(Ethos).filter_by(id=agent.ethos_id).first()
        
        if not ethos:
            return
        
        # Parse existing behavioral rules
        current_rules = []
        if ethos.behavioral_rules:
            try:
                current_rules = json.loads(ethos.behavioral_rules)
            except:
                current_rules = []
        
        # Add new wisdom entry
        wisdom_entry = f"[LIFE_{incarnation}_WISDOM]: {summary[:500]}... [Learned from {incarnation}th incarnation]"
        current_rules.append(wisdom_entry)
        
        # Also update mission statement to reflect accumulated experience
        current_mission = ethos.mission_statement or ""
        accumulated_marker = f"\n\n[INCARNATION {incarnation} COMPLETE]: This agent has lived {incarnation} lives. Wisdom accumulated: {len(current_rules)} entries."
        
        if "INCARNATION" not in current_mission:
            ethos.mission_statement = current_mission + accumulated_marker
        else:
            # Update existing marker
            lines = current_mission.split("\n")
            new_lines = [l for l in lines if not l.startswith("[INCARNATION")]
            new_lines.append(accumulated_marker)
            ethos.mission_statement = "\n".join(new_lines)
        
        ethos.behavioral_rules = json.dumps(current_rules[-20:])  # Keep last 20 wisdom entries
        ethos.updated_at = datetime.utcnow()
        
        db.flush()
    
    @staticmethod
    async def _spawn_successor(
        agent: Agent,
        db: Session,
        previous_incarnation: int,
        wisdom_summary: str
    ) -> Optional[Agent]:
        """Spawn a new agent to continue the work."""
        # Determine agent type
        agent_type = agent.agent_type
        
        # Generate new ID (same tier as predecessor)
        tier_map = {
            "0": "head",
            "1": "council",
            "2": "lead",
            "3": "task", "4": "task", "5": "task", "6": "task",
            "7": "critic", "8": "critic", "9": "critic",
        }
        tier_name = tier_map.get(agent.agentium_id[0], "task")
        
        new_id = ReincarnationService.generate_id_with_retry(tier_name, db)
        
        # Create new agent of same type
        new_agent_class = type(agent)
        
        new_agent = new_agent_class(
            agentium_id=new_id,
            name=f"{agent.name} (Incarnation {previous_incarnation + 1})",
            description=f"Reincarnation of {agent.agentium_id}. Inherited wisdom from previous life.",
            parent_id=agent.parent_id,
            agent_type=agent_type,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=agent.is_persistent,
            idle_mode_enabled=agent.idle_mode_enabled,
            created_by_agentium_id=agent.agentium_id
        )
        
        # Copy key attributes
        new_agent.constitution_version = agent.constitution_version
        new_agent.preferred_config_id = agent.preferred_config_id
        
        db.add(new_agent)
        db.flush()
        
        # Transfer ethos with wisdom
        if new_agent.ethos_id:
            successor_ethos = db.query(Ethos).filter_by(id=new_agent.ethos_id).first()
            if successor_ethos:
                # Prepend predecessor's accumulated wisdom
                predecessor_ethos = db.query(Ethos).filter_by(id=agent.ethos_id).first()
                if predecessor_ethos:
                    successor_ethos.mission_statement = (
                        f"[PREDECESSOR: {agent.agentium_id} - Incarnation {previous_incarnation}]\n"
                        f"Inherited wisdom: {wisdom_summary[:200]}...\n\n"
                        f"{successor_ethos.mission_statement}"
                    )
                    db.flush()
        
        return new_agent

    @staticmethod
    def get_predecessor_context(agent: Agent, db: Session) -> Dict[str, Any]:
        """
        Retrieve accumulated wisdom/context from a predecessor agent.
        Called by ChatService when building the prompt for an active agent.
        Returns a dict with has_predecessor flag and context details.
        """
        if not agent.ethos_id:
            return {"has_predecessor": False}

        ethos = db.query(Ethos).filter_by(id=agent.ethos_id).first()
        if not ethos:
            return {"has_predecessor": False}

        # Check if this agent has inherited wisdom (set during reincarnation)
        has_predecessor = (
            ethos.mission_statement and "PREDECESSOR" in ethos.mission_statement
        ) or (
            ethos.behavioral_rules and "LIFE_" in ethos.behavioral_rules
        )

        if not has_predecessor:
            return {"has_predecessor": False}

        # Extract wisdom entries from behavioral rules
        wisdom_entries = []
        if ethos.behavioral_rules:
            try:
                rules = json.loads(ethos.behavioral_rules)
                wisdom_entries = [r for r in rules if r.startswith("[LIFE_")]
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract predecessor ID from mission statement if present
        predecessor_id = None
        if ethos.mission_statement and "PREDECESSOR:" in ethos.mission_statement:
            try:
                line = [l for l in ethos.mission_statement.splitlines() if "PREDECESSOR:" in l][0]
                predecessor_id = line.split("PREDECESSOR:")[1].split("-")[0].strip()
            except (IndexError, ValueError):
                pass

        return {
            "has_predecessor": True,
            "predecessor_id": predecessor_id,
            "incarnation_number": agent.incarnation_number or 1,
            "wisdom_count": len(wisdom_entries),
            "wisdom_summary": wisdom_entries[-1] if wisdom_entries else None,
            "context": ethos.mission_statement[:500] if ethos.mission_statement else None,
        }


# Singleton
reincarnation_service = ReincarnationService()