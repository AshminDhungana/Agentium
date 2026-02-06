from sqlalchemy.orm import Session
from backend.models.schemas.tool_creation import ToolCreationRequest, ToolApprovalRequest
from backend.models.entities.voting import AmendmentVoting, AmendmentStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.tool_factory import ToolFactory
from backend.core.tool_registry import tool_registry
from backend.models.entities.agents import Agent
from typing import Dict, Any, List, Optional
from datetime import datetime

class ToolCreationService:
    """
    Service layer for agent-initiated tool creation with democratic approval.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.factory = ToolFactory()
    
    def propose_tool(self, request: ToolCreationRequest) -> Dict[str, Any]:
        """
        Agent proposes a new tool creation.
        Returns approval workflow status.
        """
        # Validate code
        validation = self.factory.validate_tool_code(request.code_template)
        if not validation["valid"]:
            return {"proposed": False, "error": validation["error"]}
        
        # Check authorization
        if request.created_by_agentium_id.startswith('3'):  # Task agent - No permission
            return {"proposed": False, "error": "Task agents cannot create tools"}
        
        # Generate tool file (staged, not activated)
        tool_path = self.factory.generate_tool_file(request)
        
        # Determine if voting is required
        requires_vote = not request.created_by_agentium_id.startswith('0')  # Non-Head agents need vote
        
        # Create approval record
        approval_record = {
            "tool_name": request.tool_name,
            "proposed_by": request.created_by_agentium_id,
            "tool_path": str(tool_path),
            "status": "pending_approval" if requires_vote else "approved",
            "requires_vote": requires_vote,
            "request_data": request.dict(),
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Save to database (create a simple staging table or use JSON field)
        staging_entry = ToolStaging(
            tool_name=request.tool_name,
            proposed_by_agentium_id=request.created_by_agentium_id,
            tool_path=str(tool_path),
            request_json=request.json(),
            requires_vote=requires_vote,
            status="pending_approval" if requires_vote else "approved"
        )
        self.db.add(staging_entry)
        self.db.commit()
        
        # If requires vote, create voting session
        if requires_vote:
            # Get active council members
            council = self.db.query(Agent).filter(
                Agent.agent_type == "council_member",
                Agent.status == "active"
            ).all()
            
            from backend.services.persistent_council import persistent_council
            
            voting = AmendmentVoting(
                constitution_id=None,  # This is for tool creation, not constitution
                proposed_by_agentium_id=request.created_by_agentium_id,
                proposed_changes=f"Tool Creation: {request.tool_name}",
                rationale=request.rationale,
                status=AmendmentStatus.PROPOSED,
                votes_required=len(council),
            )
            self.db.add(voting)
            self.db.commit()
            
            return {
                "proposed": True,
                "tool_name": request.tool_name,
                "status": "pending_vote",
                "voting_id": voting.id,
                "requires_council_approval": True,
                "council_members": [c.agentium_id for c in council]
            }
        
        # If Head of Council, auto-approve and activate
        if request.created_by_agentium_id.startswith('0'):
            activation = self.activate_tool(request.tool_name, staging_entry.id)
            return {
                "proposed": True,
                "tool_name": request.tool_name,
                "status": "activated",
                "activated": activation["success"],
                "error": activation.get("error")
            }
        
        return approval_record
    
    def vote_on_tool(self, tool_name: str, voter_agentium_id: str, vote: str) -> Dict[str, Any]:
        """Council member votes on tool creation proposal."""
        # Find the voting session
        voting = self.db.query(AmendmentVoting).filter(
            AmendmentVoting.proposed_changes.like(f"%Tool Creation: {tool_name}%"),
            AmendmentVoting.status.in_([AmendmentStatus.PROPOSED, AmendmentStatus.VOTING])
        ).first()
        
        if not voting:
            return {"voted": False, "error": "Voting session not found"}
        
        # Cast vote
        voting.cast_vote(vote, voter_agentium_id)
        self.db.commit()
        
        # Check if voting is complete
        if voting.check_quorum():
            voting.finalize_voting()
            self.db.commit()
            
            # If approved, activate tool
            if voting.status == AmendmentStatus.APPROVED:
                staging_entry = self.db.query(ToolStaging).filter(
                    ToolStaging.tool_name == tool_name
                ).first()
                
                if staging_entry:
                    activation = self.activate_tool(tool_name, staging_entry.id)
                    return {
                        "voted": True,
                        "tool_name": tool_name,
                        "voting_complete": True,
                        "approved": True,
                        "activated": activation["success"]
                    }
        
        return {
            "voted": True,
            "tool_name": tool_name,
            "voting_complete": False,
            "current_votes": {
                "for": voting.votes_for,
                "against": voting.votes_against,
                "abstain": voting.votes_abstain
            }
        }
    
    def activate_tool(self, tool_name: str, staging_id: int) -> Dict[str, Any]:
        """Activate a staged tool and register it."""
        staging_entry = self.db.query(ToolStaging).filter(
            ToolStaging.id == staging_id,
            ToolStaging.tool_name == tool_name
        ).first()
        
        if not staging_entry:
            return {"activated": False, "error": "Tool staging record not found"}
        
        # Load request data
        request = ToolCreationRequest(**staging_entry.request_json)
        
        # Run tests
        if request.test_cases:
            test_result = self.factory.run_tests(tool_name, request.test_cases)
            if not test_result["passed"]:
                return {
                    "activated": False,
                    "error": "Tests failed",
                    "test_results": test_result
                }
        
        # Load the tool
        load_result = self.factory.load_tool(tool_name)
        if not load_result["loaded"]:
            return {"activated": False, "error": load_result["error"]}
        
        # Register in tool registry
        tool_registry.register_tool(
            name=tool_name,
            description=request.description,
            function=load_result["tool_instance"].execute,
            parameters={p.name: {"type": p.type, "description": p.description} 
                       for p in request.parameters},
            authorized_tiers=request.authorized_tiers
        )
        
        # Update staging status
        staging_entry.status = "activated"
        staging_entry.activated_at = datetime.utcnow()
        self.db.commit()
        
        # Log activation
        self._log_tool_activation(request.created_by_agentium_id, tool_name)
        
        return {
            "activated": True,
            "tool_name": tool_name,
            "authorized_tiers": request.authorized_tiers,
            "test_results": test_result if request.test_cases else None
        }
    
    def _log_tool_activation(self, agentium_id: str, tool_name: str):
        """Log tool activation in audit trail."""
        audit = AuditLog(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type='agent',
            actor_id=agentium_id,
            action="tool_activated",
            target_type='tool',
            target_id=tool_name,
            description=f"Tool '{tool_name}' activated and registered",
            after_state={
                "tool_name": tool_name,
                "activated_by": agentium_id,
                "timestamp": datetime.utcnow().isoformat()
            },
            is_active='Y',
            created_at=datetime.utcnow()
        )
        self.db.add(audit)
        self.db.commit()


# Database model for staging (add this to models/entities/base.py or create new file)
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime
from backend.models.entities.base import BaseEntity

class ToolStaging(BaseEntity):
    """Staging table for proposed tools pending approval."""
    __tablename__ = 'tool_staging'
    
    tool_name = Column(String(100), unique=True, nullable=False)
    proposed_by_agentium_id = Column(String(10), nullable=False)
    tool_path = Column(String(500), nullable=False)
    request_json = Column(Text, nullable=False)  # Store full request as JSON
    requires_vote = Column(Boolean, default=True)
    status = Column(String(50), default='pending_approval')  # pending_approval, approved, activated, rejected
    voting_id = Column(String(36), nullable=True)
    activated_at = Column(DateTime, nullable=True)