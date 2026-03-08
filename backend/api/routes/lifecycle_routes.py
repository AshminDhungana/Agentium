"""
API routes for Agent Lifecycle Management.
Provides endpoints for spawning, promoting, and liquidating agents.

"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.agents import Agent
from backend.services.reincarnation_service import reincarnation_service
from backend.core.auth import get_current_active_user

router = APIRouter(prefix="/api/v1/agents/lifecycle", tags=["Agent Lifecycle"])


# ═══════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════

class SpawnTaskAgentRequest(BaseModel):
    parent_agentium_id: str = Field(..., description="Parent agent ID (Lead or Council)")
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10, max_length=500)
    capabilities: Optional[List[str]] = Field(default=None, description="Custom capabilities to grant")


class SpawnLeadAgentRequest(BaseModel):
    parent_agentium_id: str = Field(..., description="Parent agent ID (Council or Head)")
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10, max_length=500)


class PromoteAgentRequest(BaseModel):
    task_agentium_id: str = Field(..., description="Task Agent ID to promote (3xxxx)")
    promoted_by_agentium_id: str = Field(..., description="Agent authorizing promotion (Council/Head)")
    reason: str = Field(..., min_length=20, max_length=500, description="Justification for promotion")


class LiquidateAgentRequest(BaseModel):
    target_agentium_id: str = Field(..., description="Agent ID to liquidate")
    liquidated_by_agentium_id: str = Field(..., description="Agent authorizing liquidation")
    reason: str = Field(..., min_length=20, max_length=500, description="Justification for liquidation")
    force: bool = Field(default=False, description="Force liquidation (bypass safety checks)")


class BulkLiquidateRequest(BaseModel):
    """Request body for bulk liquidation. Query-param fallback still supported."""
    idle_days_threshold: int = Field(default=7, ge=1, le=365)
    dry_run: bool = Field(default=True)


class AgentSpawnResponse(BaseModel):
    success: bool
    agentium_id: str
    name: str
    agent_type: str
    parent_agentium_id: str
    capabilities: List[str]
    message: str


class PromotionResponse(BaseModel):
    success: bool
    old_agentium_id: str
    new_agentium_id: str
    promoted_by: str
    reason: str
    tasks_transferred: int
    message: str


class LiquidationResponse(BaseModel):
    success: bool
    agentium_id: str
    liquidated_by: str
    reason: str
    tasks_cancelled: int
    tasks_reassigned: int
    child_agents_notified: int
    capabilities_revoked: int
    message: str


class CapacityResponse(BaseModel):
    head: dict
    council: dict
    lead: dict
    task: dict
    warnings: List[str]


# ── WebSocket manager (imported lazily to avoid circular imports) ──────────────

def _get_ws_manager():
    """Lazy import of the singleton WebSocket manager to avoid circular imports."""
    try:
        from backend.api.routes.websocket import manager
        return manager
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# SPAWNING ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.post("/spawn/task", response_model=AgentSpawnResponse)
async def spawn_task_agent(
    request: SpawnTaskAgentRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Spawn a new Task Agent (3xxxx).
    Parent must be a Lead Agent or Council Member.
    Broadcasts agent_spawned WebSocket event on success.
    """
    parent = db.query(Agent).filter_by(agentium_id=request.parent_agentium_id).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent agent {request.parent_agentium_id} not found"
        )

    if not request.parent_agentium_id.startswith(('1', '2')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent must be a Lead Agent (2xxxx) or Council Member (1xxxx)"
        )

    try:
        task_agent = reincarnation_service.spawn_task_agent(
            parent=parent,
            name=request.name,
            description=request.description,
            capabilities=request.capabilities,
            db=db
        )

        db.commit()

        from backend.services.capability_registry import CapabilityRegistry
        caps_profile = CapabilityRegistry.get_agent_capabilities(task_agent)

        # ── Broadcast WS event ──────────────────────────────────────────────
        ws_manager = _get_ws_manager()
        if ws_manager:
            background_tasks.add_task(
                ws_manager.emit_agent_spawned,
                agent_id=task_agent.agentium_id,
                agent_name=task_agent.name,
                agent_type="task_agent",
                parent_id=request.parent_agentium_id,
            )

        return AgentSpawnResponse(
            success=True,
            agentium_id=task_agent.agentium_id,
            name=task_agent.name,
            agent_type="task_agent",
            parent_agentium_id=request.parent_agentium_id,
            capabilities=caps_profile["effective_capabilities"],
            message=f"Task Agent {task_agent.agentium_id} spawned successfully"
        )

    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to spawn Task Agent: {str(e)}"
        )


