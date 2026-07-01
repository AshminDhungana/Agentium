"""
Authentication dependencies for API routes.
"""

from fastapi import Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.database import get_db
from backend.core.auth import verify_token
from backend.models.entities.user import User
from backend.core.exceptions import UnauthorizedError, ForbiddenError

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[dict]:
    """
    Get the current authenticated user from JWT token.
    Returns None if no token provided.
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = verify_token(token)

    if not payload:
        raise UnauthorizedError(
            error="Invalid authentication token",
            code="INVALID_TOKEN",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user exists in database
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user:
        raise UnauthorizedError(
            error="User not found",
            code="USER_NOT_FOUND",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise ForbiddenError(
            error="User account is not active",
            code="ACCOUNT_INACTIVE",
        )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "is_pending": user.is_pending,
    }

async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Ensure user is authenticated and active."""
    if not current_user:
        raise UnauthorizedError(
            error="Not authenticated",
            code="NOT_AUTHENTICATED",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user

async def get_current_admin_user(
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Ensure user is an admin."""
    if not current_user.get("is_admin"):
        raise ForbiddenError(
            error="Admin privileges required",
            code="ADMIN_ONLY",
        )
    return current_user