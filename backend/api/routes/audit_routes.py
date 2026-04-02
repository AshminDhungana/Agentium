from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.models.database import get_db
from backend.core.auth import get_current_user
from backend.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit"])

@router.get("/escalations")
async def get_escalations(
    skip: int = 0,
    limit: int = Query(100, le=1000),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get audit logs for privilege escalations and revocations.
    Only accessible by users with admin privileges.
    """
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Not authorized to view audit logs")

    logs, total = AuditService.get_escalations(db, skip=skip, limit=limit, search=search)
    
    return {
        "data": [log.to_dict() for log in logs],
        "total": total,
        "skip": skip,
        "limit": limit
    }
