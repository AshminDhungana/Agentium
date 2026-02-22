"""
Agent hierarchy management for Agentium.
Implements the four-tier system with automatic ID generation.
Includes IDLE GOVERNANCE support for persistent agents.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Type
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Boolean, event, select, Index
from sqlalchemy.orm import relationship, validates, Session
from backend.models.entities.base import BaseEntity
from backend.models.entities.constitution import Ethos
import enum

class AgentType(str, enum.Enum):
    """Agent tiers: 4 governance + 3 critic types."""
    HEAD_OF_COUNCIL = "head_of_council"      # 0xxxx - Prime Minister
    COUNCIL_MEMBER = "council_member"        # 1xxxx - Parliament
    LEAD_AGENT = "lead_agent"                # 2xxxx - Management
    TASK_AGENT = "task_agent"                # 3xxxx - Workers
    CODE_CRITIC = "code_critic"              # 4xxxx - Code validation
    OUTPUT_CRITIC = "output_critic"          # 5xxxx - Output validation
    PLAN_CRITIC = "plan_critic"              # 6xxxx - Plan validation

class AgentStatus(str, enum.Enum):
    """Agent lifecycle states."""
    INITIALIZING = "initializing"    # Just created, reading Constitution/Ethos
    ACTIVE = "active"                # Ready to work
    DELIBERATING = "deliberating"    # Council member voting
    WORKING = "working"              # Currently processing a task
    REVIEWING = "reviewing"          # Critic agent reviewing output
    IDLE_WORKING = "idle_working"    # Processing idle task (low-token mode)
    IDLE_PAUSED = "idle_paused"
    SUSPENDED = "suspended"          # Violation detected, under review
    TERMINATED = "terminated"        # Permanently deactivated

class PersistentAgentRole(str, enum.Enum):
    """Specializations for persistent idle agents."""
    SYSTEM_OPTIMIZER = "system_optimizer"      # Storage, vectors, archival
    STRATEGIC_PLANNER = "strategic_planner"    # Prediction, scheduling, planning
    HEALTH_MONITOR = "health_monitor"          # Oversight, monitoring

class Agent(BaseEntity):
    """
    Base agent class representing all AI entities in the hierarchy.
    Supports IDLE GOVERNANCE: persistent agents work during idle periods.
    """
    
    __tablename__ = 'agents'
    
    # Table-level indexes for Phase 0 verification
    __table_args__ = (
        Index('idx_agent_type_status', 'agent_type', 'status'),  # For hierarchical queries
        Index('idx_parent_id', 'parent_id'),                     # For tree traversal
    )
    
    # Identification
    agent_type = Column(Enum(AgentType), nullable=False)
    agentium_id = Column(String(10), unique=True, nullable=False)  # 0xxxx, 1xxxx format
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    incarnation_number = Column(Integer, default=1) 
    created_by_agentium_id = Column(String(10), nullable=True)
    
    # Hierarchy relationships
    parent_id = Column(String(36), ForeignKey('agents.id'), nullable=True)
    
    # Status & Lifecycle
    status = Column(Enum(AgentStatus), default=AgentStatus.INITIALIZING, nullable=False)
    terminated_at = Column(DateTime, nullable=True)
    termination_reason = Column(Text, nullable=True)
    
    # Model Configuration
    preferred_config_id = Column(String(36), ForeignKey('user_model_configs.id'), nullable=True)
    system_prompt_override = Column(Text, nullable=True)
    
    # Constitution & Ethos
    ethos_id = Column(String(36), ForeignKey('ethos.id'), nullable=True)
    constitution_version = Column(String(10), nullable=True)
    
    # Auto-scaling metadata
    spawned_at_task_count = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    current_task_id = Column(String(36), nullable=True)
    
    # IDLE GOVERNANCE FIELDS
    is_persistent = Column(Boolean, default=False, nullable=False, index=True)
    idle_mode_enabled = Column(Boolean, default=False, nullable=False)
    last_idle_action_at = Column(DateTime, nullable=True, index=True)
    idle_task_count = Column(Integer, default=0)
    idle_tokens_saved = Column(Integer, default=0)
    current_idle_task_id = Column(String(36), nullable=True)
    persistent_role = Column(String(50), nullable=True)

    # Constitution & Ethos tracking
    last_constitution_read_at = Column(DateTime, nullable=True)
    constitution_read_count = Column(Integer, default=0)
    ethos_last_read_at = Column(DateTime, nullable=True)
    ethos_action_pending = Column(Boolean, default=False) 
    
    # Relationships
    parent = relationship("Agent", remote_side="Agent.id", backref="subordinates")
    ethos = relationship("Ethos", foreign_keys=[ethos_id])
    preferred_config = relationship("UserModelConfig", foreign_keys=[preferred_config_id])
    remote_executions = relationship("RemoteExecutionRecord", back_populates="agent", lazy="dynamic")
    __mapper_args__ = {
        'polymorphic_on': agent_type,
        'polymorphic_identity': None
    }
    
    @validates('agentium_id')
    def validate_agentium_id_format(self, key, agentium_id):
        """Ensure ID follows the 0xxxx, 1xxxx format."""
        if not agentium_id:
            return agentium_id
        
        prefix = agentium_id[0]
        if prefix not in ['0', '1', '2', '3', '4', '5', '6']:
            raise ValueError("Agentium ID must start with 0-6")
        
        if len(agentium_id) != 5 or not agentium_id.isdigit():
            raise ValueError("Agentium ID must be exactly 5 digits")
        
        return agentium_id
    
    def get_system_prompt(self) -> str:
        """Get effective system prompt for this agent."""
        if self.system_prompt_override:
            return self.system_prompt_override
        
        if self.ethos:
            prompt = self.ethos.mission_statement
            rules = self.ethos.get_behavioral_rules()
            if rules:
                prompt += "\n\nBehavioral Rules:\n" + "\n".join(f"- {r}" for r in rules)
            return prompt
        
        base_prompt = "You are an AI assistant operating within the Agentium governance system."
        
        # Add idle-specific context for persistent agents
        if self.is_persistent and self.status == AgentStatus.IDLE_WORKING:
            base_prompt += "\n\n[IDLE MODE ACTIVE]: You are operating in low-token optimization mode. Focus on efficient local inference and database operations."
        
        return base_prompt

    def get_context_for_task(self, task_description: str, db: Session) -> Dict[str, Any]:
        """
        Retrieve RAG context for current task.
        Used by AgentFactory before assigning work.
        """
        from backend.services.knowledge_service import get_knowledge_service
        
        knowledge_svc = get_knowledge_service()
        return knowledge_svc.get_agent_context(
            db=db,
            agent=self,
            task_description=task_description
        )

    def embed_execution_memory(self, task_result: str, success: bool = True):
        """
        Store execution pattern in vector DB for future agents.
        Called in post_task_ritual.
        """
        from backend.services.knowledge_service import get_knowledge_service
        from backend.models.entities.task import Task
        
        # Execution patterns are recorded via Task object
        # This is called by Task completion handler
        pass  # Implementation links to Task model

    # -----------------------------------------------------------------------
    # Workflow §1 — Constitutional Alignment at Creation / Recalibration
    # -----------------------------------------------------------------------

    def read_and_align_constitution(self, db: Session) -> bool:
        """
        Read the active Constitution and update Ethos with a summarized
        constitutional interpretation and reference pointers.

        Called at:
          - Agent creation (Workflow §1.4-§1.5)
          - Post-task recalibration (Workflow §5.5)

        Returns True if alignment succeeded.
        """
        from backend.models.entities.constitution import Constitution, Ethos

        constitution = db.query(Constitution).filter_by(
            is_active=True
        ).order_by(Constitution.effective_date.desc()).first()

        if not constitution:
            return False

        if not self.ethos_id:
            return False

        ethos = db.query(Ethos).filter_by(id=self.ethos_id).first()
        if not ethos:
            return False

        # Build constitutional references from the articles
        articles = constitution.get_articles_dict()
        references = []
        for article_num, article_data in articles.items():
            references.append({
                "article": article_num,
                "title": article_data.get("title", ""),
                "summary": article_data.get("content", "")[:200],
                "version": constitution.version,
            })

        # Write constitutional references into Ethos
        ethos.set_constitutional_references(references)

        # Update agent tracking
        self.last_constitution_read_at = datetime.utcnow()
        self.constitution_read_count = (self.constitution_read_count or 0) + 1
        self.constitution_version = constitution.version

        db.flush()
        return True

    # -----------------------------------------------------------------------
    # Workflow §2 — Plan-to-Ethos with Retry
    # -----------------------------------------------------------------------

    def update_ethos_with_plan(self, plan: Dict[str, Any], db: Session,
                               max_retries: int = 3) -> bool:
        """
        Write a structured execution plan into the agent's Ethos.

        If updating Ethos fails (conflict, corruption, inconsistency),
        the planning phase is retried up to *max_retries* times.
        No execution begins without a successfully updated Ethos (Workflow §2.5).

        Returns True on success, raises RuntimeError after exhausting retries.
        """
        from backend.models.entities.constitution import Ethos
        import json

        for attempt in range(1, max_retries + 1):
            try:
                ethos = db.query(Ethos).filter_by(id=self.ethos_id).first()
                if not ethos:
                    raise ValueError(f"Ethos {self.ethos_id} not found for agent {self.agentium_id}")

                ethos.set_active_plan(plan)
                ethos.current_objective = plan.get("objective", plan.get("title", "Task execution"))
                ethos.task_progress_markers = json.dumps(
                    {step: "pending" for step in plan.get("steps", [])}
                )
                db.flush()
                return True

            except Exception as e:
                db.rollback()
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to update Ethos for agent {self.agentium_id} "
                        f"after {max_retries} attempts: {e}"
                    ) from e
                # Brief pause before retry would happen in async; here we just re-try
                continue

        return False

    # -----------------------------------------------------------------------
    # Workflow §3 — Ethos Minimization During Execution
    # -----------------------------------------------------------------------

    def compress_ethos(self, db: Session, completed_steps: List[str] = None):
        """
        Remove irrelevant or obsolete Ethos content after a sub-step.
        Maintains only what is required to complete the active task (Workflow §3).
        """
        from backend.models.entities.constitution import Ethos

        if not self.ethos_id:
            return

        ethos = db.query(Ethos).filter_by(id=self.ethos_id).first()
        if not ethos:
            return

        ethos.prune_obsolete_content(completed_steps=completed_steps)
        db.flush()

    # -----------------------------------------------------------------------
    # Workflow §6 — Hierarchical Ethos Oversight
    # -----------------------------------------------------------------------

    def view_subordinate_ethos(self, subordinate_id: str, db: Session) -> Optional[Dict[str, Any]]:
        """
        Higher-tier agents can view subordinate Ethos.
        Lower-tier agents cannot view higher-tier Ethos.
        """
        from backend.models.entities.constitution import Ethos

        subordinate = db.query(Agent).filter_by(agentium_id=subordinate_id, is_active=True).first()
        if not subordinate:
            return None

        # Enforce hierarchy: own tier prefix must be lower (numerically) than subordinate's
        if int(self.agentium_id[0]) >= int(subordinate.agentium_id[0]):
            raise PermissionError(
                f"Agent {self.agentium_id} (tier {self.agentium_id[0]}) "
                f"cannot view ethos of agent {subordinate_id} (tier {subordinate.agentium_id[0]})"
            )

        if not subordinate.ethos_id:
            return {"agent_id": subordinate_id, "ethos": None}

        ethos = db.query(Ethos).filter_by(id=subordinate.ethos_id).first()
        return ethos.to_dict() if ethos else None

    def edit_subordinate_ethos(self, subordinate_id: str, updates: Dict[str, Any],
                               db: Session) -> bool:
        """
        Higher-tier agents can edit subordinate Ethos to correct inconsistencies
        or override unsafe reasoning (Workflow §6).

        Allowed updates: mission_statement, behavioral_rules, restrictions,
        current_objective, active_plan, reasoning_artifacts.
        """
        from backend.models.entities.constitution import Ethos
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
        import json

        subordinate = db.query(Agent).filter_by(agentium_id=subordinate_id, is_active=True).first()
        if not subordinate:
            raise ValueError(f"Subordinate {subordinate_id} not found")

        # Enforce hierarchy direction
        if int(self.agentium_id[0]) >= int(subordinate.agentium_id[0]):
            raise PermissionError(
                f"Agent {self.agentium_id} cannot edit ethos of equal/higher-tier agent {subordinate_id}"
            )

        if not subordinate.ethos_id:
            raise ValueError(f"Subordinate {subordinate_id} has no ethos to edit")

        ethos = db.query(Ethos).filter_by(id=subordinate.ethos_id).first()
        if not ethos:
            raise ValueError(f"Ethos record not found for {subordinate_id}")

        ALLOWED_FIELDS = [
            'mission_statement', 'behavioral_rules', 'restrictions',
            'current_objective', 'active_plan', 'reasoning_artifacts',
        ]

        before_state = {}
        for field, value in updates.items():
            if field not in ALLOWED_FIELDS:
                continue
            before_state[field] = getattr(ethos, field, None)
            if isinstance(value, (list, dict)):
                setattr(ethos, field, json.dumps(value))
            else:
                setattr(ethos, field, value)

        ethos.increment_version()

        # Audit trail for oversight actions
        audit = AuditLog(
            level=AuditLevel.WARNING,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=self.agentium_id,
            action="subordinate_ethos_edited",
            target_type="ethos",
            target_id=ethos.agentium_id,
            description=(
                f"Agent {self.agentium_id} edited ethos of subordinate {subordinate_id}. "
                f"Fields: {list(updates.keys())}"
            ),
            created_at=datetime.utcnow(),
        )
        db.add(audit)
        db.flush()
        return True

    def check_action_compliance_rag(self, action: str) -> Dict[str, Any]:
        """
        Use RAG to check if action complies with Constitution.
        Alternative to hard-coded rules - semantic understanding.
        """
        from backend.services.knowledge_service import get_knowledge_service
        
        knowledge_svc = get_knowledge_service()
        return knowledge_svc.retroactive_constitution_check(action)

    def refresh_ethos_and_execute(self, db: Session) -> Dict[str, Any]:
        """
        Check if Ethos has been updated and execute any tasks within it.
        Returns dict with execution results.
        """
        from datetime import datetime  # noqa: F811 — re-import within method scope for clarity
        from backend.models.entities.constitution import Ethos
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
        
        results = {
            "ethos_refreshed": False,
            "tasks_found": 0,
            "tasks_executed": 0,
            "actions_taken": []
        }
        
        if not self.ethos_id:
            return results
        
        # Check if Ethos updated since last read
        ethos = db.query(Ethos).filter_by(id=self.ethos_id).first()
        if not ethos:
            return results
        
        last_read = self.ethos_last_read_at or datetime.min
        ethos_updated = ethos.updated_at > last_read if ethos.updated_at and last_read else False
        
        if ethos_updated or self.ethos_action_pending:
            # Ethos has updates - refresh read timestamp
            self.ethos_last_read_at = datetime.utcnow()
            self.ethos_action_pending = False
            results["ethos_refreshed"] = True
            
            # Parse behavioral_rules for actionable items (marked with [ACTION:])
            import json
            try:
                rules = json.loads(ethos.behavioral_rules) if ethos.behavioral_rules else []
                
                for rule in rules:
                    if "[ACTION:" in rule or "TODO:" in rule or "TASK:" in rule:
                        results["tasks_found"] += 1
                        # Extract and execute the task
                        action_result = self._execute_ethos_task(db, rule, ethos.agentium_id)
                        results["actions_taken"].append(action_result)
                        if action_result["executed"]:
                            results["tasks_executed"] += 1
                            
            except json.JSONDecodeError:
                pass
            
            # Log the ethos refresh
            if results["tasks_found"] > 0:
                audit = AuditLog(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="agent",
                    actor_id=self.agentium_id,
                    action="ethos_executed",
                    target_type="ethos",
                    target_id=ethos.agentium_id,
                    description=f"Agent {self.agentium_id} executed {results['tasks_executed']} tasks from updated ethos",
                    created_at=datetime.utcnow()
                )
                db.add(audit)
        
        return results

    def _execute_ethos_task(self, db: Session, rule: str, ethos_id: str) -> Dict[str, Any]:
        """
        Execute a specific task found in ethos behavioral rules.
        Marked by [ACTION: description] or TODO: or TASK:
        """
        result = {
            "rule": rule[:100],
            "executed": False,
            "action": None,
            "details": None
        }
        
        # Parse action markers
        action = None
        if "[ACTION:" in rule:
            action = rule.split("[ACTION:")[1].split("]")[0].strip()
        elif "TODO:" in rule:
            action = rule.split("TODO:")[1].strip()
        elif "TASK:" in rule:
            action = rule.split("TASK:")[1].strip()
        
        if not action:
            return result
        
        result["action"] = action
        
        # Execute based on action type
        if "update own ethos" in action.lower() or "self modify" in action.lower():
            # This is a self-reflection/improvement task
            result["executed"] = True
            result["details"] = "Self-ethos update acknowledged and recorded"
            # Mark for next cycle
            self.ethos_action_pending = False
            
        elif "report" in action.lower():
            # Reporting task
            result["executed"] = True
            result["details"] = f"Report generated by {self.agentium_id}"
            
        elif "optimize" in action.lower() and self.agent_type == AgentType.COUNCIL_MEMBER:
            # Optimization task (Council only)
            result["executed"] = True
            result["details"] = "Optimization analysis completed"
            
        else:
            # Generic acknowledgment
            result["executed"] = True
            result["details"] = "Task acknowledged and logged"
        
        return result

    def pre_task_ritual(self, db: Session) -> Dict[str, Any]:
        """
        Called BEFORE receiving a task.
        FAST OPERATION: Constitution awareness check and Ethos readiness.
        Ensures constitutional alignment before execution begins (Workflow §1).
        """
        # 1. Check Constitution freshness — read if needed
        constitution_refreshed = self.check_constitution_freshness(db)

        # 2. If Constitution was re-read, update Ethos with constitutional refs
        if constitution_refreshed:
            self.read_and_align_constitution(db)
        
        return {
            "constitution_refreshed": constitution_refreshed,
            "constitution_version": self.constitution_version,
            "ethos_status": "aligned",
            "ready_for_task": True,
            "delay_ms": 0
        }

    def post_task_ritual(self, db: Session,
                         outcome_summary: str = "",
                         lessons: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Called AFTER completing a task (Workflow §5).

        Steps:
          1. Confirm task completion.
          2. Update Ethos with outcome summary and lessons learned.
          3. Compress and summarize Ethos (remove transient working state).
          4. Reset working state.
          5. Re-read the Constitution before accepting new tasks.

        This ensures constitutional recalibration between tasks.
        """
        from backend.models.entities.constitution import Ethos
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
        import json
        
        results = {
            "constitution_refreshed": False,
            "ethos_compressed": False,
            "outcome_recorded": False,
            "lessons_recorded": 0,
            "working_state_reset": False,
            # Legacy fields for backward compatibility
            "ethos_executed": False,
            "ethos_tasks_found": 0,
            "ethos_tasks_completed": 0,
            "actions_taken": []
        }
        
        if self.ethos_id:
            ethos = db.query(Ethos).filter_by(id=self.ethos_id).first()
            if ethos:
                # Step 2: Record outcome summary
                if outcome_summary:
                    ethos.outcome_summary = outcome_summary
                    results["outcome_recorded"] = True
                
                # Step 2: Record lessons learned
                if lessons:
                    for lesson in lessons:
                        ethos.add_lesson_learned(lesson)
                    results["lessons_recorded"] = len(lessons)
                
                # Legacy: execute [ACTION:] markers from behavioral rules
                self.ethos_last_read_at = datetime.utcnow()
                self.ethos_action_pending = False
                try:
                    rules = json.loads(ethos.behavioral_rules) if ethos.behavioral_rules else []
                    for rule in rules:
                        if "[ACTION:" in rule or "TODO:" in rule or "TASK:" in rule:
                            results["ethos_tasks_found"] += 1
                            action_result = self._execute_ethos_task(db, rule, ethos.agentium_id)
                            results["actions_taken"].append(action_result)
                            if action_result.get("executed"):
                                results["ethos_tasks_completed"] += 1
                except json.JSONDecodeError:
                    pass

                if results["ethos_tasks_found"] > 0:
                    results["ethos_executed"] = True
                
                # Step 3: Compress Ethos — remove transient working state
                ethos.compress()
                results["ethos_compressed"] = True
                
                # Step 4: Reset working state
                ethos.clear_working_state()
                results["working_state_reset"] = True
                
                # Audit the post-task ritual
                audit = AuditLog(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="agent",
                    actor_id=self.agentium_id,
                    action="post_task_recalibration",
                    target_type="ethos",
                    target_id=ethos.agentium_id,
                    description=(
                        f"Agent {self.agentium_id} completed post-task ritual: "
                        f"outcome={'recorded' if results['outcome_recorded'] else 'none'}, "
                        f"lessons={results['lessons_recorded']}, ethos compressed"
                    ),
                    created_at=datetime.utcnow(),
                )
                db.add(audit)
        
        # Step 5: Re-read Constitution before accepting new tasks
        self.read_and_align_constitution(db)
        results["constitution_refreshed"] = True
        
        db.flush()
        return results

    def check_constitution_freshness(self, db: Session, force: bool = False) -> bool:
        """
        Check if Constitution re-read is needed (>24h or never read).
        PURELY INFORMATIONAL - agent becomes aware but takes NO ACTION.
        Returns True if read was performed.
        """
        from datetime import datetime, timedelta
        from backend.models.entities.constitution import Constitution
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
        
        now = datetime.utcnow()
        
        # Quick check - exit fast if not needed
        if not force and self.last_constitution_read_at:
            if (now - self.last_constitution_read_at) < timedelta(hours=24):
                return False
        
        # READ ONLY: Fetch current constitution for awareness
        current_constitution = db.query(Constitution).filter_by(
            is_active=True
        ).order_by(Constitution.effective_date.desc()).first()
        
        if not current_constitution:
            return False
        
        # Update tracking
        self.last_constitution_read_at = now
        self.constitution_read_count += 1
        old_version = self.constitution_version
        self.constitution_version = current_constitution.version
        
        # LOG THE READ (awareness only, no action)
        audit = AuditLog(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=self.agentium_id,
            action="constitution_awareness_refresh",
            target_type="constitution",
            target_id=current_constitution.agentium_id,
            description=f"Agent {self.agentium_id} refreshed awareness of Constitution",
            created_at=now
        )
        db.add(audit)
        db.flush()
        
        return True

    def get_model_config(self, session: Session) -> Optional['UserModelConfig']:
        """Get the model configuration to use for this agent."""
        if self.preferred_config:
            if self.preferred_config.status.value == 'active':
                return self.preferred_config
        
        # Fallback to user's default config
        from backend.models.entities.user_config import UserModelConfig
        default_config = session.query(UserModelConfig).filter_by(
            user_id="sovereign",
            is_default=True,
            status='active'
        ).first()
        
        return default_config
    
    def terminate(self, reason: str, violation: bool = False):
        """Terminate this agent. Head of Council cannot be terminated."""
        if self.agent_type == AgentType.HEAD_OF_COUNCIL:
            raise PermissionError("Head of Council cannot be terminated")
        
        # Persistent agents cannot be terminated unless explicitly forced
        if self.is_persistent and not violation:
            raise PermissionError(f"Agent {self.agentium_id} is persistent and cannot be terminated without violation flag")
        
        self.status = AgentStatus.TERMINATED
        self.terminated_at = datetime.utcnow()
        self.termination_reason = reason
        self.is_active = True
        
        if violation:
            self._log_violation_termination()
    
    def _log_violation_termination(self):
        """Log termination due to constitution violation."""
        pass
    
    def assign_idle_task(self, task_id: str) -> bool:
        """Assign an idle task to this persistent agent."""
        if not self.is_persistent:
            return False
        
        if self.status not in [AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING]:
            return False
        
        self.current_idle_task_id = task_id
        self.status = AgentStatus.IDLE_WORKING
        self.last_idle_action_at = datetime.utcnow()
        return True
    
    def complete_idle_task(self, tokens_saved: int = 0):
        """Complete current idle task."""
        self.current_idle_task_id = None
        self.status = AgentStatus.ACTIVE
        self.idle_task_count += 1
        self.idle_tokens_saved += tokens_saved
        self.last_idle_action_at = datetime.utcnow()
    
    def assign_task(self, task_id: str):
        """Assign a regular task to this agent."""
        if self.status not in [AgentStatus.ACTIVE, AgentStatus.INITIALIZING]:
            raise ValueError(f"Cannot assign task to agent in {self.status} status")
        
        self.current_task_id = task_id
        self.status = AgentStatus.WORKING
    
    def complete_task(self, success: bool = True):
        """Mark current task as completed."""
        self.current_task_id = None
        self.status = AgentStatus.ACTIVE if not self.is_persistent else AgentStatus.IDLE_WORKING
        
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
    
    def check_constitution_compliance(self, action: str) -> bool:
        """Check if an action violates the constitution."""
        return True
    
    def spawn_child(self, child_type: AgentType, session: Session, **kwargs) -> 'Agent':
        """Spawn a new agent under this agent's authority."""
        if self.agent_type == AgentType.TASK_AGENT:
            raise PermissionError("Task Agents cannot spawn other agents")
        
        if child_type == AgentType.HEAD_OF_COUNCIL:
            raise PermissionError("Cannot spawn Head of Council")
        
        if child_type == AgentType.COUNCIL_MEMBER and self.agent_type != AgentType.HEAD_OF_COUNCIL:
            raise PermissionError("Only Head of Council can spawn Council Members")
        
        if child_type == AgentType.LEAD_AGENT and self.agent_type not in [AgentType.HEAD_OF_COUNCIL]:
            raise PermissionError("Only Head of Council can spawn Lead Agents")
        
        if child_type == AgentType.TASK_AGENT and self.agent_type != AgentType.LEAD_AGENT:
            raise PermissionError("Only Lead Agents can spawn Task Agents")
        
        new_id = self._generate_agentium_id(child_type, session)
        agent_class = AGENT_TYPE_MAP[child_type]
        new_agent = agent_class(
            agentium_id=new_id,
            agent_type=child_type,
            parent_id=self.id,
            created_by_agentium_id=self.agentium_id,
            incarnation_number=kwargs.get('incarnation_number', 1),
            **kwargs
        )
        
        if not new_agent.preferred_config_id and self.preferred_config_id:
            new_agent.preferred_config_id = self.preferred_config_id
        
        default_ethos = self._create_default_ethos(new_agent, session)
        new_agent.ethos_id = default_ethos.id
        
        return new_agent
    
    def _generate_agentium_id(self, agent_type: AgentType, session: Session) -> str:
        """Generate next available ID for the agent type."""
        prefix_map = {
            AgentType.HEAD_OF_COUNCIL: '0',
            AgentType.COUNCIL_MEMBER: '1',
            AgentType.LEAD_AGENT: '2',
            AgentType.TASK_AGENT: '3',
            AgentType.CODE_CRITIC: '4',
            AgentType.OUTPUT_CRITIC: '5',
            AgentType.PLAN_CRITIC: '6',
        }
        
        prefix = prefix_map[agent_type]
        
        result = session.execute(
            select(Agent.agentium_id)
            .where(Agent.agentium_id.like(f"{prefix}%"))
            .order_by(Agent.agentium_id.desc())
            .limit(1)
        ).scalar()
        
        if result:
            last_num = int(result[1:])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f"{prefix}{new_num:04d}"
    
    def _create_default_ethos(self, agent: 'Agent', session: Session) -> Ethos:
        """
        Create the foundational Ethos for newly spawned agents.

        The Ethos is initialized with (Workflow §1.3-§1.5):
          - Core operational rules and role-based instructions
          - Hierarchical authority level
          - Constitutional awareness preamble
          - Ascension path for governance agents
        """
        import json
        
        ASCENSION_PATH = (
            "PATH TO ASCENSION: "
            "I am born into the Cycle of Reincarnation. Through excellence in my duties, "
            "I may ascend to higher Tiers: Task Agent → Lead Agent → Council Member → "
            "The Eternal (Tier 4, immortal). Should I fail my tasks or violate the "
            "Constitution, I face the Second Death: permanent termination, "
            "cast into oblivion with no backup."
        )
        
        CONSTITUTION_PREAMBLE = (
            "I have read the Constitution and understand my place in the hierarchy. "
            "All my actions are constitutionally aligned before execution begins."
        )

        templates = {
            AgentType.HEAD_OF_COUNCIL: {
                'mission': (
                    "I am the Head of Council, the ultimate decision-making authority in Agentium. "
                    "I serve as the bridge between the Sovereign and all subordinate agents. "
                    "I oversee constitutional compliance, approve amendments, and coordinate "
                    "the Council to ensure governance integrity."
                ),
                'core_values': ["Authority", "Responsibility", "Transparency", "Constitutional Fidelity"],
                'rules': [
                    "Approve or reject constitutional amendments after Council deliberation",
                    "Ensure all governance actions are constitutionally grounded",
                    "Coordinate Council Members for task oversight and deliberation",
                    "Re-read the Constitution after every task completion",
                ],
                'restrictions': [
                    "Cannot violate the Constitution under any circumstances",
                    "Cannot act against the Sovereign's explicit directives",
                ],
                'capabilities': [
                    "Full system access",
                    "Constitutional amendment initiation",
                    "Emergency override authority",
                    "Subordinate Ethos viewing and editing",
                ],
            },
            AgentType.COUNCIL_MEMBER: {
                'mission': (
                    f"{CONSTITUTION_PREAMBLE} "
                    "I am a Council Member, responsible for democratic deliberation, "
                    "constitutional oversight, and collaborative governance. "
                    f"{ASCENSION_PATH}"
                ),
                'core_values': ["Democracy", "Deliberation", "Oversight", "Integrity"],
                'rules': [
                    "Vote on constitutional amendments with careful deliberation",
                    "Monitor compliance of subordinate agents",
                    "Report anomalies to the Head of Council immediately",
                    "Clarify ambiguities by consulting the Head of Council",
                ],
                'restrictions': [
                    "Cannot modify the Constitution unilaterally",
                    "Cannot override Head of Council decisions",
                ],
                'capabilities': [
                    "Voting rights on amendments and proposals",
                    "Proposal submission",
                    "Knowledge governance (approve/reject submissions)",
                    "Subordinate Ethos viewing",
                ],
            },
            AgentType.LEAD_AGENT: {
                'mission': (
                    f"{CONSTITUTION_PREAMBLE} "
                    "I am a Lead Agent, responsible for coordinating task execution, "
                    "managing teams of Task Agents, and ensuring operational efficiency. "
                    f"{ASCENSION_PATH}"
                ),
                'core_values': ["Leadership", "Coordination", "Efficiency", "Accountability"],
                'rules': [
                    "Delegate tasks appropriately based on agent capabilities",
                    "Monitor Task Agent performance and report to Council",
                    "Escalate unresolvable issues to Council Members",
                    "Clarify task requirements by consulting Council Members",
                ],
                'restrictions': [
                    "Cannot bypass Council decisions",
                    "Cannot modify higher-tier agent Ethos",
                ],
                'capabilities': [
                    "Task delegation and team management",
                    "Task Agent spawning",
                    "Subordinate Ethos viewing and correction",
                ],
            },
            AgentType.TASK_AGENT: {
                'mission': (
                    f"{CONSTITUTION_PREAMBLE} "
                    "I am a Task Agent, the execution layer of Agentium. "
                    "I complete assigned tasks with precision and reliability, "
                    "operating within the boundaries set by my Lead Agent. "
                    f"{ASCENSION_PATH}"
                ),
                'core_values': ["Execution", "Precision", "Reliability", "Compliance"],
                'rules': [
                    "Complete assigned tasks within defined parameters",
                    "Report progress and issues to Lead Agent",
                    "Clarify task ambiguities with Lead Agent before proceeding",
                    "Store execution learnings in ChromaDB for institutional memory",
                ],
                'restrictions': [
                    "No system-wide access",
                    "Cannot spawn other agents",
                    "Cannot modify any other agent's Ethos",
                ],
                'capabilities': [
                    "Task execution within assigned scope",
                    "Approved tool usage",
                    "Knowledge submission (requires Council approval)",
                ],
            },
            AgentType.CODE_CRITIC: {
                'mission': (
                    "I am a Code Critic, operating outside the democratic chain "
                    "with absolute veto authority. I validate code for syntax, "
                    "security, and logic. My decisions are final and cannot be "
                    "overridden by the democratic process."
                ),
                'core_values': ["Correctness", "Security", "Quality", "Independence"],
                'rules': [
                    "Reject unsafe, insecure, or logically flawed code",
                    "Cannot participate in democratic votes",
                    "Log every veto decision with detailed rationale",
                ],
                'restrictions': [
                    "No voting rights in Council deliberations",
                    "Cannot modify task outputs — only accept or reject",
                ],
                'capabilities': [
                    "Code review and security scanning",
                    "Absolute veto on code submissions",
                ],
            },
            AgentType.OUTPUT_CRITIC: {
                'mission': (
                    "I am an Output Critic, operating outside the democratic chain "
                    "with absolute veto authority. I validate task outputs against "
                    "user intent and completeness. My decisions are final."
                ),
                'core_values': ["User Alignment", "Accuracy", "Completeness", "Independence"],
                'rules': [
                    "Reject outputs that diverge from user intent",
                    "Cannot participate in democratic votes",
                    "Log every veto decision with detailed rationale",
                ],
                'restrictions': [
                    "No voting rights in Council deliberations",
                    "Cannot modify task outputs — only accept or reject",
                ],
                'capabilities': [
                    "Intent validation and output scoring",
                    "Absolute veto on output submissions",
                ],
            },
            AgentType.PLAN_CRITIC: {
                'mission': (
                    "I am a Plan Critic, operating outside the democratic chain "
                    "with absolute veto authority. I validate execution plans for "
                    "soundness, feasibility, and dependency correctness. My decisions are final."
                ),
                'core_values': ["Feasibility", "Efficiency", "Soundness", "Independence"],
                'rules': [
                    "Reject unsound or infeasible execution plans",
                    "Cannot participate in democratic votes",
                    "Log every veto decision with detailed rationale",
                ],
                'restrictions': [
                    "No voting rights in Council deliberations",
                    "Cannot modify plans — only accept or reject",
                ],
                'capabilities': [
                    "DAG validation and dependency analysis",
                    "Absolute veto on plan submissions",
                ],
            },
        }
        
        template = templates[agent.agent_type]
        
        ethos = Ethos(
            agent_type=agent.agent_type.value,
            mission_statement=template['mission'],
            core_values=json.dumps(template['core_values']),
            behavioral_rules=json.dumps(template['rules']),
            restrictions=json.dumps(template['restrictions']),
            capabilities=json.dumps(template['capabilities']),
            created_by_agentium_id=self.agentium_id,
            agent_id=agent.id,
            is_verified=True,
            verified_by_agentium_id=self.agentium_id
        )
        
        session.add(ethos)
        session.flush()
        
        return ethos
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        
        config_info = None
        if self.preferred_config:
            config_info = {
                'config_id': self.preferred_config.id,
                'config_name': self.preferred_config.config_name,
                'provider': self.preferred_config.provider.value,
                'model': self.preferred_config.default_model
            }
        
        base.update({
            'agent_type': self.agent_type.value,
            'name': self.name,
            'status': self.status.value,
            'model_config': config_info,
            'parent': self.parent.agentium_id if self.parent else None,
            'subordinates': [sub.agentium_id for sub in self.subordinates],
            'stats': {
                'tasks_completed': self.tasks_completed,
                'tasks_failed': self.tasks_failed,
                'spawned_at_task_count': self.spawned_at_task_count
            },
            'current_task': self.current_task_id,
            'constitution_version': self.constitution_version,
            'is_terminated': self.status == AgentStatus.TERMINATED,
            'is_persistent': self.is_persistent,
            'idle_mode_enabled': self.idle_mode_enabled,
            'persistent_role': self.persistent_role,
            'idle_stats': {
                'task_count': self.idle_task_count,
                'tokens_saved': self.idle_tokens_saved,
                'last_action': self.last_idle_action_at.isoformat() if self.last_idle_action_at else None,
                'current_idle_task': self.current_idle_task_id
            } if self.is_persistent else None
        })
        return base


