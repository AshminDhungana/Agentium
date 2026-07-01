"""API routes for Agent Reassignment."""

from fastapi import APIRouter, Depends, status, BackgroundTasks
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.auth import get_current_active_user
from backend.models.database import get_db
from backend.models.entities.agents import Agent
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.core.constitutional_guard import ConstitutionalGuard

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Reassignment"])


class ReassignParentRequest(BaseModel):
    new_parent_id: str = Field(..., min_length=1, max_length=10, description="Agentium ID of the new parent agent")
    reason: str = Field(default="", max_length=500, description="Optional reason for reassignment")


class ReassignParentResponse(BaseModel):
    success: bool
    agentium_id: str
    old_parent_id: str | None
    new_parent_id: str
    message: str
    constitutional_verdict: str = "ALLOW"
    requires_vote: bool = False
    audit_log_id: str | None = None


def _get_ws_manager():
    """Lazy import of the singleton WebSocket manager to avoid circular imports."""
    try:
        from backend.api.routes.websocket import manager
        return manager
    except Exception:
        return None


@router.patch("/{agentium_id}/parent", response_model=ReassignParentResponse)
async def reassign_agent(
    agentium_id: str,
    request: ReassignParentRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Reassign an agent to a new parent.

    Runs a two-tier constitutional guard before persisting.
    Returns 403 BLOCK if the reassignment violates the constitution.
    Returns 200 with requires_vote=True if a Council vote is needed.
    """
    # ------------------------------------------------------------------
    # 1. Resolve both agents
    # ------------------------------------------------------------------
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not agent:
        raise NotFoundError(error=f"Agent {agentium_id} not found", code="AGENT_NOT_FOUND")

    new_parent = db.query(Agent).filter_by(agentium_id=request.new_parent_id).first()
    if not new_parent:
        raise NotFoundError(error=f"New parent {request.new_parent_id} not found", code="NEW_PARENT_NOT_FOUND")

    if new_parent.status in ('terminated', 'terminating'):
        raise BadRequestError(error="Cannot reassign to a terminated agent", code="CANNOT_REASSIGN_TO_A_TERMINATED")

    old_parent_id = agent.parent.agentium_id if agent.parent else None

    # ------------------------------------------------------------------
    # 2. Run Constitutional Guard
    # ------------------------------------------------------------------
    guard = ConstitutionalGuard(db)
    try:
        await guard.initialize()
    except Exception:
        # If ChromaDB/RAG is unavailable, guard still works (Tier 1 only)
        pass

    decision = await guard.check_action(
        agent_id=new_parent.agentium_id,
        action="reassign_agent",
        context={
            "new_parent_id": request.new_parent_id,
            "agent_to_reassign": agentium_id,
            "reason": request.reason or "Manual drag-and-drop reassignment",
        },
    )

    # ------------------------------------------------------------------
    # 3. Handle BLOCK
    # ------------------------------------------------------------------
    if decision.verdict.value == "block":
        audit = AuditLog(
            level=AuditLevel.CRITICAL,
            category=AuditCategory.CONSTITUTION,
            actor_type="user",
            actor_id=current_user.get("id", "unknown"),
            action="constitutional_check:reassign_agent",
            target_type="agent",
            target_id=agentium_id,
            description=f"Reassignment blocked by Constitution: {decision.explanation}",
            metadata_json=str({"citations": decision.citations, "severity": decision.severity.value}),
            success="N",
        )
        db.add(audit)
        db.commit()

        raise ForbiddenError(error={
                "error": "Constitutional Block",
                "code": "CONSTITUTIONAL_BLOCK",
                "detail": {
                    "verdict": "BLOCK",
                    "explanation": decision.explanation,
                    "citations": decision.citations,
                    "severity": decision.severity.value,
                },
            }, code="ERROR")

    # ------------------------------------------------------------------
    # 4. Handle VOTE_REQUIRED
    # ------------------------------------------------------------------
    if decision.verdict.value == "vote_required":
        audit = AuditLog(
            level=AuditLevel.WARNING,
            category=AuditCategory.CONSTITUTION,
            actor_type="user",
            actor_id=current_user.get("id", "unknown"),
            action="constitutional_check:reassign_agent",
            target_type="agent",
            target_id=agentium_id,
            description=f"Reassignment requires Council vote: {decision.explanation}",
            metadata_json=str({"citations": decision.citations, "severity": decision.severity.value}),
            success="N",
        )
        db.add(audit)
        db.commit()

        return ReassignParentResponse(
            success=False,
            agentium_id=agentium_id,
            old_parent_id=old_parent_id,
            new_parent_id=request.new_parent_id,
            message=f"Reassignment requires Council vote: {decision.explanation}",
            constitutional_verdict="VOTE_REQUIRED",
            requires_vote=True,
            audit_log_id=str(audit.id) if audit else None,
        )

    # ------------------------------------------------------------------
    # 5. ALLOW - persist reassignment
    # ------------------------------------------------------------------
    try:
        agent.parent_id = new_parent.id
        db.commit()
    except Exception as exc:
        db.rollback()
        raise InternalServerError(error=f"Failed to persist reassignment: {str(exc)}", code="FAILED_TO_PERSIST_REASSIGNMENT") from exc

    # ------------------------------------------------------------------
    # 6. Audit log for ALLOW
    # ------------------------------------------------------------------
    audit = AuditLog(
        level=AuditLevel.INFO,
        category=AuditCategory.AGENT_LIFECYCLE,
        actor_type="user",
        actor_id=current_user.get("id", "unknown"),
        action="agent_reassigned",
        target_type="agent",
        target_id=agentium_id,
        description=f"Agent {agentium_id} reassigned from {old_parent_id or 'none'} to {request.new_parent_id}",
        metadata_json=str({
            "old_parent_id": old_parent_id,
            "new_parent_id": request.new_parent_id,
            "reason": request.reason,
        }),
        success="Y",
    )
    db.add(audit)
    db.commit()

    # ------------------------------------------------------------------
    # 7. WebSocket broadcast
    # ------------------------------------------------------------------
    ws_manager = _get_ws_manager()
    if ws_manager:
        background_tasks.add_task(
            ws_manager.broadcast,
            {
                "type": "agent_reassigned",
                "agentium_id": agentium_id,
                "old_parent_id": old_parent_id,
                "new_parent_id": request.new_parent_id,
                "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
            }
        )

    return ReassignParentResponse(
        success=True,
        agentium_id=agentium_id,
        old_parent_id=old_parent_id,
        new_parent_id=request.new_parent_id,
        message=f"Agent {agentium_id} reassigned to {request.new_parent_id}",
        constitutional_verdict="ALLOW",
        requires_vote=False,
        audit_log_id=str(audit.id),
    )
