"""
User Preferences API Routes.
REST endpoints for frontend to manage preferences.
"""

from typing import Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.models.database import get_db
from backend.core.auth import get_current_active_user, get_current_agent_tier, get_current_agent_id
from backend.services.user_preference_service import UserPreferenceService, PreferenceCategory


router = APIRouter(prefix="/preferences", tags=["User Preferences"], redirect_slashes=False)


# ═══════════════════════════════════════════════════════════
# Request/Response Schemas
# ═══════════════════════════════════════════════════════════

class PreferenceCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, description="Hierarchical preference key")
    value: Any = Field(..., description="Preference value (any JSON-serializable type)")
    category: str = Field(default=PreferenceCategory.GENERAL, description="Preference category")
    scope: str = Field(default="global", description="Scope: global, agent, task")
    scope_target_id: Optional[str] = Field(None, description="Target ID for scoped preferences")
    description: Optional[str] = Field(None, description="Human-readable description")
    editable_by_agents: bool = Field(default=True, description="Allow agents to modify")


class PreferenceUpdateRequest(BaseModel):
    value: Any = Field(..., description="New preference value")
    reason: Optional[str] = Field(None, description="Reason for change")


class PreferenceBulkUpdateRequest(BaseModel):
    preferences: Dict[str, Any] = Field(..., description="Map of keys to values")
    reason: Optional[str] = Field(None, description="Reason for bulk update")


class PreferenceResponse(BaseModel):
    agentium_id: str
    key: str
    value: Any
    category: str
    scope: str
    data_type: str
    editable: bool
    description: Optional[str]
    last_modified_by_agent: Optional[str]
    last_agent_modified_at: Optional[str]


