"""
Phase 13.6 — Event Trigger API Routes
=======================================
CRUD for EventTriggers, public webhook receiver, event log viewer,
and dead-letter queue management.
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.models.database import get_db_context
from backend.models.entities.event_trigger import (
    EventLog,
    EventLogStatus,
    EventTrigger,
    TriggerType,
)
from backend.services.event_processor import EventProcessorService

router = APIRouter(prefix="/events", tags=["Events"])


# ── Dependency ────────────────────────────────────────────────────────────────

def get_db():
    with get_db_context() as db:
        yield db


# ── Trigger CRUD ──────────────────────────────────────────────────────────────

@router.get("/triggers", response_model=List[Dict[str, Any]])
def list_triggers(db: Session = Depends(get_db)):
    """List all event triggers."""
    triggers = db.query(EventTrigger).order_by(EventTrigger.created_at.desc()).all()
    return [t.to_dict() for t in triggers]


@router.post("/triggers", response_model=Dict[str, Any])
def create_trigger(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Create a new event trigger."""
    name = payload.get("name")
    trigger_type = payload.get("trigger_type")
    config = payload.get("config", {})
    target_workflow_id = payload.get("target_workflow_id")
    target_agent_id = payload.get("target_agent_id")

    if not name or not trigger_type:
        raise HTTPException(status_code=400, detail="name and trigger_type are required")

    try:
        tt = TriggerType(trigger_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trigger_type. Must be one of: {[t.value for t in TriggerType]}",
        )

    # For webhook triggers, auto-generate an HMAC secret if not provided
    if tt == TriggerType.WEBHOOK and not config.get("hmac_secret"):
        config["hmac_secret"] = uuid.uuid4().hex

    trigger = EventTrigger(
        name=name,
        trigger_type=tt,
        config=config,
        target_workflow_id=target_workflow_id,
        target_agent_id=target_agent_id,
        max_fires_per_minute=payload.get("max_fires_per_minute", 10),
        pause_duration_seconds=payload.get("pause_duration_seconds", 300),
    )
    db.add(trigger)
    db.commit()
    db.refresh(trigger)
    return trigger.to_dict()


@router.put("/triggers/{trigger_id}", response_model=Dict[str, Any])
def update_trigger(
    trigger_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """Update an existing event trigger."""
    trigger = db.query(EventTrigger).filter(EventTrigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    for field in (
        "name", "config", "target_workflow_id", "target_agent_id",
        "max_fires_per_minute", "pause_duration_seconds",
    ):
        if field in payload:
            setattr(trigger, field, payload[field])

    if "is_active" in payload:
        trigger.is_active = payload["is_active"]
        if payload["is_active"]:
            trigger.paused_until = None  # Unpause on re-enable

    db.commit()
    db.refresh(trigger)
    return trigger.to_dict()


@router.delete("/triggers/{trigger_id}", response_model=Dict[str, Any])
def delete_trigger(trigger_id: str, db: Session = Depends(get_db)):
    """Deactivate (soft-delete) a trigger."""
    trigger = db.query(EventTrigger).filter(EventTrigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    trigger.deactivate()
    db.commit()
    return {"status": "deactivated", "id": trigger_id}


# ── Public Webhook Receiver ───────────────────────────────────────────────────

@router.post("/webhook/{trigger_id}", response_model=Dict[str, Any])
async def receive_webhook(trigger_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Public endpoint for external webhook delivery.
    Uses HMAC-SHA256 for authentication (no Bearer token required).
    """
    body = await request.body()
    signature = request.headers.get("X-Agentium-Signature", "")
    correlation_id = request.headers.get("X-Correlation-Id", None)

    result = EventProcessorService.receive_webhook(
        db=db,
        trigger_id=trigger_id,
        body=body,
        signature=signature,
        correlation_id=correlation_id,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail", "Processing error"))

    return result


# ── Event Logs ────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=List[Dict[str, Any]])
def list_event_logs(
    trigger_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Paginated event log viewer with optional filters."""
    query = db.query(EventLog).order_by(EventLog.created_at.desc())

    if trigger_id:
        query = query.filter(EventLog.trigger_id == trigger_id)
    if status:
        try:
            st = EventLogStatus(status)
            query = query.filter(EventLog.status == st)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    logs = query.offset(offset).limit(limit).all()
    return [l.to_dict() for l in logs]


# ── Dead-Letter Queue ─────────────────────────────────────────────────────────

@router.get("/dead-letters", response_model=List[Dict[str, Any]])
def list_dead_letters(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """View events that failed processing multiple times."""
    return EventProcessorService.get_dead_letters(db, limit=limit, offset=offset)


@router.post("/dead-letters/{log_id}/retry", response_model=Dict[str, Any])
def retry_dead_letter(log_id: str, db: Session = Depends(get_db)):
    """Manually retry a dead-lettered event."""
    result = EventProcessorService.retry_dead_letter(db, log_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail", "Retry failed"))
    return result