@router.post("/spawn/lead", response_model=AgentSpawnResponse)
async def spawn_lead_agent(
    request: SpawnLeadAgentRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Spawn a new Lead Agent (2xxxx).
    Parent must be a Council Member or Head of Council.
    Broadcasts agent_spawned WebSocket event on success.
    """
    parent = db.query(Agent).filter_by(agentium_id=request.parent_agentium_id).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent agent {request.parent_agentium_id} not found"
        )

    if not request.parent_agentium_id.startswith(('0', '1')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent must be a Council Member (1xxxx) or Head of Council (0xxxx)"
        )

    try:
        lead_agent = reincarnation_service.spawn_lead_agent(
            parent=parent,
            name=request.name,
            description=request.description,
            db=db
        )

        db.commit()

        from backend.services.capability_registry import CapabilityRegistry
        caps_profile = CapabilityRegistry.get_agent_capabilities(lead_agent)

        # ── Broadcast WS event ──────────────────────────────────────────────
        ws_manager = _get_ws_manager()
        if ws_manager:
            background_tasks.add_task(
                ws_manager.emit_agent_spawned,
                agent_id=lead_agent.agentium_id,
                agent_name=lead_agent.name,
                agent_type="lead_agent",
                parent_id=request.parent_agentium_id,
            )

        return AgentSpawnResponse(
            success=True,
            agentium_id=lead_agent.agentium_id,
            name=lead_agent.name,
            agent_type="lead_agent",
            parent_agentium_id=request.parent_agentium_id,
            capabilities=caps_profile["effective_capabilities"],
            message=f"Lead Agent {lead_agent.agentium_id} spawned successfully"
        )

    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to spawn Lead Agent: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════
# PROMOTION ENDPOINT
# ═══════════════════════════════════════════════════════════

@router.post("/promote", response_model=PromotionResponse)
async def promote_task_to_lead(
    request: PromoteAgentRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Promote a Task Agent (3xxxx) to Lead Agent (2xxxx).
    Requires Council or Head authorization.
    Broadcasts agent_promoted WebSocket event on success.
    """
    promoter = db.query(Agent).filter_by(agentium_id=request.promoted_by_agentium_id).first()

    if not promoter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promoter agent {request.promoted_by_agentium_id} not found"
        )

    if not request.task_agentium_id.startswith('3'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Task Agents (3xxxx) can be promoted to Lead"
        )

    try:
        lead_agent = reincarnation_service.promote_to_lead(
            agent_id=request.task_agentium_id,
            promoted_by=promoter,
            reason=request.reason,
            db=db
        )

        from backend.models.entities.audit import AuditLog
        promotion_audit = db.query(AuditLog).filter_by(
            action="agent_promoted",
            target_id=lead_agent.agentium_id
        ).order_by(AuditLog.created_at.desc()).first()

        tasks_transferred = 0
        if promotion_audit and promotion_audit.meta_data:
            tasks_transferred = promotion_audit.meta_data.get("tasks_transferred", 0)

        # ── Broadcast WS event ──────────────────────────────────────────────
        ws_manager = _get_ws_manager()
        if ws_manager:
            background_tasks.add_task(
                ws_manager.emit_agent_promoted,
                old_agentium_id=request.task_agentium_id,
                new_agentium_id=lead_agent.agentium_id,
                agent_name=lead_agent.name,
                promoted_by=request.promoted_by_agentium_id,
                reason=request.reason,
            )

        return PromotionResponse(
            success=True,
            old_agentium_id=request.task_agentium_id,
            new_agentium_id=lead_agent.agentium_id,
            promoted_by=request.promoted_by_agentium_id,
            reason=request.reason,
            tasks_transferred=tasks_transferred,
            message=f"Agent {request.task_agentium_id} promoted to {lead_agent.agentium_id}"
        )

    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote agent: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════
# LIQUIDATION ENDPOINT
# ═══════════════════════════════════════════════════════════

