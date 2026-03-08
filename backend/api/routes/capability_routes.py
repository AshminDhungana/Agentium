"""
API routes for Capability Management.
Provides endpoints for capability inspection, granting, and revocation.

Changes vs previous version:
  - Added POST /validate-reassignment endpoint used by the drag-and-drop
    reassignment flow in the frontend to check if an agent can be moved
    under a new parent based on tier hierarchy and capability rules.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.agents import Agent
from backend.services.capability_registry import (
    CapabilityRegistry,
    Capability,
    capability_registry
)
from backend.core.auth import get_current_active_user

router = APIRouter(prefix="/api/v1/capabilities", tags=["Capabilities"])


# ═══════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════

class CapabilityCheckRequest(BaseModel):
    agentium_id: str = Field(..., description="Agent ID to check")
    capability:  str = Field(..., description="Capability name to verify")


class CapabilityCheckResponse(BaseModel):
    has_capability: bool
    agentium_id:    str
    capability:     str
    tier:           str
    reason:         Optional[str] = None


class GrantCapabilityRequest(BaseModel):
    target_agentium_id: str = Field(..., description="Agent to grant capability to")
    capability:         str = Field(..., description="Capability to grant")
    reason:             str = Field(..., min_length=10, description="Justification for granting")


class RevokeCapabilityRequest(BaseModel):
    target_agentium_id: str = Field(..., description="Agent to revoke capability from")
    capability:         str = Field(..., description="Capability to revoke")
    reason:             str = Field(..., min_length=10, description="Justification for revocation")


class CapabilityProfileResponse(BaseModel):
    tier:                    str
    agentium_id:             str
    base_capabilities:       List[str]
    granted_capabilities:    List[str]
    revoked_capabilities:    List[str]
    effective_capabilities:  List[str]
    total_count:             int


class CapabilityAuditResponse(BaseModel):
    total_agents:             int
    tier_distribution:        dict
    dynamic_grants_total:     int
    dynamic_revocations_total: int
    recent_capability_changes: List[dict]


class ValidateReassignmentRequest(BaseModel):
    agent_agentium_id:      str = Field(..., description="ID of the agent to reassign")
    new_parent_agentium_id: str = Field(..., description="ID of the proposed new parent")


class ValidateReassignmentResponse(BaseModel):
    valid:  bool
    reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/list")
async def list_all_capabilities(
    current_user: dict = Depends(get_current_active_user)
):
    """List all available capabilities in the system."""
    capabilities = {
        "head_of_council_0xxxx": [cap.value for cap in Capability if cap.value in [
            "veto", "amend_constitution", "liquidate_any", "admin_vector_db",
            "override_budget", "emergency_shutdown", "grant_capability", "revoke_capability"
        ]],
        "council_members_1xxxx": [cap.value for cap in Capability if cap.value in [
            "propose_amendment", "allocate_resources", "audit_system", "moderate_knowledge",
            "spawn_lead", "vote_on_amendment", "review_violations", "manage_channels"
        ]],
        "lead_agents_2xxxx": [cap.value for cap in Capability if cap.value in [
            "spawn_task_agent", "delegate_work", "request_resources", "submit_knowledge",
            "liquidate_task_agent", "escalate_to_council"
        ]],
        "task_agents_3xxxx": [cap.value for cap in Capability if cap.value in [
            "execute_task", "report_status", "escalate_blocker", "query_knowledge",
            "use_tools", "request_clarification"
        ]]
    }

    return {
        "capabilities_by_tier": capabilities,
        "total_capabilities":   len(Capability),
        "all_capabilities":     [cap.value for cap in Capability]
    }


@router.post("/check", response_model=CapabilityCheckResponse)
async def check_capability(
    request: CapabilityCheckRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Check if a specific agent has a specific capability."""
    agent = db.query(Agent).filter_by(agentium_id=request.agentium_id).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {request.agentium_id} not found"
        )

    try:
        capability = Capability(request.capability)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability: {request.capability}"
        )

    has_capability = CapabilityRegistry.can_agent(agent, capability, db)
    tier           = CapabilityRegistry.get_agent_tier(agent.agentium_id)

    return CapabilityCheckResponse(
        has_capability=has_capability,
        agentium_id=request.agentium_id,
        capability=request.capability,
        tier=tier,
        reason=(
            "Capability granted" if has_capability
            else f"Requires tier {CapabilityRegistry._get_required_tier(capability)}"
        )
    )


@router.get("/agent/{agentium_id}", response_model=CapabilityProfileResponse)
async def get_agent_capabilities(
    agentium_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get complete capability profile for an agent."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agentium_id} not found"
        )

    profile = CapabilityRegistry.get_agent_capabilities(agent)
    return CapabilityProfileResponse(**profile)


