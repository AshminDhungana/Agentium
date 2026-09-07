"""
Constitution API routes for Agentium.
Handles constitution retrieval, updates, and sovereign preferences.
"""
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import json

from backend.models.database import get_db
from backend.models.entities.constitution import Constitution
from backend.core.auth import get_current_active_user
from backend.api.schemas.examples import build_responses
from backend.core.exceptions import ForbiddenError

router = APIRouter(prefix="/constitution", tags=["constitution"])


class ConstitutionUpdate(BaseModel):
    preamble: str = Field(..., min_length=1)
    articles: Dict[str, Any] = Field(default_factory=dict)
    prohibited_actions: List[str] = Field(default_factory=list)
    sovereign_preferences: Dict[str, Any] = Field(default_factory=dict)


class PreferencesUpdate(BaseModel):
    communication_style: Optional[str] = None
    response_format: Optional[str] = None
    verbosity: Optional[str] = None
    country_name: Optional[str] = None


@router.get(
    "",
    response_model=dict,
    summary="Get Active Constitution",
    description="Returns the currently active constitution with all sections.",
    responses=build_responses(None),
)
async def get_constitution(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get the active constitution."""
    constitution = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    
    if not constitution:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    return constitution.to_dict()


@router.post(
    "/update",
    response_model=dict,
    summary="Update Constitution",
    description="Creates a new constitution version, archiving the previous one. Requires admin/sovereign.",
    responses=build_responses(None),
)
async def update_constitution(
    update: ConstitutionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise ForbiddenError(error="Requires admin or sovereign access", code="REQUIRES_ADMIN_OR_SOVEREIGN")
    """Update constitution by creating new version."""
    if not update.preamble or not update.preamble.strip():
        raise HTTPException(status_code=400, detail="Preamble cannot be empty")
    
    # Get current active constitution
    current = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    
    if not current:
        raise HTTPException(status_code=404, detail="No active constitution to update")
    
    # Archive current
    current.archive()
    db.flush()
    
    # Create new version
    new_version_number = current.version_number + 1
    new_version = f"v{new_version_number}.0.0"
    
    new_constitution = Constitution(
        agentium_id=f"C{new_version_number:04d}",
        version=new_version,
        version_number=new_version_number,
        preamble=update.preamble,
        articles=json.dumps(update.articles),
        prohibited_actions=json.dumps(update.prohibited_actions),
        sovereign_preferences=json.dumps(update.sovereign_preferences),
        created_by_agentium_id=current.created_by_agentium_id,
        replaces_version_id=current.id,
        is_active=True,
    )
    
    db.add(new_constitution)
    db.flush()
    db.commit()
    
    return new_constitution.to_dict()


@router.post(
    "/preferences",
    response_model=dict,
    summary="Update Sovereign Preferences",
    description="Updates only the sovereign_preferences section of the active constitution.",
    responses=build_responses(None),
)
async def update_preferences(
    prefs: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Update sovereign preferences."""
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise ForbiddenError(error="Requires admin or sovereign access", code="REQUIRES_ADMIN_OR_SOVEREIGN")
    constitution = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    
    if not constitution:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    # Merge with existing preferences
    current_prefs = constitution.get_sovereign_preferences()
    update_data = prefs.model_dump(exclude_unset=True)
    merged = {**current_prefs, **update_data}
    
    constitution.sovereign_preferences = json.dumps(merged)
    db.commit()
    
    return constitution.to_dict()


@router.get(
    "/history",
    response_model=List[dict],
    summary="Get Constitution Amendment History",
    description="Returns history of constitutional amendments via voting service.",
    responses=build_responses(None),
)
async def get_constitution_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get amendment history."""
    from backend.services.amendment_service import AmendmentService
    
    service = AmendmentService(db)
    await service.initialize()
    history = await service.get_amendment_history(limit=limit)
    
    return history