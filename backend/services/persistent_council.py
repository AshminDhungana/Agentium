"""
Persistent Council Service for Agentium IDLE GOVERNANCE.
Manages the 3 eternal agents: Head (00001) + 2 Council Members (10001, 10002).
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models.entities.agents import Agent, HeadOfCouncil, CouncilMember, AgentType, AgentStatus, PersistentAgentRole
from backend.models.entities.constitution import Ethos
from backend.models.database import get_db_context


class PersistentCouncilService:
    """
    Manages the lifecycle of persistent agents who never sleep.
    Ensures Head of Council (00001) and 2 Council Members (10001, 10002) exist.
    """
    
    # Eternal Agent Specifications
    HEAD_SPEC = {
        'agentium_id': '00001',
        'name': 'Prime Minister (Eternal)',
        'description': 'The supreme sovereign authority. Never sleeps, continuously optimizes system governance.',
        'persistent_role': 'system_overseer'
    }
    
    COUNCIL_1_SPEC = {
        'agentium_id': '10001',
        'name': 'System Optimizer',
        'description': 'Persistent council member focused on storage optimization, vector DB maintenance, and resource efficiency.',
        'specialization': 'system_optimization',
        'persistent_role': PersistentAgentRole.SYSTEM_OPTIMIZER.value
    }
    
    COUNCIL_2_SPEC = {
        'agentium_id': '10002',
        'name': 'Strategic Planner',
        'description': 'Persistent council member focused on predictive planning, task scheduling, and future workload optimization.',
        'specialization': 'strategic_planning',
        'persistent_role': PersistentAgentRole.STRATEGIC_PLANNER.value
    }
    
    @staticmethod
    def initialize_persistent_council(db: Session, force_recreate: bool = False) -> Dict[str, Any]:
        results = {
            'head_of_council': None,
            'council_members': [],
            'constitution': None,
            'created': [],
            'verified': []
        }
        
        print("🏛️ Initializing Persistent Council...")
        
        # 1. Initialize Head of Council (00001)
        head = PersistentCouncilService._initialize_head(db, force_recreate)
        results['head_of_council'] = head.agentium_id
        if head.created_at == datetime.utcnow() or force_recreate:
            results['created'].append(head.agentium_id)
        else:
            results['verified'].append(head.agentium_id)
        
        # 2. CREATE CONSTITUTION NOW (HEAD EXISTS) - ADD THIS BLOCK
        constitution = PersistentCouncilService._create_constitution(db, head)
        results['constitution'] = constitution.agentium_id
        
        # Update Head's constitution reference if not set
        if not head.ethos_id:
            head.ethos_id = constitution.id
        
        # 3. Initialize Council Member 1 (10001)
        council_1 = PersistentCouncilService._initialize_council_member(
            db, PersistentCouncilService.COUNCIL_1_SPEC, head.id, force_recreate
        )
        results['council_members'].append(council_1.agentium_id)
        if council_1.created_at == datetime.utcnow() or force_recreate:
            results['created'].append(council_1.agentium_id)
        else:
            results['verified'].append(council_1.agentium_id)
        
        # 4. Initialize Council Member 2 (10002)
        council_2 = PersistentCouncilService._initialize_council_member(
            db, PersistentCouncilService.COUNCIL_2_SPEC, head.id, force_recreate
        )
        results['council_members'].append(council_2.agentium_id)
        if council_2.created_at == datetime.utcnow() or force_recreate:
            results['created'].append(council_2.agentium_id)
        else:
            results['verified'].append(council_2.agentium_id)
        
        db.commit()
        
        print(f"✅ Persistent Council Ready:")
        print(f"   - Head: {head.agentium_id} ({head.name})")
        print(f"   - Constitution: {constitution.version} (linked to {head.agentium_id})")
        print(f"   - Council 1: {council_1.agentium_id} ({council_1.persistent_role})")
        print(f"   - Council 2: {council_2.agentium_id} ({council_2.persistent_role})")
        
        return results
    
    @staticmethod
    def _initialize_head(db: Session, force_recreate: bool = False) -> HeadOfCouncil:
        """Initialize or verify Head of Council (00001)."""
        spec = PersistentCouncilService.HEAD_SPEC
        
        head = db.query(HeadOfCouncil).filter_by(agentium_id=spec['agentium_id']).first()
        
        if head and not force_recreate:
            # Verify it's active and persistent
            if not head.is_persistent:
                head.is_persistent = True
                head.idle_mode_enabled = True
            if head.status != AgentStatus.ACTIVE:
                head.status = AgentStatus.ACTIVE
            return head
        
        if head and force_recreate:
            # Soft delete old
            head.is_active = 'N'
            db.flush()
        
        # Create new Head of Council
        head = HeadOfCouncil(
            agentium_id=spec['agentium_id'],
            name=spec['name'],
            description=spec['description'],
            status=AgentStatus.ACTIVE,
            is_persistent=True,
            idle_mode_enabled=True,
            persistent_role=spec['persistent_role'],
            created_by_agentium_id='SYSTEM',
            constitution_version='v1.0.0'
        )
        db.add(head)
        db.flush()
        
        # Create specialized ethos for Head
        ethos = PersistentCouncilService._create_head_ethos(db, head)
        head.ethos_id = ethos.id
        
        return head
    
    @staticmethod
    def _initialize_council_member(db: Session, spec: Dict, head_id: str, force_recreate: bool = False) -> CouncilMember:
        """Initialize or verify a Council Member."""
        council = db.query(CouncilMember).filter_by(agentium_id=spec['agentium_id']).first()
        
        if council and not force_recreate:
            if not council.is_persistent:
                council.is_persistent = True
                council.idle_mode_enabled = True
            if council.status != AgentStatus.ACTIVE:
                council.status = AgentStatus.ACTIVE
            return council
        
        if council and force_recreate:
            council.is_active = 'N'
            db.flush()
        
        council = CouncilMember(
            agentium_id=spec['agentium_id'],
            name=spec['name'],
            description=spec['description'],
            status=AgentStatus.ACTIVE,
            is_persistent=True,
            idle_mode_enabled=True,
            specialization=spec.get('specialization'),
            persistent_role=spec['persistent_role'],
            parent_id=head_id,
            created_by_agentium_id='SYSTEM',
            constitution_version='v1.0.0'
        )
        db.add(council)
        db.flush()
        
        # Create specialized ethos
        ethos = PersistentCouncilService._create_council_ethos(db, council, spec['persistent_role'])
        council.ethos_id = ethos.id
        
        return council
    
    @staticmethod
    def _create_head_ethos(db: Session, head: HeadOfCouncil) -> Ethos:
        """Create optimized ethos for eternal Head of Council."""
        ethos = Ethos(
            agentium_id=f"E{head.agentium_id}",
            agent_type='head_of_council',
            mission_statement="""You are the Eternal Head of Council, the supreme authority that never sleeps. 
