"""
RBAC API Routes
Endpoints for managing roles and delegations.
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.user import User
from backend.services.rbac_service import RBACService, VALID_CAPABILITIES
from backend.core.auth import security

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/rbac", tags=["Role-Based Access Control"])


# --- Request/Response Schemas --- #

class DelegateRequest(BaseModel):
    grantee_id: str
    capabilities: List[str]
    expires_at: Optional[datetime] = None
    reason: Optional[str] = None

class EmergencyTransferRequest(BaseModel):
    new_sovereign_id: str
    reason: str


# --- Dependencies --- #

def get_current_user_from_token(
    db: Session = Depends(get_db),
    credentials=Depends(security)
) -> User:
    """
    Dependency to resolve the current user from a Bearer token.

    Uses the shared `security` (HTTPBearer) dependency to extract
    the raw token string, then delegates to the auth module's
    token-verification logic.
    """
    from backend.core.auth import verify_token

    token = credentials.credentials  # HTTPAuthorizationCredentials → str

    payload = verify_token(token)
    if not payload:
        raise UnauthorizedError(error="Invalid authentication credentials", code="INVALID_AUTHENTICATION_CREDENTIALS")

    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise UnauthorizedError(error="User not found", code="USER_NOT_FOUND")
    return user


# --- Endpoints --- #

@router.get(
    "/roles",
    summary="List Users With Roles",
    description="List all users and their roles (requires Sovereign).",
    responses=build_responses(None),
)
def list_users_with_roles(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """List all users and their roles (requires Sovereign)."""
    # Use is_sovereign property so role-expiry is respected, with is_admin
    # as a backward-compat fallback for users that pre-date the RBAC system.
    if not (current_user.is_sovereign or current_user.is_admin):
        raise ForbiddenError(error="Insufficient permissions.", code="INSUFFICIENT_PERMISSIONS")

    users = db.query(User).all()
    # Include delegation details for sovereign/admin callers
    include_delegations = current_user.is_sovereign or current_user.is_admin

    result = []
    for u in users:
        u_dict = u.to_dict()
        # Ensure effective_role is always present in the response
        u_dict.setdefault("effective_role", "observer")
        if include_delegations:
            active_dels = [
                d.to_dict()
                for d in getattr(u, "delegations_received", [])
                if d.is_active
            ]
            u_dict["active_delegations"] = active_dels
        result.append(u_dict)
    return result


@router.get(
    "/capabilities",
    summary="List Capabilities",
    description="Return the sorted list of capability strings that are valid for delegation. This is the authoritative source for the frontend capability picker — the UI should derive its selectable capabilities from this endpoint rather than maintaining its own hardcoded list.",
    responses=build_responses(None),
)
def list_capabilities(
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Return the sorted list of capability strings that are valid for delegation.

    This is the authoritative source for the frontend capability picker —
    the UI should derive its selectable capabilities from this endpoint rather
    than maintaining its own hardcoded list.
    """
    if not (current_user.is_sovereign or current_user.is_admin):
        raise ForbiddenError(error="Insufficient permissions.", code="INSUFFICIENT_PERMISSIONS")
    return sorted(VALID_CAPABILITIES)


@router.post(
    "/delegate",
    summary="Delegate Capability",
    description="Delegate capabilities to another user. Only Primary Sovereign.",
    responses=build_responses(None),
)
def delegate_capability(
    request: DelegateRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Delegate capabilities to another user. Only Primary Sovereign."""
    # Use is_sovereign (property, respects role expiry) for consistent guard
    if not current_user.is_sovereign:
        raise ForbiddenError(error="Only Sovereign can delegate capabilities.", code="ONLY_SOVEREIGN_CAN_DELEGATE_CAPABILITIES")
    try:
        delegation = RBACService.delegate_capabilities(
            db=db,
            grantor=current_user,
            grantee_id=request.grantee_id,
            capabilities=request.capabilities,
            expires_at=request.expires_at,
            reason=request.reason,
        )
        return delegation.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestError(error=str(e), code="STRE")


@router.delete(
    "/delegate/{delegation_id}",
    summary="Revoke Delegation",
    description="Revoke an active delegation.",
    responses=build_responses(None),
)
def revoke_delegation(
    delegation_id: str,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Revoke an active delegation."""
    try:
        delegation = RBACService.revoke_delegation(db, current_user, delegation_id)
        return delegation.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestError(error=str(e), code="STRE")


@router.post(
    "/emergency-transfer",
    summary="Emergency Override Transfer",
    description="Emergency transfer of Primary Sovereign role.",
    responses=build_responses(None),
)
def emergency_override_transfer(
    request: EmergencyTransferRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Emergency transfer of Primary Sovereign role."""
    if not current_user.is_sovereign:
        raise ForbiddenError(error="Only Sovereign can initiate emergency transfer.", code="ONLY_SOVEREIGN_CAN_INITIATE_EMERGENCY")
    try:
        delegation = RBACService.transfer_emergency_override(
            db=db,
            current_sovereign=current_user,
            new_sovereign_id=request.new_sovereign_id,
            reason=request.reason,
        )
        return {
            "success": True,
            "message": "Sovereignty transferred successfully",
            "delegation_record": delegation.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestError(error=str(e), code="STRE")


@router.get(
    "/permissions/me",
    summary="Get My Permissions",
    description="Get effective permissions for the current user.",
    responses=build_responses(None),
)
def get_my_permissions(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Get effective permissions for the current user."""
    perms = RBACService.get_effective_permissions(current_user)
    return {
        "user_id": current_user.id,
        "role": getattr(current_user, "effective_role", "observer"),
        "effective_permissions": list(perms),
    }