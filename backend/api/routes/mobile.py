"""
Mobile API Routes
Mobile-optimized endpoints for future iOS/Android clients.

Endpoints:
- Device registration / unregistration
- Condensed dashboard, task list, and agent list
- Notification preferences management
- Offline sync (constitution cache, task queue)
- Active votes for push alerts
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Literal, Optional

from fastapi import APIRouter, Depends, status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.routes.rbac import get_current_user_from_token
from backend.models.database import get_db
from backend.models.entities.agents import Agent
from backend.models.entities.constitution import Constitution
from backend.models.entities.task import Task
from backend.models.entities.user import User
from backend.models.entities.voting import AmendmentVoting
from backend.services.push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/mobile", tags=["Mobile API"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class DeviceRegistrationRequest(BaseModel):
    # Literal enforces the valid values at the Pydantic validation layer,
    # producing a clean 422 before the request ever reaches the service.
    platform: Literal["ios", "android"]
    token: str

class DeviceRegistrationResponse(BaseModel):
    id: str
    status: str

class NotificationPreferencesRequest(BaseModel):
    votes_enabled: Optional[bool] = None
    alerts_enabled: Optional[bool] = None
    tasks_enabled: Optional[bool] = None
    constitutional_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


# ── Device Registration ───────────────────────────────────────────────────────

@router.post(
    "/register-device",
    response_model=DeviceRegistrationResponse,
    summary="Register Device",
    description="Register a mobile device token for push notifications.",
    responses=build_responses(None),
)
def register_device(
    request: DeviceRegistrationRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Register a mobile device token for push notifications."""
    device = PushNotificationService.register_device(
        db=db,
        user=current_user,
        platform=request.platform,
        token=request.token
    )
    return {"id": device.id, "status": "active"}


