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
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.services.push_notification_service import PushNotificationService
from backend.api.routes.rbac import get_current_user_from_token
from backend.models.entities.user import User

router = APIRouter(prefix="/mobile", tags=["Mobile API"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class DeviceRegistrationRequest(BaseModel):
    platform: str  # "ios" or "android"
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

@router.post("/register-device", response_model=DeviceRegistrationResponse)
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

@router.delete("/register-device/{token}")
def unregister_device(
    token: str,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Unregister a push notification token."""
    PushNotificationService.unregister_device(db, current_user, token)
    return {"success": True}


# ── Notification Preferences ──────────────────────────────────────────────────

@router.get("/notifications/preferences")
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

@router.put("/notifications/preferences")
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

@router.get("/dashboard")
def get_mobile_dashboard(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Condensed dashboard summary optimised for mobile.
    Returns raw counts and high-level statuses to minimise payload size.
    """
    from backend.models.entities.agents import Agent
    from backend.models.entities.task import Task
    from backend.models.entities.voting import AmendmentVoting

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
        "unread_notifications": 0  # Stub until notification centre is built
    }


# ── Mobile Task List ─────────────────────────────────────────────────────────

@router.get("/tasks")
def get_mobile_tasks(
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = None,
    hide_system: bool = True,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Paginated task list returning only essential fields for mobile list views."""
    from backend.models.entities.task import Task

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

@router.get("/agents")
def get_mobile_agents(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Condensed agent list for mobile views (type, status, name only)."""
    from backend.models.entities.agents import Agent

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

@router.get("/votes/active")
def get_active_votes(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """Return active votes with basic metadata for mobile push alert badges."""
    from backend.models.entities.voting import AmendmentVoting

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

@router.get("/offline/constitution")
def get_offline_constitution(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Return the active constitution text for offline caching.
    Mobile clients should periodically refresh this and store locally.
    """
    from backend.models.entities.constitution import Constitution

    constitution = db.query(Constitution).filter(
        Constitution.is_active == True
    ).order_by(Constitution.version.desc()).first()

    if not constitution:
        return {"version": 0, "content": "", "cached_at": None}

    return {
        "version": constitution.version,
        "preamble": constitution.preamble if hasattr(constitution, 'preamble') else "",
        "articles": constitution.articles if hasattr(constitution, 'articles') else {},
        "cached_at": datetime.utcnow().isoformat(),
    }

# Need datetime for the cached_at field
from datetime import datetime

@router.get("/offline/task-queue")
def get_offline_task_queue(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    """
    Return queued/pending tasks for offline viewing.
    Mobile clients can display these when connectivity is lost.
    """
    from backend.models.entities.task import Task

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
        "synced_at": datetime.utcnow().isoformat(),
        "total_queued": len(tasks),
    }