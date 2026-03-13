"""
Plugin Marketplace API Routes
Endpoints for plugin developers and administrators to manage the ecosystem.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.services.plugin_marketplace_service import PluginMarketplaceService
from backend.api.routes.rbac import get_current_user_from_token
from backend.models.entities.user import User

router = APIRouter(prefix="/plugins", tags=["Plugin Marketplace"])


# --- Schemas ---

class PluginSubmitRequest(BaseModel):
    name: str
    description: str
    author: str
    version: str
    plugin_type: str
    entry_point: str
    source_url: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    dependencies: Optional[List[str]] = None

class PluginInstallRequest(BaseModel):
    config: Dict[str, Any]

class PluginReviewRequest(BaseModel):
    rating: int
    review_text: Optional[str] = None


# --- Public / User Endpoints ---

@router.get("")  # Matches /api/v1/plugins (no trailing slash ambiguity)
def list_plugins(
    query: Optional[str] = None,
    type_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all published plugins, with optional search and type filter."""
    plugins = PluginMarketplaceService.search_plugins(db, query, type_filter)
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "author": p.author,
            "version": p.version,
            "plugin_type": p.plugin_type,
            "rating": p.rating,
            "install_count": p.install_count,
            "status": p.status,
        }
        for p in plugins
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_plugin(
    request: PluginSubmitRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Submit a new plugin for Council review."""
    plugin = PluginMarketplaceService.submit_plugin(
        db=db,
        name=request.name,
        description=request.description,
        author=request.author,
        version=request.version,
        plugin_type=request.plugin_type,
        entry_point=request.entry_point,
        source_url=request.source_url,
        config_schema=request.config_schema,
        dependencies=request.dependencies,
    )
    return {"id": plugin.id, "status": plugin.status}


@router.post("/{plugin_id}/install")
def install_plugin(
    plugin_id: str,
    request: PluginInstallRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Install a published plugin for the current user."""
    installation = PluginMarketplaceService.install_plugin(
        db=db,
        plugin_id=plugin_id,
        config=request.config,
        user=current_user,
    )
    return {"id": installation.id, "is_active": installation.is_active}


@router.post("/{plugin_id}/reviews", status_code=status.HTTP_201_CREATED)
def submit_review(
    plugin_id: str,
    request: PluginReviewRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Submit a star rating and optional review text for an installed plugin."""
    if not (1 <= request.rating <= 5):
        raise HTTPException(status_code=422, detail="Rating must be between 1 and 5.")
    review = PluginMarketplaceService.submit_review(
        db, plugin_id, current_user, request.rating, request.review_text
    )
    return {"id": review.id, "rating": review.rating}


# --- Admin Endpoints ---

@router.post("/{plugin_id}/verify")
def verify_plugin(
    plugin_id: str,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Admin: Mark a submitted plugin as security-verified."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can verify plugins.")
    plugin = PluginMarketplaceService.verify_plugin(db, plugin_id, current_user)
    return {"id": plugin.id, "status": plugin.status}


@router.post("/{plugin_id}/publish")
def publish_plugin(
    plugin_id: str,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Admin: Publish a verified plugin to the public marketplace."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can publish plugins.")
    plugin = PluginMarketplaceService.publish_plugin(db, plugin_id, current_user)
    return {"id": plugin.id, "status": plugin.status}


@router.post("/{plugin_id}/request-approval")
def request_council_approval(
    plugin_id: str,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Developer: Request Council approval for a submitted plugin."""
    proposal_id = PluginMarketplaceService.request_council_approval(db, plugin_id)
    return {"status": "success", "proposal_id": proposal_id}


class ExecutePluginRequest(BaseModel):
    installation_id: str
    input_data: Dict[str, Any]

@router.post("/{plugin_id}/execute")
async def execute_plugin(
    plugin_id: str,
    request: ExecutePluginRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Execute a plugin within a secure sandbox."""
    # Ensure the user has the right to execute (e.g. they installed it)
    if not current_user.is_sovereign:
        raise HTTPException(status_code=403, detail="Only Sovereign can execute plugins manually.")
        
    result = await PluginMarketplaceService.execute_plugin_sandboxed(
        db=db, 
        installation_id=request.installation_id, 
        input_data=request.input_data
    )
    return result


class RevenueRecordRequest(BaseModel):
    amount: float
    currency: str = "USD"
    notes: str = ""

@router.post("/{plugin_id}/revenue")
def record_plugin_revenue(
    plugin_id: str,
    request: RevenueRecordRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Record a revenue transaction for a plugin on the ledger."""
    if not current_user.is_sovereign:
        raise HTTPException(status_code=403, detail="Only Sovereign can record revenue for plugins.")
        
    ledger = PluginMarketplaceService.record_revenue(
        db=db,
        plugin_id=plugin_id,
        amount=request.amount,
        currency=request.currency,
        notes=request.notes
    )
    return {
        "status": "success", 
        "ledger_id": ledger.id, 
        "amount": ledger.amount, 
        "currency": ledger.currency
    }