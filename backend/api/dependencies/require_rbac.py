"""
RBAC dependencies for FastAPI route protection.

Provides reusable dependency factories that enforce capability-based or
role-based access control on any endpoint.

Usage::

    from backend.api.dependencies.require_rbac import require_permission, require_admin_or_sovereign

    @router.get("/sensitive")
    def sensitive_endpoint(user: User = Depends(require_permission("configure_agents"))):
        ...

    @router.post("/admin-action")
    def admin_action(user: User = Depends(require_admin_or_sovereign)):
        ...
"""

from typing import Tuple

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.user import User
from backend.api.middleware.auth import get_current_user as _get_current_user_orm
from backend.services.rbac_service import RBACService
from backend.core.exceptions import ForbiddenError


def require_permission(*capabilities: str):
    """
    FastAPI dependency factory that checks the current user has **all**
    of the specified capabilities.

    Returns the resolved ``User`` ORM object for downstream use.
    """
    async def _dependency(
        current_user: User = Depends(_get_current_user_orm),
    ) -> User:
        for cap in capabilities:
            if not RBACService.has_permission(current_user, cap):
                raise ForbiddenError(
                    error=f"Missing required capability: {cap}",
                    code="MISSING_CAPABILITY",
                )
        return current_user

    return _dependency


async def require_admin_or_sovereign(
    current_user: User = Depends(_get_current_user_orm),
) -> User:
    """
    FastAPI dependency that checks the current user is either an admin
    (``is_admin=True``) or the Primary Sovereign.

    Returns the resolved ``User`` ORM object.
    """
    if not (current_user.is_admin or current_user.is_sovereign):
        raise ForbiddenError(
            error="Admin or Sovereign privileges required.",
            code="ADMIN_OR_SOVEREIGN_REQUIRED",
        )
    return current_user