@router.post("/validate-reassignment", response_model=ValidateReassignmentResponse)
async def validate_reassignment(
    request: ValidateReassignmentRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Validate whether an agent can be reassigned to a new parent.

    Rules enforced:
      1. Head of Council (0xxxx) can never be reassigned.
      2. New parent's tier prefix must be numerically lower than agent's tier.
         (e.g. lead_agent 2xxxx can only move under council 1xxxx or head 0xxxx)
      3. New parent must have the capability to spawn the agent's type:
         - Receiving a task_agent  → new parent needs `spawn_task_agent`
         - Receiving a lead_agent  → new parent needs `spawn_lead`
      4. Neither agent may be terminated.
    """
    agent_id   = request.agent_agentium_id
    parent_id  = request.new_parent_agentium_id

    # ── Rule 1: Head cannot be reassigned ─────────────────────────────────
    if agent_id.startswith('0'):
        return ValidateReassignmentResponse(
            valid=False, reason="Head of Council cannot be reassigned."
        )

    # ── Rule 2: Tier hierarchy ─────────────────────────────────────────────
    agent_tier  = agent_id[0]  if agent_id  else '9'
    parent_tier = parent_id[0] if parent_id else '9'

    if parent_tier >= agent_tier:
        return ValidateReassignmentResponse(
            valid=False,
            reason=f"New parent (tier {parent_tier}) must outrank agent (tier {agent_tier})."
        )

    # ── Fetch agents from DB ───────────────────────────────────────────────
    agent      = db.query(Agent).filter_by(agentium_id=agent_id).first()
    new_parent = db.query(Agent).filter_by(agentium_id=parent_id).first()

    if not agent:
        return ValidateReassignmentResponse(
            valid=False, reason=f"Agent {agent_id} not found."
        )
    if not new_parent:
        return ValidateReassignmentResponse(
            valid=False, reason=f"Proposed parent {parent_id} not found."
        )

    # ── Rule 4: Neither terminated ─────────────────────────────────────────
    if getattr(agent, 'is_terminated', False) or agent.status in ('terminated', 'terminating'):
        return ValidateReassignmentResponse(
            valid=False, reason="Cannot reassign a terminated agent."
        )
    if getattr(new_parent, 'is_terminated', False) or new_parent.status in ('terminated', 'terminating'):
        return ValidateReassignmentResponse(
            valid=False, reason="Cannot assign to a terminated parent."
        )

    # ── Rule 3: Spawn capability check ────────────────────────────────────
    capability_map = {
        '3': 'spawn_task_agent',   # task agent → new parent needs spawn_task_agent
        '2': 'spawn_lead',         # lead agent → new parent needs spawn_lead
        '1': 'spawn_lead',         # council → new parent (head) needs spawn_lead
    }
    capability_needed = capability_map.get(agent_tier)

    if not capability_needed:
        return ValidateReassignmentResponse(
            valid=False, reason=f"No reassignment rule defined for tier {agent_tier}."
        )

    try:
        required_cap = Capability(capability_needed)
        has_cap      = CapabilityRegistry.can_agent(new_parent, required_cap, db)
    except ValueError:
        has_cap = False

    if not has_cap:
        return ValidateReassignmentResponse(
            valid=False,
            reason=f"New parent lacks '{capability_needed}' capability required to receive this agent."
        )

    return ValidateReassignmentResponse(valid=True)


@router.post("/grant")
async def grant_capability(
    request: GrantCapabilityRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Grant a capability to an agent. Requires GRANT_CAPABILITY permission."""
    target_agent = db.query(Agent).filter_by(agentium_id=request.target_agentium_id).first()

    if not target_agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target agent {request.target_agentium_id} not found"
        )

    granter = db.query(Agent).filter_by(agentium_id="00001").first()

    if not granter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Head of Council not found (required to grant capabilities)"
        )

    try:
        capability = Capability(request.capability)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability: {request.capability}"
        )

    try:
        CapabilityRegistry.grant_capability(
            target_agent, capability, granter, request.reason, db
        )
        db.commit()

        return {
            "success": True,
            "message":            f"Capability '{request.capability}' granted to {request.target_agentium_id}",
            "target_agentium_id": request.target_agentium_id,
            "capability":         request.capability,
            "granted_by":         granter.agentium_id,
            "reason":             request.reason,
        }

    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to grant capability: {str(e)}"
        )


@router.post("/revoke")
async def revoke_capability(
    request: RevokeCapabilityRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Revoke a capability from an agent. Requires REVOKE_CAPABILITY permission."""
    target_agent = db.query(Agent).filter_by(agentium_id=request.target_agentium_id).first()

    if not target_agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target agent {request.target_agentium_id} not found"
        )

    revoker = db.query(Agent).filter_by(agentium_id="00001").first()

    if not revoker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Head of Council not found (required to revoke capabilities)"
        )

    try:
        capability = Capability(request.capability)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability: {request.capability}"
        )

    try:
        CapabilityRegistry.revoke_capability(
            target_agent, capability, revoker, request.reason, db
        )
        db.commit()

        return {
            "success": True,
            "message":            f"Capability '{request.capability}' revoked from {request.target_agentium_id}",
            "target_agentium_id": request.target_agentium_id,
            "capability":         request.capability,
            "revoked_by":         revoker.agentium_id,
            "reason":             request.reason,
        }

    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke capability: {str(e)}"
        )


@router.get("/audit", response_model=CapabilityAuditResponse)
async def capability_audit(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate system-wide capability audit report. Admin/Council only."""
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Sovereign privileges required"
        )

    report = CapabilityRegistry.capability_audit_report(db)
    return CapabilityAuditResponse(**report)


@router.delete("/agent/{agentium_id}/all")
async def revoke_all_capabilities(
    agentium_id: str,
    reason: str = "manual_revocation",
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Revoke ALL capabilities from an agent. Emergency use only. Requires admin/sovereign."""
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Sovereign privileges required"
        )

    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agentium_id} not found"
        )

    if agentium_id == "00001":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot revoke all capabilities from Head of Council"
        )

    try:
        CapabilityRegistry.revoke_all_capabilities(agent, reason, db)
        db.commit()

        return {
            "success":    True,
            "message":    f"All capabilities revoked from {agentium_id}",
            "agentium_id": agentium_id,
            "reason":     reason,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke capabilities: {str(e)}"
        )