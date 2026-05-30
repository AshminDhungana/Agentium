"""
Capability Registry for Agentium.
Defines and enforces tier-based capabilities with runtime permission checks.
"""

from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from sqlalchemy.orm import Session
from enum import Enum

from backend.models.entities.agents import Agent, AgentType
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory


class Capability(str, Enum):
    """All possible capabilities in the system."""
    
    # ═══════════════════════════════════════════════════════════
    # HEAD OF COUNCIL CAPABILITIES (0xxxx)
    # ═══════════════════════════════════════════════════════════
    VETO = "veto"                                    # Veto any decision
    AMEND_CONSTITUTION = "amend_constitution"        # Propose/approve amendments
    LIQUIDATE_ANY = "liquidate_any"                  # Terminate any agent
    ADMIN_VECTOR_DB = "admin_vector_db"              # Full ChromaDB admin access
    OVERRIDE_BUDGET = "override_budget"              # Override token/cost limits
    EMERGENCY_SHUTDOWN = "emergency_shutdown"        # System-wide emergency stop
    GRANT_CAPABILITY = "grant_capability"            # Grant capabilities to others
    REVOKE_CAPABILITY = "revoke_capability"          # Revoke capabilities from others
    
    # ═══════════════════════════════════════════════════════════
    # COUNCIL MEMBER CAPABILITIES (1xxxx)
    # ═══════════════════════════════════════════════════════════
    PROPOSE_AMENDMENT = "propose_amendment"          # Propose constitution changes
    ALLOCATE_RESOURCES = "allocate_resources"        # Allocate budget/tokens
    AUDIT_SYSTEM = "audit_system"                    # Access audit logs
    MODERATE_KNOWLEDGE = "moderate_knowledge"        # Curate knowledge base
    SPAWN_LEAD = "spawn_lead"                        # Create Lead Agents
    VOTE_ON_AMENDMENT = "vote_on_amendment"          # Vote on constitution changes
    REVIEW_VIOLATIONS = "review_violations"          # Review rule violations
    MANAGE_CHANNELS = "manage_channels"              # Configure external channels
    
    # ═══════════════════════════════════════════════════════════
    # LEAD AGENT CAPABILITIES (2xxxx)
    # ═══════════════════════════════════════════════════════════
    SPAWN_TASK_AGENT = "spawn_task_agent"            # Create Task Agents
    DELEGATE_WORK = "delegate_work"                  # Assign tasks to Task Agents
    REQUEST_RESOURCES = "request_resources"          # Request budget from Council
    SUBMIT_KNOWLEDGE = "submit_knowledge"            # Submit to knowledge base
    LIQUIDATE_TASK_AGENT = "liquidate_task_agent"    # Terminate Task Agents
    ESCALATE_TO_COUNCIL = "escalate_to_council"      # Escalate issues upward
    
    # ═══════════════════════════════════════════════════════════
    # TASK AGENT CAPABILITIES (3xxxx)
    # ═══════════════════════════════════════════════════════════
    EXECUTE_TASK = "execute_task"                    # Execute assigned tasks
    REPORT_STATUS = "report_status"                  # Report progress
    ESCALATE_BLOCKER = "escalate_blocker"            # Escalate blockers to Lead
    QUERY_KNOWLEDGE = "query_knowledge"              # Query knowledge base (read-only)
    USE_TOOLS = "use_tools"                          # Use approved tools
    REQUEST_CLARIFICATION = "request_clarification"  # Ask for task clarification


# ═══════════════════════════════════════════════════════════
# TIER-BASED CAPABILITY MAPPING
# ═══════════════════════════════════════════════════════════

