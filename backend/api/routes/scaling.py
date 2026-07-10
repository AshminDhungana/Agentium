from fastapi import APIRouter, Depends
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, Any

from backend.models.database import get_db
from backend.core.auth import get_current_user
from backend.services.predictive_scaling import predictive_scaling_service
from backend.models.entities.audit import AuditLog, AuditCategory
from backend.models.entities.agents import HeadOfCouncil, Agent, AgentStatus
from backend.services.reincarnation_service import ReincarnationService
from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample

router = APIRouter(tags=["Scaling"])

@router.get(
    "/scaling/predictions/load",
    summary="Get load predictions",
    description="Return next_1h, next_6h, next_24h predictions and current capacity.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def get_load_predictions():
    """Return next_1h, next_6h, next_24h predictions and current capacity."""
    try:
        predictions = predictive_scaling_service.get_predictions()
        return predictions
    except Exception as e:
        raise InternalServerError(error=str(e), code="STRE")

@router.get(
    "/scaling/history",
    summary="Get scaling history",
    description="Fetch the last 100 scaling decisions from AuditLog.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def get_scaling_history(db: Session = Depends(get_db)):
    """Fetch the last 100 scaling decisions from AuditLog."""
    logs = db.query(AuditLog).filter(
        AuditLog.category == AuditCategory.GOVERNANCE,
        AuditLog.action.in_([
            "auto_scale_predictive_spawn",
            "auto_scale_predictive_liquidate",
            "manual_scale_override"
        ])
    ).order_by(AuditLog.created_at.desc()).limit(100).all()

    return {"history": [log.to_dict() for log in logs]}

@router.post(
    "/scaling/override",
    summary="Manual scaling override",
    description="Manual override to spawn or liquidate agents immediately. Admin only.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def manual_scaling_override(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Manual override to spawn or liquidate agents immediately.
    Expects { action: 'spawn' | 'liquidate', count: int, tier: int }
    Admin only (or sovereign).
    """
    if current_user.get("role") not in ["primary_sovereign", "admin"]:
        raise ForbiddenError(error="Admin permissions required.", code="ADMIN_PERMISSIONS_REQUIRED")

    action = payload.get("action")
    count = payload.get("count", 1)
    tier = payload.get("tier", 3)

    if action == "spawn":
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if not head:
            raise InternalServerError(error="Head of Council not found", code="HEAD_OF_COUNCIL_NOT_FOUND")

        spawned = 0
        for i in range(count):
            try:
                ReincarnationService.spawn_task_agent(
                    parent=head,
                    name=f"Manual-Spawn-{datetime.utcnow().strftime('%H%M%S')}-{i}",
                    description=f"Manually spawned Task Agent via scaling override (count: {count})",
                    db=db
                )
                spawned += 1
            except Exception as e:
                pass

        AuditLog.log(
            db=db,
            level="INFO",
            category=AuditCategory.GOVERNANCE,
            actor_type="user",
            actor_id=current_user.get("id"),
            action="manual_scale_override",
            description=f"Manual override: spawn {spawned} agents.",
            after_state={"action": "spawn", "count": count, "spawned": spawned}
        )
        return {"status": "success", "spawned": spawned}

    elif action == "liquidate":
        # Find active task agents
        agents = db.query(Agent).filter(
            Agent.tier == tier,
            Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.IDLE]),
            Agent.is_persistent == False
        ).limit(count).all()

        liquidated = 0
        for ag in agents:
            ag.is_active = False
            ag.status = AgentStatus.TERMINATED
            liquidated += 1

        db.commit()

        AuditLog.log(
            db=db,
            level="INFO",
            category=AuditCategory.GOVERNANCE,
            actor_type="user",
            actor_id=current_user.get("id"),
            action="manual_scale_override",
            description=f"Manual override: liquidated {liquidated} agents.",
            after_state={"action": "liquidate", "count": count, "liquidated": liquidated}
        )
        return {"status": "success", "liquidated": liquidated}
    else:
        raise BadRequestError(error="Invalid action", code="INVALID_ACTION")
