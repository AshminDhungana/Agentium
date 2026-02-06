from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.models.schemas.tool_creation import ToolCreationRequest, ToolApprovalRequest
from backend.services.tool_creation_service import ToolCreationService
from backend.models.database import get_db

router = APIRouter(prefix="/tools/create", tags=["Tool Creation"])

@router.post("/propose")
async def propose_tool(
    request: ToolCreationRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Propose creation of a new tool.
    Head of Council: Auto-approves
    Council Members: Requires voting
    Lead Agents: Requires Head approval
    """
    service = ToolCreationService(db)
    
    # Verify proposing agent exists and is active
    agent = db.query(Agent).filter_by(agentium_id=request.created_by_agentium_id, status='active').first()
    if not agent:
        raise HTTPException(status_code=404, detail="Proposing agent not found or inactive")
    
    result = service.propose_tool(request)
    return result

@router.post("/vote")
async def vote_on_tool(
    tool_name: str,
    vote: str,  # "for", "against", "abstain"
    voter_agentium_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Cast vote on tool creation proposal."""
    service = ToolCreationService(db)
    
    # Verify voter is council member
    voter = db.query(Agent).filter_by(agentium_id=voter_agentium_id, agent_type='council_member', status='active').first()
    if not voter:
        raise HTTPException(status_code=403, detail="Only active council members can vote")
    
    result = service.vote_on_tool(tool_name, voter_agentium_id, vote)
    return result

@router.post("/activate")
async def activate_tool(
    tool_name: str,
    approved_by_agentium_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Manually activate a tool (Head of Council only)."""
    service = ToolCreationService(db)
    
    # Verify Head of Council
    head = db.query(Agent).filter_by(agentium_id=approved_by_agentium_id, agent_type='head_of_council', status='active').first()
    if not head:
        raise HTTPException(status_code=403, detail="Only Head of Council can manually activate tools")
    
    # Find staging entry
    staging_entry = db.query(ToolStaging).filter_by(tool_name=tool_name, status='approved').first()
    if not staging_entry:
        raise HTTPException(status_code=404, detail="No approved tool found with this name")
    
    result = service.activate_tool(tool_name, staging_entry.id)
    return result

@router.get("/staging")
async def list_staged_tools(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all tools pending approval or activation."""
    staging_entries = db.query(ToolStaging).filter(
        ToolStaging.status.in_(['pending_approval', 'approved'])
    ).all()
    
    return {
        "count": len(staging_entries),
        "tools": [
            {
                "tool_name": s.tool_name,
                "proposed_by": s.proposed_by_agentium_id,
                "status": s.status,
                "requires_vote": s.requires_vote,
                "created_at": s.created_at.isoformat(),
                "voting_id": s.voting_id
            }
            for s in staging_entries
        ]
    }