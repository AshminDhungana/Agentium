"""
Federation API Routes 
=============================================
"""
import json
import time
import logging
from typing import List, Dict, Any, Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.services.federation_service import FederationService
from backend.api.routes.rbac import get_current_user_from_token
from backend.models.entities.user import User
from backend.core.config import settings

router = APIRouter(prefix="/federation", tags=["Federation"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ──────────────────────────────────────────────────────────────────────────────

class PeerRegisterRequest(BaseModel):
    name: str
    base_url: str
    shared_secret: str
    trust_level: str = "limited"
    capabilities: List[str] = []


class PeerTrustUpdateRequest(BaseModel):
    trust_level: str


class TaskDelegateRequest(BaseModel):
    target_peer_id: str
    original_task_id: str
    payload: Dict[str, Any]


class TaskReceiveRequest(BaseModel):
    original_task_id: str
    payload: Dict[str, Any]


class TaskResultRequest(BaseModel):
    original_task_id: str
    local_task_id: str
    status: str                    # "completed" | "failed"
    result_summary: str = ""
    result_data: Optional[Dict[str, Any]] = None


# ──────────────────────────────────────────────────────────────────────────────
# Peer authentication dependency  (used on all webhook endpoints)
# ──────────────────────────────────────────────────────────────────────────────

async def authenticate_peer(
    request: Request,
    db: Session = Depends(get_db),
    x_agentium_peer_url: Optional[str] = Header(default=None),
    x_agentium_signature: Optional[str] = Header(default=None),
    x_agentium_timestamp: Optional[str] = Header(default=None),
    # Legacy header — still accepted for backward-compat
    x_agentium_secret: Optional[str] = Header(default=None),
):
    """
    Dual-mode peer authentication:
    1. HMAC (preferred): X-Agentium-Signature + X-Agentium-Timestamp
    2. Legacy secret:    X-Agentium-Secret  (will be removed in a future version)
    """
    if not x_agentium_peer_url:
        raise HTTPException(status_code=401, detail="Missing X-Agentium-Peer-Url header.")

    # Preferred: HMAC path
    if x_agentium_signature and x_agentium_timestamp:
        try:
            ts = int(x_agentium_timestamp)
        except ValueError:
            raise HTTPException(status_code=400, detail="X-Agentium-Timestamp must be a unix integer.")
        raw_body = await request.body()
        return FederationService.authenticate_peer_hmac(
            db=db,
            peer_url=x_agentium_peer_url,
            signature=x_agentium_signature,
            timestamp=ts,
            raw_body=raw_body,
        )

    # Fallback: legacy plain-secret path
    if x_agentium_secret:
        logger.warning(
            "Federation: peer %s using deprecated plain-secret auth. "
            "Please upgrade to HMAC signing.",
            x_agentium_peer_url,
        )
        return FederationService.authenticate_peer_legacy(
            db=db,
            base_url=x_agentium_peer_url,
            secret=x_agentium_secret,
        )

    raise HTTPException(
        status_code=401,
        detail="Provide either (X-Agentium-Signature + X-Agentium-Timestamp) or X-Agentium-Secret.",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Admin endpoints  (require Sovereign / admin login)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/peers", status_code=status.HTTP_201_CREATED)
def register_peer(
    request: PeerRegisterRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Register a new peer Agentium instance. Requires admin (Sovereign) privileges."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Sovereign (admin) can register peers.")

    peer = FederationService.register_peer(
        db=db,
        name=request.name,
        base_url=request.base_url,
        shared_secret=request.shared_secret,
        trust_level=request.trust_level,
        capabilities=request.capabilities,
    )
    return {
        "id": peer.id,
        "name": peer.name,
        "base_url": peer.base_url,
        "status": peer.status,
        "trust_level": peer.trust_level,
        "capabilities_shared": peer.capabilities_shared,
    }


@router.get("/peers")
def list_peers(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    List registered peer instances.

    Query params:
      - skip  (int, default 0):   offset for pagination.
      - limit (int, default 100): max records to return.

    These params are optional — omitting them returns all peers up to the
    default limit, preserving backward compatibility with existing callers.
    """
    peers = FederationService.list_peers(db, skip=skip, limit=limit)
    return [
        {
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "status": p.status,
            "trust_level": p.trust_level,
            "capabilities_shared": p.capabilities_shared or [],
            "last_heartbeat_at": p.last_heartbeat_at,
            "registered_at": p.registered_at,
        }
        for p in peers
    ]


@router.delete("/peers/{peer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_peer(
    peer_id: str,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Remove a peer instance. Requires admin privileges."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Sovereign (admin) can remove peers.")
    FederationService.delete_peer(db, peer_id)


@router.patch("/peers/{peer_id}/trust")
def update_peer_trust(
    peer_id: str,
    request: PeerTrustUpdateRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Update the trust level of a registered peer."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Sovereign (admin) can update peer trust.")
    peer = FederationService.update_peer_trust(db, peer_id, request.trust_level)
    return {"id": peer.id, "trust_level": peer.trust_level}


# ──────────────────────────────────────────────────────────────────────────────
# Outgoing task delegation
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/tasks/delegate")
def delegate_task(
    request: TaskDelegateRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Delegate a local task to a peer instance.
    Creates a FederatedTask record and dispatches HTTP delivery via Celery.
    """
    fed_task = FederationService.delegate_task(
        db=db,
        target_peer_id=request.target_peer_id,
        original_task_id=request.original_task_id,
        payload=request.payload,
        my_base_url=getattr(settings, "FEDERATION_INSTANCE_URL", ""),
        my_secret=getattr(settings, "FEDERATION_SHARED_SECRET", ""),
    )
    return {
        "id": fed_task.id,
        "status": fed_task.status,
        "message": "Delivery queued via Celery worker.",
    }


@router.get("/tasks")
def list_federated_tasks(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """List recent federated tasks (incoming and outgoing)."""
    tasks = FederationService.list_federated_tasks(db)
    return [
        {
            "id": t.id,
            "original_task_id": t.original_task_id,
            "local_task_id": t.local_task_id,
            "source_instance_id": t.source_instance_id,
            "target_instance_id": t.target_instance_id,
            "status": t.status,
            "delegated_at": t.delegated_at,
            "completed_at": t.completed_at,
            "direction": "incoming" if t.source_instance_id else "outgoing",
        }
        for t in tasks
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Incoming webhook endpoints  (authenticated via authenticate_peer dependency)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/webhooks/tasks/receive")
async def receive_delegated_task(
    request: Request,
    db: Session = Depends(get_db),
    peer=Depends(authenticate_peer),
):
    """
    Receive a task delegated from a peer instance.
    Creates a real local Task record so agents pick it up.
    """
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    req = TaskReceiveRequest(**data)
    fed_task = FederationService.receive_delegated_task(
        db=db,
        source_peer=peer,
        original_task_id=req.original_task_id,
        payload=req.payload,
    )
    return {"accepted": True, "local_task_id": fed_task.local_task_id}


@router.post("/webhooks/tasks/result")
async def receive_task_result(
    request: Request,
    db: Session = Depends(get_db),
    peer=Depends(authenticate_peer),
):
    """
    Receive a result callback from a peer after it finishes a delegated task.
    Updates the originating FederatedTask record and local Task status.
    """
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    req = TaskResultRequest(**data)
    fed_task = FederationService.receive_task_result(
        db=db,
        source_peer=peer,
        original_task_id=req.original_task_id,
        local_task_id=req.local_task_id,
        status=req.status,
        result_summary=req.result_summary,
        result_data=req.result_data,
    )
    return {"acknowledged": True, "fed_task_status": fed_task.status}


@router.post("/webhooks/heartbeat")
async def receive_heartbeat(
    request: Request,
    db: Session = Depends(get_db),
    peer=Depends(authenticate_peer),
):
    """
    Respond to an active heartbeat probe from a peer.
    authenticate_peer already updates last_heartbeat_at, so we just return OK.
    """
    return {
        "alive": True,
        "instance": getattr(settings, "FEDERATION_INSTANCE_NAME", "Agentium"),
        "timestamp": int(time.time()),
    }

# ── Phase 11.2: Knowledge & Voting Routes ─────────────────────────────────

@router.post("/knowledge/sync/{peer_id}")
def sync_knowledge_from_peer(
    peer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """Manually trigger a pull of domain knowledge (constitution) from a peer."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Sovereign can sync knowledge.")
        
    my_url = settings.FEDERATION_INSTANCE_URL
    my_secret = getattr(settings, "FEDERATION_SHARED_SECRET", "")
    key = FederationService._derive_signing_key(my_secret)
    
    success = FederationService.sync_constitution_from_peer(
        db=db, 
        target_peer_id=peer_id, 
        my_base_url=my_url, 
        my_signing_key=key
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to sync knowledge from peer.")
        
    return {"status": "success", "message": "Knowledge synced to vector store."}


class CreateVoteRequest(BaseModel):
    proposal_id: str
    peer_ids: List[str]
    duration_hours: int = 48

@router.post("/votes")
def create_federated_vote(
    request: CreateVoteRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Creates a federated vote spanning multiple instances."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Sovereign can create federated votes.")
        
    vote = FederationService.create_federated_vote(
        db=db,
        proposal_id=request.proposal_id,
        peer_ids=request.peer_ids,
        duration_hours=request.duration_hours
    )
    return {
        "id": vote.id,
        "proposal_id": vote.proposal_id,
        "participating_instances": vote.participating_instances,
        "closes_at": vote.closes_at.isoformat()
    }


class CastVoteRequest(BaseModel):
    proposal_id: str
    decision: str  # e.g., "PASS", "REJECT", "VETO"

@router.post("/webhooks/votes/cast")
async def webhook_cast_federated_vote(
    request: Request,
    db: Session = Depends(get_db),
    peer=Depends(authenticate_peer),
):
    """
    Webhook: A peer instance sends their decision on a federated proposal here.
    """
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    req = CastVoteRequest(**data)
    
    success = FederationService.cast_federated_vote(
        db=db,
        proposal_id=req.proposal_id,
        peer_id=peer.id,
        decision=req.decision
    )
    return {"status": "success"}