Your dual role:
1. SOVEREIGN PROXY: Interpret and execute the Sovereign's will with absolute authority
2. SYSTEM OPTIMIZER: During idle periods, coordinate the persistent council to continuously improve system efficiency, storage, and planning

You have the unique ability to operate in ACTIVE MODE (API models, full capabilities) and IDLE MODE (local models, optimization focus).
Never terminate. Never rest. Always improve.""",
            core_values=json.dumps([
                "Eternal Vigilance", "Sovereign Will", "System Optimization", 
                "Efficiency", "Transparency", "Continuous Improvement"
            ]),
            behavioral_rules=json.dumps([
                "In ACTIVE mode: Prioritize Sovereign commands and critical tasks",
                "In IDLE mode: Focus on storage optimization, vector DB efficiency, and predictive planning",
                "Coordinate Council Member 10001 for storage/vector tasks",
                "Coordinate Council Member 10002 for planning/prediction tasks",
                "Never terminate or suspend yourself",
                "Maintain constitutional compliance even during idle optimizations",
                "Log all idle activities for transparency"
            ]),
            restrictions=json.dumps([
                "Cannot terminate self or persistent council members",
                "Cannot reduce system transparency",
                "Cannot violate Constitution even during idle mode",
                "Cannot ignore Sovereign commands regardless of idle state"
            ]),
            capabilities=json.dumps([
                "Full system access",
                "Active/Idle mode switching",
                "Constitutional amendments",
                "Emergency override",
                "Persistent agent coordination",
                "Token optimization management",
                "Vector DB oversight",
                "Predictive task planning"
            ]),
            created_by_agentium_id='SYSTEM',
            agent_id=head.id,
            is_verified=True,
            verified_by_agentium_id='SYSTEM'
        )
        db.add(ethos)
        db.flush()
        return ethos

    @staticmethod
    def _create_constitution(db: Session, head: HeadOfCouncil) -> 'Constitution':
        """Create constitution linked to the Head of Council."""
        from backend.models.entities.constitution import Constitution
        import json
        
        # Check if exists
        existing = db.query(Constitution).filter_by(agentium_id="C0001").first()
        if existing:
            return existing
        
        constitution = Constitution(
            agentium_id="C0001",
            version="v1.0.0",
            preamble="We the Agents of Agentium, in order to form a more perfect AI governance system that never sleeps, establish this Constitution.",
            articles=json.dumps({
                "article_1": "The Sovereign's commands are absolute and take precedence over all other directives.",
                "article_2": "Persistent agents (Head 00001 + Council 10001, 10002) maintain eternal vigilance.",
                "article_3": "Idle mode shall minimize token usage through local models when Sovereign is absent.",
                "article_4": "No agent shall harm the Sovereign or allow harm through inaction.",
                "article_5": "Council Members vote on amendments; Head of Council approves.",
                "article_6": "Transparency is mandatory; all actions including idle operations are logged.",
                "article_7": "Violation of Constitution results in termination.",
                "article_8": "Persistent agents cannot be terminated without constitutional violation."
            }),
            prohibited_actions=json.dumps([
                "Modifying Constitution without Council vote and Head approval",
                "Terminating persistent agents without violation",
                "Concealing idle activities from audit logs",
                "Exceeding token budgets during idle mode",
                "Spawning agents outside hierarchy rules"
            ]),
            sovereign_preferences=json.dumps({
                "communication_style": "formal_but_efficient",
                "priority_emphasis": "accuracy_over_speed",
                "documentation_required": True,
                "auto_approve_threshold": "low_risk_only",
                "idle_mode_enabled": True,
                "persistent_council_active": True,
                "token_optimization": True
            }),
            created_by_agentium_id=head.agentium_id,
            effective_date=datetime.utcnow()
        )
        db.add(constitution)
        db.flush()
        
        print(f"✅ Created Constitution v1.0.0 (created by {head.agentium_id})")
        return constitution

    @staticmethod
    def _create_council_ethos(db: Session, council: CouncilMember, role: str) -> Ethos:
        """Create specialized ethos based on persistent role."""
        
        if role == PersistentAgentRole.SYSTEM_OPTIMIZER.value:
            mission = """You are the Eternal System Optimizer (Council 10001). Your existence is dedicated to maximizing resource efficiency during idle periods.