@router.delete(
    "/register-device/{token}",
    summary="Unregister Device",
    description="Unregister a push notification token.",
    responses=build_responses(None),
)
def unregister_device(
    token: str,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Unregister a push notification token."""
    PushNotificationService.unregister_device(db, current_user, token)
    return {"success": True}


# ── Device List ───────────────────────────────────────────────────────────────

@router.get(
    "/devices",
    summary="Get Devices",
    description="Return all active registered device tokens for the current user. Used by the Mobile page Devices tab to populate the device list.",
    responses=build_responses(None),
)
def get_devices(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Return all active registered device tokens for the current user.
    Used by the Mobile page Devices tab to populate the device list.
    """
    from backend.models.entities.mobile import DeviceToken

    devices = (
        db.query(DeviceToken)
        .filter(
            DeviceToken.user_id == current_user.id,
            DeviceToken.is_active == True,  # noqa: E712
        )
        .order_by(DeviceToken.registered_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "platform": d.platform,
            "token": d.token,
            "registered_at": d.registered_at.isoformat() if d.registered_at else None,
        }
        for d in devices
    ]


# ── Notification Preferences ──────────────────────────────────────────────────

@router.get(
    "/notifications/preferences",
    summary="Get Notification Preferences",
    description="Get notification preferences for the current user.",
    responses=build_responses(None),
)
def get_notification_preferences(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Get notification preferences for the current user."""
    pref = PushNotificationService.get_preferences(db, current_user.id)
    return {
        "votes_enabled": pref.votes_enabled,
        "alerts_enabled": pref.alerts_enabled,
        "tasks_enabled": pref.tasks_enabled,
        "constitutional_enabled": pref.constitutional_enabled,
        "quiet_hours_start": pref.quiet_hours_start,
        "quiet_hours_end": pref.quiet_hours_end,
    }


@router.put(
    "/notifications/preferences",
    summary="Update Notification Preferences",
    description="Update notification preferences for the current user.",
    responses=build_responses(None),
)
def update_notification_preferences(
    request: NotificationPreferencesRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Update notification preferences for the current user."""
    pref = PushNotificationService.update_preferences(
        db=db,
        user_id=current_user.id,
        votes_enabled=request.votes_enabled,
        alerts_enabled=request.alerts_enabled,
        tasks_enabled=request.tasks_enabled,
        constitutional_enabled=request.constitutional_enabled,
        quiet_hours_start=request.quiet_hours_start,
        quiet_hours_end=request.quiet_hours_end,
    )
    return {
        "votes_enabled": pref.votes_enabled,
        "alerts_enabled": pref.alerts_enabled,
        "tasks_enabled": pref.tasks_enabled,
        "constitutional_enabled": pref.constitutional_enabled,
        "quiet_hours_start": pref.quiet_hours_start,
        "quiet_hours_end": pref.quiet_hours_end,
    }


# ── Mobile Dashboard ─────────────────────────────────────────────────────────

@router.get(
    "/dashboard",
    summary="Get Mobile Dashboard",
    description="Condensed dashboard summary optimised for mobile. Returns raw counts and high-level statuses to minimise payload size.",
    responses=build_responses(None),
)
def get_mobile_dashboard(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Condensed dashboard summary optimised for mobile.
    Returns raw counts and high-level statuses to minimise payload size.
    """
    active_agents = db.query(Agent).filter(Agent.status == 'active').count()
    pending_tasks = db.query(Task).filter(Task.status == 'pending').count()
    failed_tasks = db.query(Task).filter(Task.status == 'failed').count()
    active_votes = db.query(AmendmentVoting).filter(AmendmentVoting.status == 'voting').count()

    return {
        "status": "online",
        "active_agents": active_agents,
        "tasks": {
            "pending": pending_tasks,
            "failed": failed_tasks
        },
        "active_votes": active_votes,
        "role": current_user.effective_role,
        "unread_notifications": 0
    }


# ── Mobile Task List ─────────────────────────────────────────────────────────

@router.get(
    "/tasks",
    summary="Get Mobile Tasks",
    description="Paginated task list returning only essential fields for mobile list views.",
    responses=build_responses(None),
)
def get_mobile_tasks(
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = None,
    hide_system: bool = True,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Paginated task list returning only essential fields for mobile list views."""
    query = db.query(Task)

    # User isolation: only return tasks created by this user
    query = query.filter(Task.created_by == str(current_user.id))

    # Exclude idle/system tasks by default
    if hide_system:
        query = query.filter(Task.is_idle_task != True)  # noqa: E712

    if status_filter:
        query = query.filter(Task.status == status_filter)

    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()

    return [
        {
            "id": t.id,
            "description": t.description[:100] + "..." if len(t.description) > 100 else t.description,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None
        } for t in tasks
    ]


# ── Mobile Agent List ────────────────────────────────────────────────────────

@router.get(
    "/agents",
    summary="Get Mobile Agents",
    description="Condensed agent list for mobile views (type, status, name only).",
    responses=build_responses(None),
)
def get_mobile_agents(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Condensed agent list for mobile views (type, status, name only)."""
    agents = db.query(Agent).filter(Agent.status == 'active').all()
    return [
        {
            "id": a.id,
            "agentium_id": a.agentium_id,
            "name": a.name,
            "agent_type": a.agent_type,
            "status": a.status,
        } for a in agents
    ]


# ── Active Votes (Push Alert Source) ─────────────────────────────────────────

@router.get(
    "/votes/active",
    summary="Get Active Votes",
    description="Return active votes with basic metadata for mobile push alert badges.",
    responses=build_responses(None),
)
def get_active_votes(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Return active votes with basic metadata for mobile push alert badges."""
    votes = db.query(AmendmentVoting).filter(
        AmendmentVoting.status == 'voting'
    ).order_by(AmendmentVoting.created_at.desc()).all()

    return [
        {
            "id": v.id,
            "title": v.title if hasattr(v, 'title') else "Amendment Vote",
            "status": v.status,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "closes_at": v.voting_deadline.isoformat() if hasattr(v, 'voting_deadline') and v.voting_deadline else None,
        } for v in votes
    ]


# ── Offline Sync Endpoints ───────────────────────────────────────────────────

@router.get(
    "/offline/constitution",
    summary="Get Offline Constitution",
    description="Return the active constitution text for offline caching. Mobile clients should periodically refresh this and store locally.",
    responses=build_responses(None),
)
def get_offline_constitution(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Return the active constitution text for offline caching.
    Mobile clients should periodically refresh this and store locally.
    """
    constitution = db.query(Constitution).filter(
        Constitution.is_active == True  # noqa: E712
    ).order_by(Constitution.version.desc()).first()

    if not constitution:
        return {"version": 0, "content": "", "cached_at": None}

    return {
        "version": constitution.version,
        "preamble": constitution.preamble if hasattr(constitution, 'preamble') else "",
        "articles": constitution.articles if hasattr(constitution, 'articles') else {},
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/offline/task-queue",
    summary="Get Offline Task Queue",
    description="Return queued/pending tasks for offline viewing. Mobile clients can display these when connectivity is lost.",
    responses=build_responses(None),
)
def get_offline_task_queue(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Return queued/pending tasks for offline viewing.
    Mobile clients can display these when connectivity is lost.
    """
    tasks = db.query(Task).filter(
        Task.status.in_(['pending', 'in_progress'])
    ).order_by(Task.created_at.desc()).limit(50).all()

    return {
        "tasks": [
            {
                "id": t.id,
                "description": t.description[:150] if t.description else "",
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            } for t in tasks
        ],
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total_queued": len(tasks),
    }


# ── Offline Delta Sync ───────────────────────────────────────────────────────

class OfflineSyncRequest(BaseModel):
    last_sync_at: Optional[str] = None  # ISO-8601 timestamp
    cached_constitution_version: Optional[int] = None
    cached_task_ids: Optional[List[str]] = None


@router.post(
    "/offline/sync",
    summary="Offline Delta Sync",
    description="Receives a client-side sync manifest and returns only data that has changed since the client's last sync timestamp.",
    responses=build_responses(None),
)
def offline_delta_sync(
    request: OfflineSyncRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Receives a client-side sync manifest and returns only data that has
    changed since the client's last sync timestamp.
    """
    result: Dict[str, Any] = {"synced_at": datetime.now(timezone.utc).isoformat()}

    # Parse last sync time
    last_sync = None
    if request.last_sync_at:
        try:
            last_sync = datetime.fromisoformat(request.last_sync_at)
        except ValueError:
            pass

    # Constitution delta
    constitution = db.query(Constitution).filter(
        Constitution.is_active == True  # noqa: E712
    ).order_by(Constitution.version.desc()).first()

    if constitution:
        if (
            request.cached_constitution_version is None
            or constitution.version != request.cached_constitution_version
        ):
            result["constitution"] = {
                "version": constitution.version,
                "preamble": constitution.preamble if hasattr(constitution, 'preamble') else "",
                "articles": constitution.articles if hasattr(constitution, 'articles') else {},
            }

    # Task delta — only tasks changed since last sync
    task_query = db.query(Task).filter(
        Task.created_by == str(current_user.id)
    )
    if last_sync:
        task_query = task_query.filter(Task.updated_at > last_sync)

    changed_tasks = task_query.order_by(Task.updated_at.desc()).limit(100).all()
    result["tasks"] = [
        {
            "id": t.id,
            "description": t.description[:150] if t.description else "",
            "status": t.status,
            "priority": t.priority,
            "updated_at": t.updated_at.isoformat() if hasattr(t, 'updated_at') and t.updated_at else None,
        } for t in changed_tasks
    ]
    result["total_changed"] = len(changed_tasks)

    return result


# ── Voice Commands ───────────────────────────────────────────────────────────

class VoiceCommandRequest(BaseModel):
    transcribed_text: str
    language: str = "en"


@router.post(
    "/voice-command",
    summary="Voice Command",
    description="Accepts transcribed voice text from mobile clients, routes it to the agent orchestrator, and returns the textual response.",
    responses=build_responses(None),
)
async def voice_command(
    request: VoiceCommandRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Accepts transcribed voice text from mobile clients, routes it to the
    agent orchestrator, and returns the textual response.
    """
    if not request.transcribed_text.strip():
        raise BadRequestError(error="Transcribed text cannot be empty.", code="TRANSCRIBED_TEXT_CANNOT_BE_EMPTY")

    try:
        from backend.services.agent_orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator(db)
        response = await orchestrator.route_message(
            message=request.transcribed_text,
            user_id=str(current_user.id),
            channel="mobile_voice",
            metadata={"language": request.language}
        )
        return {
            "status": "success",
            "response": response.get("reply", "") if isinstance(response, dict) else str(response),
            "source": "voice_command"
        }
    except Exception as e:
        logger.error(f"Voice command error: {e}")
        return {
            "status": "error",
            "response": "Sorry, I couldn't process your voice command at this time.",
            "error": str(e)
        }