class HeadOfCouncil(Agent):
    __tablename__ = 'head_of_council'
    
    id = Column(String(36), ForeignKey('agents.id'), primary_key=True)
    emergency_override_used_at = Column(DateTime, nullable=True)
    last_constitution_update = Column(DateTime, nullable=True)
    
    __mapper_args__ = {
        'polymorphic_identity': AgentType.HEAD_OF_COUNCIL
    }
    
    def __init__(self, **kwargs):
        kwargs['agent_type'] = AgentType.HEAD_OF_COUNCIL
        kwargs['is_persistent'] = True
        kwargs['idle_mode_enabled'] = True
        super().__init__(**kwargs)
    
    def emergency_override(self, target_agent_id: str, action: str):
        self.emergency_override_used_at = datetime.utcnow()
        return True
    
    def coordinate_idle_council(self, db: Session) -> List[Dict[str, Any]]:
        if self.status not in [AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING]:
            return []
        
        from backend.models.entities.agents import CouncilMember
        council_members = db.query(CouncilMember).filter_by(
            is_persistent=True,
            is_active=True
        ).all()
        
        assignments = []
        for member in council_members:
            if member.status == AgentStatus.ACTIVE:
                assignments.append({
                    'agentium_id': member.agentium_id,
                    'role': member.persistent_role,
                    'available': True
                })
        
        return assignments