# ═══════════════════════════════════════════════════════════
# User Endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/")
@router.get("")  # also handles GET /api/v1/preferences (no trailing slash — prevents 307 redirect through Vite proxy)
async def list_my_preferences(
    category: Optional[str] = None,
    scope: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """List all preferences for the current user."""
    service = UserPreferenceService(db)
    prefs = service.get_all_preferences(
        user_id=current_user["user_id"],
        category=category,
        scope=scope,
        include_system=True
    )

    # Return a plain array — frontend unwrap logic handles both array and envelope shapes
    return [p.to_dict() for p in prefs]


@router.get("/{key}")
async def get_my_preference(
    key: str,
    default: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get a specific preference value."""
    service = UserPreferenceService(db)
    value = service.get_value(key, user_id=current_user["user_id"], default=default)

    if value is None and default is None:
        raise HTTPException(status_code=404, detail=f"Preference '{key}' not found")

    return {
        "key": key,
        "value": value,
        "default_used": value == default
    }


@router.post("/")
@router.post("")  # also handles POST /api/v1/preferences (no trailing slash — prevents 307 redirect)
async def create_preference(
    request: PreferenceCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Create a new preference."""
    service = UserPreferenceService(db)

    pref = service.set_preference(
        key=request.key,
        value=request.value,
        user_id=current_user["user_id"],
        category=request.category,
        scope=request.scope,
        scope_target_id=request.scope_target_id,
        description=request.description,
        editable_by_agents=request.editable_by_agents
    )

    return {
        "status": "created",
        "preference": pref.to_dict()
    }


@router.put("/{key}")
async def update_preference(
    key: str,
    request: PreferenceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Update an existing preference."""
    service = UserPreferenceService(db)

    # Check if exists
    existing = service.get_preference(key, user_id=current_user["user_id"])
    if not existing:
        raise HTTPException(status_code=404, detail=f"Preference '{key}' not found")

    pref = service.set_preference(
        key=key,
        value=request.value,
        user_id=current_user["user_id"],
        change_reason=request.reason
    )

    return {
        "status": "updated",
        "preference": pref.to_dict()
    }


@router.delete("/{key}")
async def delete_preference(
    key: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Soft-delete a preference."""
    service = UserPreferenceService(db)

    success = service.delete_preference(key, user_id=current_user["user_id"])
    if not success:
        raise HTTPException(status_code=404, detail=f"Preference '{key}' not found")

    return {
        "status": "deleted",
        "key": key
    }


@router.post("/bulk")
async def bulk_update_preferences(
    request: PreferenceBulkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Update multiple preferences at once."""
    service = UserPreferenceService(db)

    results = {"success": [], "failed": []}

    for key, value in request.preferences.items():
        try:
            service.set_preference(
                key=key,
                value=value,
                user_id=current_user["user_id"],
                change_reason=request.reason
            )
            results["success"].append(key)
        except Exception as e:
            results["failed"].append({"key": key, "error": str(e)})

    return {
        "status": "partial_success" if results["failed"] else "success",
        "results": results
    }


# ═══════════════════════════════════════════════════════════
# System/Default Endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/system/defaults")
async def get_default_preferences():
    """Get system default preferences."""
    return {
        "defaults": UserPreferenceService.DEFAULT_PREFERENCES,
        "categories": {
            PreferenceCategory.GENERAL: "General system preferences",
            PreferenceCategory.UI: "User interface settings",
            PreferenceCategory.NOTIFICATIONS: "Notification preferences",
            PreferenceCategory.AGENTS: "Agent behavior settings",
            PreferenceCategory.TASKS: "Task execution preferences",
            PreferenceCategory.CHAT: "Chat and messaging settings",
            PreferenceCategory.MODELS: "AI model configuration",
            PreferenceCategory.TOOLS: "Tool execution settings",
            PreferenceCategory.PRIVACY: "Privacy and data settings",
            PreferenceCategory.CUSTOM: "Custom user-defined preferences",
        }
    }


@router.post("/system/initialize")
async def initialize_defaults(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Initialize default preferences for current user."""
    service = UserPreferenceService(db)

    prefs = service.initialize_user_defaults(current_user["user_id"])

    return {
        "status": "initialized",
        "count": len(prefs),
        "preferences": [p.to_dict() for p in prefs]
    }


# ═══════════════════════════════════════════════════════════
# Agent Tool Endpoints (for tool registry)
# ═══════════════════════════════════════════════════════════

@router.get("/agent/list")
async def agent_list_preferences(
    category: Optional[str] = None,
    include_values: bool = True,
    db: Session = Depends(get_db),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
    current_user: dict = Depends(get_current_active_user)
):
    """
    List preferences accessible to the calling agent.
    Used by agent tools to discover available preferences.
    """
    from backend.tools.user_preference_tool import user_preference_tool

    result = user_preference_tool.list_preferences(
        agent_tier=agent_tier,
        agent_id=agent_id,
        user_id=current_user.get("id"),
        category=category,
        include_values=include_values
    )

    if result["status"] == "error":
        raise HTTPException(status_code=403, detail=result["error"])

    return result


@router.get("/agent/get/{key}")
async def agent_get_preference(
    key: str,
    default: Optional[Any] = None,
    db: Session = Depends(get_db),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
    current_user: dict = Depends(get_current_active_user)
):
    """Agent tool endpoint to get a preference."""
    from backend.tools.user_preference_tool import user_preference_tool

    result = user_preference_tool.get_preference(
        key=key,
        agent_tier=agent_tier,
        agent_id=agent_id,
        user_id=current_user.get("id"),
        default=default
    )

    if result["status"] == "error":
        raise HTTPException(status_code=403, detail=result["error"])

    return result


@router.post("/agent/set/{key}")
async def agent_set_preference(
    key: str,
    value: Any,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
    current_user: dict = Depends(get_current_active_user)
):
    """Agent tool endpoint to set a preference."""
    from backend.tools.user_preference_tool import user_preference_tool

    result = user_preference_tool.set_preference(
        key=key,
        value=value,
        agent_tier=agent_tier,
        agent_id=agent_id,
        user_id=current_user.get("id"),
        reason=reason
    )

    if result["status"] == "error":
        raise HTTPException(status_code=403, detail=result["error"])

    return result


# ═══════════════════════════════════════════════════════════
# Admin/Optimization Endpoints
# ═══════════════════════════════════════════════════════════

@router.post("/admin/optimize")
async def optimize_preferences(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Run preference optimization (remove duplicates, clean unused).
    Admin only.
    """
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    service = UserPreferenceService(db)
    results = service.optimize_preferences()

    return {
        "status": "optimized",
        "results": results
    }


@router.get("/admin/recommendations")
async def get_optimization_recommendations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get optimization recommendations. Admin only."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    service = UserPreferenceService(db)
    recommendations = service.get_optimization_recommendations()

    return {
        "count": len(recommendations),
        "recommendations": recommendations
    }


@router.get("/admin/history/{preference_id}")
async def get_preference_history(
    preference_id: str,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get change history for a preference. Admin only."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from backend.models.entities.user_preference import UserPreferenceHistory

    history = db.query(UserPreferenceHistory).filter(
        UserPreferenceHistory.preference_id == preference_id,
        UserPreferenceHistory.is_active == True
    ).order_by(UserPreferenceHistory.created_at.desc()).limit(limit).all()

    return {
        "preference_id": preference_id,
        "count": len(history),
        "history": [h.to_dict() for h in history]
    }