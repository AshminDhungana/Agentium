from fastapi import APIRouter, Depends, Query
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.models.database import get_db
from backend.core.auth import get_current_user
from backend.services.audit_service import AuditService

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/audit", tags=["Audit"])

@router.get(
    "/escalations",
    summary="Get Escalations",
    description="Get audit logs for privilege escalations and revocations. Only accessible by users with admin privileges.",
    responses=build_responses(None),
)
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
        raise ForbiddenError(error="Not authorized to view audit logs", code="NOT_AUTHORIZED_TO_VIEW_AUDIT")

    logs, total = AuditService.get_escalations(db, skip=skip, limit=limit, search=search)
    
    return {
        "data": [log.to_dict() for log in logs],
        "total": total,
        "skip": skip,
        "limit": limit
    }