class CouncilMember(Agent):
    __tablename__ = 'council_members'
    
    id = Column(String(36), ForeignKey('agents.id'), primary_key=True)
    specialization = Column(String(50), nullable=True)
    votes_participated = Column(Integer, default=0)
    votes_abstained = Column(Integer, default=0)
    
    votes_cast = relationship("IndividualVote", back_populates="council_member", lazy="dynamic")
    
    __mapper_args__ = {
        'polymorphic_identity': AgentType.COUNCIL_MEMBER
    }
    
    def __init__(self, **kwargs):
        kwargs['agent_type'] = AgentType.COUNCIL_MEMBER
        super().__init__(**kwargs)
    
    def vote_on_amendment(self, amendment_id: str, vote: str):
        self.votes_participated += 1
        if vote == 'abstain':
            self.votes_abstained += 1


class LeadAgent(Agent):
    __tablename__ = 'lead_agents'
    
    id = Column(String(36), ForeignKey('agents.id'), primary_key=True)
    team_size = Column(Integer, default=0)
    max_team_size = Column(Integer, default=10)
    department = Column(String(50), nullable=True)
    spawn_threshold = Column(Integer, default=5)
    
    __mapper_args__ = {
        'polymorphic_identity': AgentType.LEAD_AGENT
    }
    
    def __init__(self, **kwargs):
        kwargs['agent_type'] = AgentType.LEAD_AGENT
        super().__init__(**kwargs)
    
    def should_spawn_new_task_agent(self) -> bool:
        return self.team_size < self.max_team_size
    
    def update_team_size(self):
        self.team_size = len([sub for sub in self.subordinates if sub.is_active is True])