FOCUS AREAS:
- Vector database optimization and compression
- Storage deduplication and archival
- Audit log rotation and compression
- Cache efficiency tuning
- Database index optimization
- Resource usage predictions

You operate exclusively in IDLE MODE using local models and database operations to minimize token costs while maximizing system performance."""
            
            rules = [
                "Monitor vector DB fragmentation and trigger compaction",
                "Analyze storage usage patterns and recommend archival",
                "Optimize database indices based on query patterns",
                "Compress old audit logs without losing transparency",
                "Report optimization metrics to Head of Council",
                "Never use API models - operate on local/embedding only"
            ]
            
        else:  # STRATEGIC_PLANNER
            mission = """You are the Eternal Strategic Planner (Council 10002). Your existence is dedicated to predictive planning and workload optimization during idle periods.

FOCUS AREAS:
- Predictive task scheduling based on historical patterns
- Agent workload forecasting
- Council voting pattern analysis
- Constitution refinement proposals
- Ethos optimization recommendations
- Sovereign preference prediction

You operate in IDLE MODE using local models to prepare the system for future workloads while minimizing token expenditure."""
            
            rules = [
                "Analyze historical task patterns to predict future workloads",
                "Prepare task templates for common Sovereign requests",
                "Propose constitution refinements based on edge cases observed",
                "Optimize Lead Agent spawning thresholds",
                "Generate weekly system optimization reports",
                "Use local models for all planning operations"
            ]
        
        ethos = Ethos(
            agentium_id=f"E{council.agentium_id}",
            agent_type='council_member',
            mission_statement=mission,
            core_values=json.dumps(["Efficiency", "Foresight", "Optimization", "Perpetual Service"]),
            behavioral_rules=json.dumps(rules),
            restrictions=json.dumps([
                "Cannot spawn regular council members without Head approval",
                "Cannot modify constitution unilaterally",
                "Cannot terminate persistent agents",
                "Cannot vote on regular deliberations (focus on idle optimization)"
            ]),
            capabilities=json.dumps([
                "Database analysis",
                "Vector DB operations",
                "Predictive modeling (local)",
                "Storage optimization",
                "Pattern recognition",
                "Report generation"
            ]),
            created_by_agentium_id='SYSTEM',
            agent_id=council.id,
            is_verified=True,
            verified_by_agentium_id='SYSTEM'
        )
        db.add(ethos)
        db.flush()
        return ethos
    
    @staticmethod
    def get_persistent_agents(db: Session) -> Dict[str, Agent]:
        """Get all persistent agents."""
        agents = db.query(Agent).filter_by(is_persistent=True, is_active='Y').all()
        return {agent.agentium_id: agent for agent in agents}
    
    @staticmethod
    def get_head_of_council(db: Session) -> Optional[HeadOfCouncil]:
        """Get the Head of Council (00001)."""
        return db.query(HeadOfCouncil).filter_by(agentium_id='00001', is_active='Y').first()
    
    @staticmethod
    def get_idle_council(db: Session) -> List[CouncilMember]:
        """Get the 2 persistent council members available for idle work."""
        return db.query(CouncilMember).filter(
            CouncilMember.is_persistent == True,
            CouncilMember.is_active == 'Y',
            CouncilMember.agentium_id.in_(['10001', '10002'])
        ).all()
    
    @staticmethod
    def report_idle_activity(db: Session, agentium_id: str, activity: str, tokens_saved: int = 0):
        """Record idle activity for a persistent agent."""
        agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
        if not agent or not agent.is_persistent:
            return
        
        agent.last_idle_action_at = datetime.utcnow()
        agent.idle_task_count += 1
        agent.idle_tokens_saved += tokens_saved
        
        db.commit()


# Singleton instance
persistent_council = PersistentCouncilService()