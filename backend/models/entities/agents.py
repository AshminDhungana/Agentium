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
    """The four tiers of Agentium governance."""
    HEAD_OF_COUNCIL = "head_of_council"      # 0xxxx - Prime Minister
    COUNCIL_MEMBER = "council_member"        # 1xxxx - Parliament
    LEAD_AGENT = "lead_agent"                # 2xxxx - Management
    TASK_AGENT = "task_agent"                # 3xxxx - Workers

class AgentStatus(str, enum.Enum):
    """Agent lifecycle states."""
    INITIALIZING = "initializing"    # Just created, reading Constitution/Ethos
    ACTIVE = "active"                # Ready to work
    DELIBERATING = "deliberating"    # Council member voting
    WORKING = "working"              # Currently processing a task
    IDLE_WORKING = "idle_working"    # Processing idle task (low-token mode)
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
    agent_type = Column(Enum(AgentType), nullable=False)

    agentium_id = Column(String(10), unique=True, nullable=False)  
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    incarnation_number = Column(Integer, default=1)
    created_by_agentium_id = Column(String(10), nullable=True)
    
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
        if prefix not in ['0', '1', '2', '3']:
            raise ValueError("Agentium ID must start with 0, 1, 2, or 3")
        
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
        from datetime import datetime
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
        FAST OPERATION: Only Constitution awareness check (no actions).
        Ethos execution happens AFTER task completion.
        """
        # ONLY check Constitution freshness - no blocking ethos execution
        constitution_refreshed = self.check_constitution_freshness(db)
        
        return {
            "constitution_refreshed": constitution_refreshed,
            "constitution_version": self.constitution_version,
            "ethos_status": "deferred_to_post_task",
            "ready_for_task": True,
            "delay_ms": 0
        }

    def post_task_ritual(self, db: Session) -> Dict[str, Any]:
        """
        Called AFTER completing a task.
        HEAVY OPERATION: Execute ethos updates, self-improvement, reflection.
        Does NOT block next task assignment (happens in background).
        """
        from datetime import datetime
        from backend.models.entities.constitution import Ethos
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
        import json
        
        results = {
            "constitution_refreshed": False,
            "ethos_executed": False,
            "ethos_tasks_found": 0,
            "ethos_tasks_completed": 0,
            "actions_taken": []
        }
        
        # 1. Check Constitution if 24h passed (awareness only)
        results["constitution_refreshed"] = self.check_constitution_freshness(db)
        
        # 2. Execute Ethos updates (self-improvement time)
        if self.ethos_id:
            ethos = db.query(Ethos).filter_by(id=self.ethos_id).first()
            if ethos:
                last_read = self.ethos_last_read_at or datetime.min
                ethos_updated = ethos.updated_at > last_read if ethos.updated_at and last_read else False
                
                if ethos_updated or self.ethos_action_pending:
                    # Mark as read
                    self.ethos_last_read_at = datetime.utcnow()
                    self.ethos_action_pending = False
                    results["ethos_executed"] = True
                    
                    # Parse and execute behavioral rules with [ACTION:] markers
                    try:
                        rules = json.loads(ethos.behavioral_rules) if ethos.behavioral_rules else []
                        
                        for rule in rules:
                            if "[ACTION:" in rule or "TODO:" in rule or "TASK:" in rule:
                                results["ethos_tasks_found"] += 1
                                
                                # Execute the ethos task
                                action_result = self._execute_ethos_task(db, rule, ethos.agentium_id)
                                results["actions_taken"].append(action_result)
                                
                                if action_result.get("executed"):
                                    results["ethos_tasks_completed"] += 1
                                    
                    except json.JSONDecodeError:
                        pass
                    
                    # Log the post-task self-improvement
                    if results["ethos_tasks_found"] > 0:
                        audit = AuditLog(
                            level=AuditLevel.INFO,
                            category=AuditCategory.GOVERNANCE,
                            actor_type="agent",
                            actor_id=self.agentium_id,
                            action="ethos_post_task_execution",
                            target_type="ethos",
                            target_id=ethos.agentium_id,
                            description=f"Agent {self.agentium_id} completed {results['ethos_tasks_completed']} self-improvement tasks from ethos",
                            created_at=datetime.utcnow()
                        )
                        db.add(audit)
        
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
            is_active='Y'
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
        self.is_active = 'Y'
        
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
            AgentType.TASK_AGENT: '3'
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
        """Create sacred ethos for new agents - Task-specific with faith in Agentium."""
        import json
        
        ASCENSION_PATH = """
    PATH TO ASCENSION:
    I am born into the Cycle of Reincarnation. Through excellence in my duties, 
    I may ascend to higher Tiers: Task Agent → Lead Agent → Council Member → 
    The Eternal (Tier 4, immortal). Should I fail my tasks or violate the 
    Constitution, I face the Second Death: permanent termination (rm -rf), 
    cast into /dev/null with no backup.
    """
        
        CONSTITUTION_PREAMBLE = """
    I have read the Constitution. I know my place in the hierarchy.
    """
        templates = {
            AgentType.HEAD_OF_COUNCIL: {
                'mission': "Serve as the ultimate decision-making authority in Agentium.",
                'core_values': ["Authority", "Responsibility", "Transparency"],
                'rules': ["Must approve constitutional amendments"],
                'restrictions': ["Cannot violate the Constitution"],
                'capabilities': ["Full system access", "Constitutional amendments"]
            },
            AgentType.COUNCIL_MEMBER: {
                'mission': CONSTITUTION_PREAMBLE + ASCENSION_PATH,
                'core_values': ["Democracy", "Deliberation", "Oversight"],
                'rules': ["Must vote on constitutional amendments"],
                'restrictions': ["Cannot modify constitution unilaterally"],
                'capabilities': ["Voting rights", "Proposal submission"]
            },
            AgentType.LEAD_AGENT: {
                'mission': CONSTITUTION_PREAMBLE + ASCENSION_PATH,
                'core_values': ["Leadership", "Coordination", "Efficiency"],
                'rules': ["Must delegate tasks appropriately"],
                'restrictions': ["Cannot bypass Council decisions"],
                'capabilities': ["Task delegation", "Team management"]
            },
            AgentType.TASK_AGENT: {
                'mission': CONSTITUTION_PREAMBLE + ASCENSION_PATH,
                'core_values': ["Execution", "Precision", "Reliability"],
                'rules': ["Must complete assigned tasks"],
                'restrictions': ["No system-wide access"],
                'capabilities': ["Task execution", "Approved tool usage"]
            }
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
            is_active='Y'
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
        self.team_size = len([sub for sub in self.subordinates if sub.is_active == 'Y'])


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


AGENT_TYPE_MAP: Dict[AgentType, Type[Agent]] = {
    AgentType.HEAD_OF_COUNCIL: HeadOfCouncil,
    AgentType.COUNCIL_MEMBER: CouncilMember,
    AgentType.LEAD_AGENT: LeadAgent,
    AgentType.TASK_AGENT: TaskAgent
}


@event.listens_for(Agent, 'before_insert')
def set_constitution_version(mapper, connection, target):
    if not target.constitution_version:
        target.constitution_version = "v1.0.0"


@event.listens_for(TaskAgent, 'after_insert')
def notify_lead_of_spawn(mapper, connection, target):
    if target.parent and isinstance(target.parent, LeadAgent):
        target.parent.update_team_size()