@router.post("/liquidate", response_model=LiquidationResponse)
async def liquidate_agent(
    request: LiquidateAgentRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Liquidate (terminate) an agent with full cleanup.
    Requires appropriate authorization based on tier hierarchy.
    Broadcasts agent_liquidated WebSocket event on success.
    """
    liquidator = db.query(Agent).filter_by(agentium_id=request.liquidated_by_agentium_id).first()

    if not liquidator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Liquidator agent {request.liquidated_by_agentium_id} not found"
        )

    if request.target_agentium_id == "00001" and not request.force:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot liquidate Head of Council (00001)"
        )

    # Capture agent name before liquidation for WS event
    target_agent = db.query(Agent).filter_by(agentium_id=request.target_agentium_id).first()
    target_name  = target_agent.name if target_agent else request.target_agentium_id

    try:
        summary = reincarnation_service.liquidate_agent(
            agent_id=request.target_agentium_id,
            liquidated_by=liquidator,
            reason=request.reason,
            db=db,
            force=request.force
        )

        # ── Broadcast WS event ──────────────────────────────────────────────
        ws_manager = _get_ws_manager()
        if ws_manager:
            background_tasks.add_task(
                ws_manager.emit_agent_liquidated,
                agent_id=request.target_agentium_id,
                agent_name=target_name,
                liquidated_by=request.liquidated_by_agentium_id,
                reason=request.reason,
                tasks_reassigned=summary.get("tasks_reassigned", 0),
            )

        return LiquidationResponse(
            success=True,
            agentium_id=summary["agent_id"],
            liquidated_by=summary["liquidated_by"],
            reason=summary["reason"],
            tasks_cancelled=summary["tasks_cancelled"],
            tasks_reassigned=summary["tasks_reassigned"],
            child_agents_notified=summary["child_agents_notified"],
            capabilities_revoked=summary["capabilities_revoked"],
            message=f"Agent {request.target_agentium_id} liquidated successfully"
        )

    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to liquidate agent: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════
# CAPACITY MANAGEMENT ENDPOINT
# ═══════════════════════════════════════════════════════════

@router.get("/capacity", response_model=CapacityResponse)
async def get_capacity(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get available ID pool capacity for each agent tier."""
    capacity = reincarnation_service.get_available_capacity(db)

    warnings = []
    for tier_name, tier_data in capacity.items():
        if tier_data["critical"]:
            warnings.append(f"CRITICAL: {tier_name.upper()} tier at {tier_data['percentage']}% capacity")
        elif tier_data["warning"]:
            warnings.append(f"WARNING: {tier_name.upper()} tier at {tier_data['percentage']}% capacity")

    return CapacityResponse(
        head=capacity["head"],
        council=capacity["council"],
        lead=capacity["lead"],
        task=capacity["task"],
        warnings=warnings
    )


# ═══════════════════════════════════════════════════════════
# BULK OPERATIONS
# ═══════════════════════════════════════════════════════════

@router.post("/bulk/liquidate-idle")
async def bulk_liquidate_idle_agents(
    body: Optional[BulkLiquidateRequest] = None,
    # Query-param fallback for backward-compat
    idle_days_threshold: int = 7,
    dry_run: bool = True,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Bulk liquidate idle agents.
    Accepts params as JSON body (preferred) or query params (legacy).
    Set dry_run=false to actually execute. Admin/Sovereign only.
    """
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Sovereign privileges required"
        )

    # Body takes precedence over query params
    effective_threshold = body.idle_days_threshold if body else idle_days_threshold
    effective_dry_run   = body.dry_run if body else dry_run

    from backend.services.idle_governance_enhanced import enhanced_idle_governance

    original_threshold = enhanced_idle_governance.IDLE_THRESHOLD_DAYS
    enhanced_idle_governance.IDLE_THRESHOLD_DAYS = effective_threshold

    try:
        if effective_dry_run:
            idle_agents = await enhanced_idle_governance.detect_idle_agents(db)
            return {
                "dry_run": True,
                "idle_agents_found": len(idle_agents),
                "idle_agents": idle_agents,
                "message": "Dry run complete. Set dry_run=false to execute liquidation."
            }
        else:
            summary = await enhanced_idle_governance.auto_liquidate_expired(db)
            return {
                "dry_run": False,
                "liquidated_count": summary["liquidated_count"],
                "liquidated": summary["liquidated"],
                "skipped_count": summary["skipped_count"],
                "skipped": summary["skipped"],
                "message": f"Liquidated {summary['liquidated_count']} idle agents"
            }
    finally:
        enhanced_idle_governance.IDLE_THRESHOLD_DAYS = original_threshold


# ═══════════════════════════════════════════════════════════
# LIFECYCLE STATS
# ═══════════════════════════════════════════════════════════

@router.get("/stats/lifecycle")
async def get_lifecycle_stats(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive lifecycle statistics (last 30 days)."""
    from backend.models.entities.audit import AuditLog
    from datetime import timedelta
    from sqlalchemy import func

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    spawned = db.query(AuditLog).filter(
        AuditLog.action.in_(["agent_spawned", "lead_spawned"]),
        AuditLog.created_at >= thirty_days_ago
    ).count()

    promoted = db.query(AuditLog).filter(
        AuditLog.action == "agent_promoted",
        AuditLog.created_at >= thirty_days_ago
    ).count()

    liquidated = db.query(AuditLog).filter(
        AuditLog.action == "agent_liquidated",
        AuditLog.created_at >= thirty_days_ago
    ).count()

    reincarnated = db.query(AuditLog).filter(
        AuditLog.action == "agent_birth",
        AuditLog.created_at >= thirty_days_ago
    ).count()

    active_by_tier = {}
    for prefix in ['0', '1', '2', '3']:
        count = db.query(func.count(Agent.id)).filter(
            Agent.agentium_id.like(f"{prefix}%"),
            Agent.is_active == True
        ).scalar()
        active_by_tier[f"tier_{prefix}"] = count

    return {
        "period_days": 30,
        "lifecycle_events": {
            "spawned":      spawned,
            "promoted":     promoted,
            "liquidated":   liquidated,
            "reincarnated": reincarnated,
        },
        "active_agents_by_tier": active_by_tier,
        "capacity": reincarnation_service.get_available_capacity(db)
    }