TIER_CAPABILITIES: Dict[str, Set[Capability]] = {
    # HEAD OF COUNCIL (0xxxx) - Supreme authority
    "0": {
        Capability.VETO,
        Capability.AMEND_CONSTITUTION,
        Capability.LIQUIDATE_ANY,
        Capability.ADMIN_VECTOR_DB,
        Capability.OVERRIDE_BUDGET,
        Capability.EMERGENCY_SHUTDOWN,
        Capability.GRANT_CAPABILITY,
        Capability.REVOKE_CAPABILITY,
        # Inherits all lower tier capabilities
        Capability.PROPOSE_AMENDMENT,
        Capability.ALLOCATE_RESOURCES,
        Capability.AUDIT_SYSTEM,
        Capability.MODERATE_KNOWLEDGE,
        Capability.SPAWN_LEAD,
        Capability.VOTE_ON_AMENDMENT,
        Capability.REVIEW_VIOLATIONS,
        Capability.MANAGE_CHANNELS,
        Capability.SPAWN_TASK_AGENT,
        Capability.DELEGATE_WORK,
        Capability.REQUEST_RESOURCES,
        Capability.SUBMIT_KNOWLEDGE,
        Capability.LIQUIDATE_TASK_AGENT,
        Capability.ESCALATE_TO_COUNCIL,
        Capability.EXECUTE_TASK,
        Capability.REPORT_STATUS,
        Capability.ESCALATE_BLOCKER,
        Capability.QUERY_KNOWLEDGE,
        Capability.USE_TOOLS,
        Capability.REQUEST_CLARIFICATION,
    },
    
    # COUNCIL MEMBERS (1xxxx) - Governance & oversight
    "1": {
        Capability.PROPOSE_AMENDMENT,
        Capability.ALLOCATE_RESOURCES,
        Capability.AUDIT_SYSTEM,
        Capability.MODERATE_KNOWLEDGE,
        Capability.SPAWN_LEAD,
        Capability.VOTE_ON_AMENDMENT,
        Capability.REVIEW_VIOLATIONS,
        Capability.MANAGE_CHANNELS,
        # Inherits all Lead capabilities (Council supersedes Lead)
        Capability.SPAWN_TASK_AGENT,
        Capability.DELEGATE_WORK,
        Capability.LIQUIDATE_TASK_AGENT,
        Capability.REQUEST_RESOURCES,
        Capability.SUBMIT_KNOWLEDGE,
        Capability.ESCALATE_TO_COUNCIL,
        # Inherits Task capabilities
        Capability.EXECUTE_TASK,
        Capability.REPORT_STATUS,
        Capability.ESCALATE_BLOCKER,
        Capability.QUERY_KNOWLEDGE,
        Capability.USE_TOOLS,
        Capability.REQUEST_CLARIFICATION,
    },
    
    # LEAD AGENTS (2xxxx) - Middle management
    "2": {
        Capability.SPAWN_TASK_AGENT,
        Capability.DELEGATE_WORK,
        Capability.REQUEST_RESOURCES,
        Capability.SUBMIT_KNOWLEDGE,
        Capability.LIQUIDATE_TASK_AGENT,
        Capability.ESCALATE_TO_COUNCIL,
        # Inherits Task capabilities
        Capability.EXECUTE_TASK,
        Capability.REPORT_STATUS,
        Capability.ESCALATE_BLOCKER,
        Capability.QUERY_KNOWLEDGE,
        Capability.USE_TOOLS,
        Capability.REQUEST_CLARIFICATION,
    },
    
    # TASK AGENTS (3xxxx - 6xxxx) - Workers
    "3": {
        Capability.EXECUTE_TASK,
        Capability.REPORT_STATUS,
        Capability.ESCALATE_BLOCKER,
        Capability.QUERY_KNOWLEDGE,
        Capability.USE_TOOLS,
        Capability.REQUEST_CLARIFICATION,
    },
}

# Extend Task Agent capabilities
for t in ["4", "5", "6"]:
    TIER_CAPABILITIES[t] = TIER_CAPABILITIES["3"].copy()

# Critic capabilities (7, 8, 9)
for t in ["7", "8", "9"]:
    TIER_CAPABILITIES[t] = {
        Capability.VETO,
        Capability.REPORT_STATUS,
        Capability.QUERY_KNOWLEDGE,
    }


