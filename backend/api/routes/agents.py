"""
API routes for Agent Management.
Provides endpoints for verifying and repairing genesis agents.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.services.initialization_service import InitializationService
from backend.api.middleware.auth import get_current_user
from backend.models.entities.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/verify")
async def verify_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify and repair missing genesis agents.
    
    Requires admin/sovereign access.
    
    Returns:
        Verification report with status, checked, missing, recreated, warnings, details.
    """
    # Check admin permission
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    init_service = InitializationService(db)
    result = await init_service.verify_and_repair(db)
    return result