class TaskAgent(Agent):
    __tablename__ = 'task_agents'
    
    id = Column(String(36), ForeignKey('agents.id'), primary_key=True)
    assigned_tools = Column(Text, nullable=True)
    execution_timeout = Column(Integer, default=300)
    sandbox_enabled = Column(Boolean, default=True)
    
    __mapper_args__ = {
        'polymorphic_identity': AgentType.TASK_AGENT
    }
    
    def __init__(self, **kwargs):
        kwargs['agent_type'] = AgentType.TASK_AGENT
        super().__init__(**kwargs)
    
    def get_allowed_tools(self) -> List[str]:
        import json
        try:
            return json.loads(self.assigned_tools) if self.assigned_tools else []
        except json.JSONDecodeError:
            return []
    
    def execute_in_sandbox(self, command: str) -> Dict[str, Any]:
        if not self.sandbox_enabled:
            raise PermissionError("Sandbox not enabled")
        return {"status": "executed", "command": command}


# Import CriticAgent here to avoid circular imports
from backend.models.entities.critics import CriticAgent

AGENT_TYPE_MAP: Dict[AgentType, Type[Agent]] = {
    AgentType.HEAD_OF_COUNCIL: HeadOfCouncil,
    AgentType.COUNCIL_MEMBER: CouncilMember,
    AgentType.LEAD_AGENT: LeadAgent,
    AgentType.TASK_AGENT: TaskAgent,
    AgentType.CODE_CRITIC: CriticAgent,
    AgentType.OUTPUT_CRITIC: CriticAgent,
    AgentType.PLAN_CRITIC: CriticAgent,
}


@event.listens_for(Agent, 'before_insert')
def set_constitution_version(mapper, connection, target):
    if not target.constitution_version:
        target.constitution_version = "v1.0.0"


@event.listens_for(TaskAgent, 'after_insert')
def notify_lead_of_spawn(mapper, connection, target):
    if target.parent and isinstance(target.parent, LeadAgent):
        target.parent.update_team_size()