class CapabilityRegistry:
    """
    Centralized capability management system.
    Enforces tier-based permissions and tracks capability changes.
    """
    
    @staticmethod
    def get_agent_tier(agentium_id: str) -> str:
        """Extract tier from agentium_id (first digit)."""
        if not agentium_id or len(agentium_id) < 5:
            raise ValueError(f"Invalid agentium_id: {agentium_id}")
        return agentium_id[0]
    
    @staticmethod
    def get_base_capabilities(agentium_id: str) -> Set[Capability]:
        """Get base capabilities for an agent based on tier."""
        tier = CapabilityRegistry.get_agent_tier(agentium_id)
        return TIER_CAPABILITIES.get(tier, set()).copy()
    
    @staticmethod
    def can_agent(
        agent: Agent,
        capability: Capability,
        db: Session,
        raise_on_deny: bool = False
    ) -> bool:
        """
        Check if agent has permission for a capability.
        
        Args:
            agent: Agent to check
            capability: Capability to verify
            db: Database session
            raise_on_deny: If True, raise exception instead of returning False
            
        Returns:
            True if agent has capability, False otherwise
            
        Raises:
            PermissionError: If raise_on_deny=True and permission denied
        """
        # Get agent's base capabilities from tier
        base_caps = CapabilityRegistry.get_base_capabilities(agent.agentium_id)
        
        # Check if capability is in base set
        has_capability = capability in base_caps
        
        # Check for dynamically granted capabilities (stored in agent.custom_capabilities)
        if hasattr(agent, 'custom_capabilities') and agent.custom_capabilities:
            import json
            try:
                custom_caps = json.loads(agent.custom_capabilities)
                if capability.value in custom_caps.get('granted', []):
                    has_capability = True
                elif capability.value in custom_caps.get('revoked', []):
                    has_capability = False
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Raise exception if denied and requested
        if not has_capability and raise_on_deny:
            raise PermissionError(
                f"Agent {agent.agentium_id} lacks capability: {capability.value}. "
                f"Required tier: {CapabilityRegistry._get_required_tier(capability)}"
            )
        
        # Log capability check (for audit trail)
        if not has_capability:
            AuditLog.log(
                level=AuditLevel.WARNING,
                category=AuditCategory.GOVERNANCE,
                actor_type="agent",
                actor_id=agent.agentium_id,
                action="capability_denied",
                description=f"Agent attempted action without permission: {capability.value}",
                success=False,
                meta_data={
                    "capability": capability.value,
                    "agent_tier": CapabilityRegistry.get_agent_tier(agent.agentium_id)
                }
            )
        
        return has_capability
    
    @staticmethod
    def _get_required_tier(capability: Capability) -> str:
        """Get minimum tier required for a capability."""
        for tier, caps in TIER_CAPABILITIES.items():
            if capability in caps:
                return tier
        return "unknown"
    
    @staticmethod
    def grant_capability(
        agent: Agent,
        capability: Capability,
        granted_by: Agent,
        reason: str,
        db: Session
    ) -> bool:
        """
        Dynamically grant a capability to an agent.
        Requires granter to have GRANT_CAPABILITY permission.
        
        Args:
            agent: Agent to grant capability to
            capability: Capability to grant
            granted_by: Agent granting the capability
            reason: Justification for grant
            db: Database session
            
        Returns:
            True if granted successfully
            
        Raises:
            PermissionError: If granter lacks GRANT_CAPABILITY
        """
        # Check if granter has permission to grant capabilities
        if not CapabilityRegistry.can_agent(granted_by, Capability.GRANT_CAPABILITY, db):
            raise PermissionError(
                f"Agent {granted_by.agentium_id} cannot grant capabilities "
                "(requires GRANT_CAPABILITY)"
            )
        
        # Initialize custom_capabilities if not exists
        import json
        if not hasattr(agent, 'custom_capabilities') or not agent.custom_capabilities:
            agent.custom_capabilities = json.dumps({'granted': [], 'revoked': []})
        
        custom_caps = json.loads(agent.custom_capabilities)
        
        # Add to granted list
        if capability.value not in custom_caps['granted']:
            custom_caps['granted'].append(capability.value)
        
        # Remove from revoked list if present
        if capability.value in custom_caps.get('revoked', []):
            custom_caps['revoked'].remove(capability.value)
        
        agent.custom_capabilities = json.dumps(custom_caps)
        db.flush()
        
        # Log the grant
        AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=granted_by.agentium_id,
            action="capability_granted",
            target_type="agent",
            target_id=agent.agentium_id,
            description=f"Granted {capability.value} to {agent.agentium_id}. Reason: {reason}",
            meta_data={
                "capability": capability.value,
                "reason": reason,
                "granted_by": granted_by.agentium_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        print(f"✅ Capability granted: {agent.agentium_id} → {capability.value}")
        return True
    
    @staticmethod
    def revoke_capability(
        agent: Agent,
        capability: Capability,
        revoked_by: Agent,
        reason: str,
        db: Session
    ) -> bool:
        """
        Revoke a capability from an agent.
        Requires revoker to have REVOKE_CAPABILITY permission.
        
        Args:
            agent: Agent to revoke capability from
            capability: Capability to revoke
            revoked_by: Agent revoking the capability
            reason: Justification for revocation
            db: Database session
            
        Returns:
            True if revoked successfully
            
        Raises:
            PermissionError: If revoker lacks REVOKE_CAPABILITY
        """
        # Check if revoker has permission
        if not CapabilityRegistry.can_agent(revoked_by, Capability.REVOKE_CAPABILITY, db):
            raise PermissionError(
                f"Agent {revoked_by.agentium_id} cannot revoke capabilities "
                "(requires REVOKE_CAPABILITY)"
            )
        
        # Initialize custom_capabilities if not exists
        import json
        if not hasattr(agent, 'custom_capabilities') or not agent.custom_capabilities:
            agent.custom_capabilities = json.dumps({'granted': [], 'revoked': []})
        
        custom_caps = json.loads(agent.custom_capabilities)
        
        # Add to revoked list
        if capability.value not in custom_caps.get('revoked', []):
            if 'revoked' not in custom_caps:
                custom_caps['revoked'] = []
            custom_caps['revoked'].append(capability.value)
        
        # Remove from granted list if present
        if capability.value in custom_caps.get('granted', []):
            custom_caps['granted'].remove(capability.value)
        
        agent.custom_capabilities = json.dumps(custom_caps)
        db.flush()
        
        # Log the revocation
        AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.GOVERNANCE,
            actor_type="agent",
            actor_id=revoked_by.agentium_id,
            action="capability_revoked",
            target_type="agent",
            target_id=agent.agentium_id,
            description=f"Revoked {capability.value} from {agent.agentium_id}. Reason: {reason}",
            meta_data={
                "capability": capability.value,
                "reason": reason,
                "revoked_by": revoked_by.agentium_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        print(f"⚠️ Capability revoked: {agent.agentium_id} ✗ {capability.value}")
        return True
    
    @staticmethod
    def get_agent_capabilities(agent: Agent) -> Dict[str, Any]:
        """
        Get complete capability profile for an agent.
        
        Returns:
            {
                "tier": "0",
                "base_capabilities": [...],
                "granted_capabilities": [...],
                "revoked_capabilities": [...],
                "effective_capabilities": [...]
            }
        """
        import json
        
        tier = CapabilityRegistry.get_agent_tier(agent.agentium_id)
        base_caps = CapabilityRegistry.get_base_capabilities(agent.agentium_id)
        
        granted = []
        revoked = []
        
        if hasattr(agent, 'custom_capabilities') and agent.custom_capabilities:
            try:
                custom_caps = json.loads(agent.custom_capabilities)
                granted = custom_caps.get('granted', [])
                revoked = custom_caps.get('revoked', [])
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Calculate effective capabilities
        effective = set([cap.value for cap in base_caps])
        effective.update(granted)
        effective.difference_update(revoked)
        
        return {
            "tier": tier,
            "agentium_id": agent.agentium_id,
            "base_capabilities": sorted([cap.value for cap in base_caps]),
            "granted_capabilities": sorted(granted),
            "revoked_capabilities": sorted(revoked),
            "effective_capabilities": sorted(list(effective)),
            "total_count": len(effective)
        }
    
    @staticmethod
    def revoke_all_capabilities(agent: Agent, reason: str, db: Session):
        """
        Revoke ALL capabilities from an agent (used during liquidation).
        
        Args:
            agent: Agent to revoke all capabilities from
            reason: Reason for revocation (e.g., "agent_liquidated")
            db: Database session
        """
        import json
        
        # Get all effective capabilities
        base_caps = CapabilityRegistry.get_base_capabilities(agent.agentium_id)
        
        # Mark all as revoked
        revoked_list = [cap.value for cap in base_caps]
        
        agent.custom_capabilities = json.dumps({
            'granted': [],
            'revoked': revoked_list
        })
        db.flush()
        
        # Log mass revocation
        AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.GOVERNANCE,
            actor_type="system",
            actor_id="CAPABILITY_REGISTRY",
            action="all_capabilities_revoked",
            target_type="agent",
            target_id=agent.agentium_id,
            description=f"All capabilities revoked from {agent.agentium_id}. Reason: {reason}",
            meta_data={
                "capabilities_revoked": revoked_list,
                "count": len(revoked_list),
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        print(f"🔒 All capabilities revoked: {agent.agentium_id} ({len(revoked_list)} capabilities)")
    
    @staticmethod
    def capability_audit_report(db: Session) -> Dict[str, Any]:
        """
        Generate system-wide capability audit report.
        
        Returns:
            Statistics on capability distribution and usage
        """
        from sqlalchemy import func
        
        # Get all active agents
        agents = db.query(Agent).filter_by(is_active=True).all()
        
        tier_distribution = {str(i): 0 for i in range(10)}
        dynamic_grants = 0
        dynamic_revocations = 0
        
        for agent in agents:
            tier = CapabilityRegistry.get_agent_tier(agent.agentium_id)
            tier_distribution[tier] = tier_distribution.get(tier, 0) + 1
            
            if hasattr(agent, 'custom_capabilities') and agent.custom_capabilities:
                import json
                try:
                    custom = json.loads(agent.custom_capabilities)
                    dynamic_grants += len(custom.get('granted', []))
                    dynamic_revocations += len(custom.get('revoked', []))
                except:
                    pass
        
        # Get recent capability changes from audit log
        recent_changes = db.query(AuditLog).filter(
            AuditLog.action.in_([
                'capability_granted',
                'capability_revoked',
                'all_capabilities_revoked'
            ])
        ).order_by(AuditLog.created_at.desc()).limit(10).all()
        
        return {
            "total_agents": len(agents),
            "tier_distribution": tier_distribution,
            "dynamic_grants_total": dynamic_grants,
            "dynamic_revocations_total": dynamic_revocations,
            "recent_capability_changes": [
                {
                    "action": log.action,
                    "actor": log.actor_id,
                    "target": log.target_id,
                    "timestamp": log.created_at.isoformat(),
                    "description": log.description
                }
                for log in recent_changes
            ]
        }


# ═══════════════════════════════════════════════════════════
# DECORATOR FOR CAPABILITY ENFORCEMENT
# ═══════════════════════════════════════════════════════════

def require_capability(capability: Capability):
    """
    Decorator to enforce capability requirements on agent methods.
    
    Usage:
        @require_capability(Capability.SPAWN_TASK_AGENT)
        async def create_task_agent(agent: Agent, db: Session, ...):
            # Method implementation
    """
    def decorator(func):
        async def wrapper(agent: Agent, db: Session, *args, **kwargs):
            # Check capability
            if not CapabilityRegistry.can_agent(agent, capability, db):
                raise PermissionError(
                    f"Agent {agent.agentium_id} lacks required capability: {capability.value}"
                )
            
            # Execute original function
            return await func(agent, db, *args, **kwargs)
        
        return wrapper
    return decorator


# Singleton instance
capability_registry = CapabilityRegistry()