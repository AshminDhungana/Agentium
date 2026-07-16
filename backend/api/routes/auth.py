"""
Authentication API for frontend.
Database-backed with user approval workflow.
"""
import os
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from time import time

from fastapi import APIRouter, Depends, status, Request
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from typing import Optional


from backend.models.database import get_db
from backend.core.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_active_user,
)
from backend.models.entities.user import User
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.core.voice_auth import create_voice_token
from backend.api.schemas.examples import ErrorResponseExample

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── Security scheme (for /verify header reading) ─────────────────────────────
_security = HTTPBearer(auto_error=False)

# ── B3: Simple in-memory login rate limiter ───────────────────────────────────
# Tracks failed login attempts per username.  Not distributed (single-process
# only), but effective for single-node deployments and requires zero external
# dependencies.  For multi-worker deployments, replace with Redis-backed
# slowapi or similar.
_login_attempts: defaultdict[str, list[float]] = defaultdict(list)
_attempts_lock = Lock()
_MAX_LOGIN_ATTEMPTS   = 5
_LOGIN_WINDOW_SECONDS = 300  # 5 minutes


def _check_rate_limit(identifier: str) -> None:
    """Raise HTTP 429 if the identifier has exceeded the allowed attempt count."""
    now = time()
    with _attempts_lock:
        # Prune attempts outside the rolling window
        _login_attempts[identifier] = [
            t for t in _login_attempts[identifier]
            if now - t < _LOGIN_WINDOW_SECONDS
        ]
        if len(_login_attempts[identifier]) >= _MAX_LOGIN_ATTEMPTS:
            raise RateLimitError(error=(
                    f"Too many failed login attempts. "
                    f"Please wait {_LOGIN_WINDOW_SECONDS // 60} minutes before trying again."
                ), code="FTOO_MANY_FAILED_LOGIN_ATTEMPTS", headers={"Retry-After": str(_LOGIN_WINDOW_SECONDS)})
        _login_attempts[identifier].append(now)


def _clear_rate_limit(identifier: str) -> None:
    """Reset the attempt counter after a successful login."""
    with _attempts_lock:
        _login_attempts.pop(identifier, None)


# ── Request / Response Models ─────────────────────────────────────────────────

class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)

class SignupResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class VerifyResponse(BaseModel):
    valid: bool
    user: Optional[dict] = None

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=SignupResponse,
    summary="Register a new user account",
    description="Creates a pending user account. Requires admin approval before login.\n\n**Rate limit:** 5 attempts per IP per 5 minutes.")  # noqa: D401
async def signup(
    request: Request,
    payload: SignupRequest,
    db: Session = Depends(get_db),
):
    """
    User signup request.
    Creates a pending user account that requires admin approval.
    """
    existing_user = db.query(User).filter(
        (User.username == payload.username) |
        (User.email == payload.email)
    ).first()

    if existing_user:
        raise BadRequestError(error="Username or email already registered", code="USERNAME_OR_EMAIL_ALREADY_REGISTERED")

    user = User.create_user(
        db=db,
        username=payload.username,
        email=payload.email,
        password=payload.password,
    )

    # C1: db.add() so this entry is actually persisted.
    audit_entry = AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="user",
        actor_id=payload.username,
        action="signup_request",
        description=f"New user registered: {payload.username} (pending approval)",
        meta_data={
            "user_id": user.id,
            "email": payload.email,
            "auto_approved": False,
        },
    )
    db.add(audit_entry)
    db.commit()

    return SignupResponse(
        success=True,
        message="Account created successfully. Awaiting admin approval.",
        user_id=user.id,
    )





@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate a user",
    description="Authenticate a user with username and password, returning a JWT access token.")
async def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    User login with username and password.
    Returns JWT token for authenticated sessions.
    """
    # B3: enforce rate limit before any credential check so that enumeration
    #     and brute-force attempts are blocked regardless of whether the
    #     username exists.
    _check_rate_limit(payload.username)

    # First try database authentication
    user = User.authenticate(db, payload.username, payload.password)

    if not user:
        # C1: persist failed login audit, then raise
        audit_entry = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.AUTHENTICATION,
            actor_type="user",
            actor_id=payload.username,
            action="login_failed",
            description="Failed login attempt",
            success=False,
        )
        db.add(audit_entry)
        db.commit()

        raise UnauthorizedError(error="Invalid credentials or account not approved", code="INVALID_CREDENTIALS_OR_ACCOUNT_NOT")

    # Check if user is active and approved
    if not user.is_active or user.is_pending:
        # C1: persist the inactive-login audit, then raise
        audit_entry = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.AUTHENTICATION,
            actor_type="user",
            actor_id=payload.username,
            action="login_failed_inactive",
            description="Login attempt on inactive/pending account",
            success=False,
            meta_data={
                "user_id": user.id,
                "is_active": user.is_active,
                "is_pending": user.is_pending,
            },
        )
        db.add(audit_entry)
        db.commit()

        raise ForbiddenError(error="Account pending approval or deactivated", code="ACCOUNT_PENDING_APPROVAL_OR_DEACTIVATED")

    # Successful DB login — clear rate-limit counter for this username
    _clear_rate_limit(payload.username)

    # D3: Record the last login timestamp
    user.last_login_at = datetime.now(timezone.utc)

    token_data = {
        "sub": user.username,
        "user_id": user.id,
        "role": "user",
        "is_admin": user.is_admin,
        "is_active": user.is_active,
    }
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # C1: persist the successful login audit in the same commit as last_login_at
    audit_entry = AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="user",
        actor_id=user.username,
        action="login_success",
        description="User logged in successfully",
        meta_data={"user_id": user.id, "is_admin": user.is_admin},
    )
    db.add(audit_entry)
    db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=user.to_dict(),
    )


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="Refresh an access token",
    description="Refresh an access token using a valid refresh token.")
async def refresh_token_endpoint(
    request: Request,
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    """Refresh access token using a valid refresh token."""
    token_payload = verify_token(payload.refresh_token)

    if not token_payload or token_payload.get("type") != "refresh":
        raise UnauthorizedError(error="Invalid or expired refresh token", code="INVALID_OR_EXPIRED_REFRESH_TOKEN", headers={"WWW-Authenticate": "Bearer"})

    username = token_payload.get("sub")
    if not username:
        raise UnauthorizedError(error="Invalid token payload", code="INVALID_TOKEN_PAYLOAD")

    token_data = {
        "sub": username,
        "user_id": token_payload.get("user_id"),
        "role": token_payload.get("role", "user"),
        "is_admin": token_payload.get("is_admin", False),
        "is_active": token_payload.get("is_active", True),
    }

    new_access_token  = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    user_dict = {
        "username": username,
        "role": token_data["role"],
        "is_admin": token_data["is_admin"],
    }

    if token_data["role"] != "sovereign" and token_data.get("user_id"):
        db_user = db.query(User).filter(User.id == token_data["user_id"]).first()
        if db_user:
            user_dict = db_user.to_dict()

    return LoginResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        user=user_dict,
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify a bearer token",
    description="Verify if the current bearer token is valid. Reads token from the Authorization header only.")
async def verify_token_endpoint(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    db: Session = Depends(get_db),
):
    """
    Verify if the current bearer token is valid.

    B2: The token is read exclusively from the Authorization header, NOT from
    a query parameter.  Tokens in query strings are recorded in server access
    logs, CDN logs, and browser history — a significant information-leak risk.

    The frontend sends the token via the Authorization header automatically
    (api.ts request interceptor), so no callers need to change.

    The GET /verify variant that accepted a token query param has been removed
    for the same reason.
    """
    if not credentials:
        return VerifyResponse(valid=False)

    payload = verify_token(credentials.credentials)

    if not payload:
        return VerifyResponse(valid=False)

    # Fetch the persisted user so profile fields not carried in the JWT
    # (e.g. avatar_url) are returned to the client on every session check.
    user = None
    user_id = payload.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()

    user_payload = {
        "username": payload.get("sub"),
        "user_id": user_id,
        "is_admin": payload.get("is_admin", False),
        "role": payload.get("role", "user"),
    }
    if user:
        user_payload["avatar_url"] = user.avatar_url

    return VerifyResponse(
        valid=True,
        user=user_payload,
    )

# B2: GET /verify endpoint removed — it accepted the JWT as a query parameter
#     (?token=<jwt>) which exposes the token in server logs, browser history,
#     and Referer headers.  The POST /verify endpoint above is the sole
#     verification route and reads from the Authorization header only.


@router.post(
    "/change-password", response_model=dict,
    summary="Change own password",
    description="Change the authenticated user's password. Requires current password for verification.")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Change own password."""
    if current_user.get("user_id") is None:
        raise BadRequestError(error="Emergency sovereign users cannot change password. Please use database admin account.", code="EMERGENCY_SOVEREIGN_USERS_CANNOT_CHANGE")

    user_id = current_user.get("user_id")
    if not user_id:
        raise BadRequestError(error="User ID not found in token", code="USER_ID_NOT_FOUND_IN")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError(error="User not found", code="USER_NOT_FOUND")

    if not User.verify_password(payload.old_password, user.hashed_password):
        # C1: persist failed audit, then raise
        audit_entry = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.AUTHENTICATION,
            actor_type="user",
            actor_id=current_user.get("username", "unknown"),
            action="password_change_failed",
            description="Password change failed - incorrect old password",
            success=False,
        )
        db.add(audit_entry)
        db.commit()

        raise BadRequestError(error="Current password is incorrect", code="CURRENT_PASSWORD_IS_INCORRECT")

    user.hashed_password = User.hash_password(payload.new_password)
    user.updated_at = datetime.now(timezone.utc)

    # C1: persist success audit in the same commit as the password change
    audit_entry = AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="user",
        actor_id=current_user.get("username", "unknown"),
        action="password_changed",
        description="Password changed successfully",
    )
    db.add(audit_entry)
    db.commit()

    return {"status": "success", "message": "Password updated successfully"}


class VoiceTokenResponse(BaseModel):
    voice_token: str
    expires_in_minutes: int


@router.post(
    "/voice-token", response_model=VoiceTokenResponse,
    summary="Issue a voice bridge token",
    description="Issue a short-lived voice-scoped JWT for the host-native voice bridge.")
async def get_voice_token(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Issue a short-lived voice-scoped JWT for the host-native voice bridge.

    The token is separate from the main session JWT so a leaked voice token
    cannot be used to access any other API.  Returns HTTP 503 if
    VOICE_JWT_SECRET is not configured in the environment.
    """
    try:
        token = create_voice_token(
            username=current_user.get("username", "unknown"),
            user_id=current_user.get("user_id"),
        )
    except RuntimeError as exc:
        raise ServiceUnavailableError(error=str(exc), code="STREXC")

    duration = int(os.getenv("VOICE_TOKEN_DURATION_MINUTES", "30"))

    # C1: persist the audit entry
    audit_entry = AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="user",
        actor_id=current_user.get("username", "unknown"),
        action="voice_token_issued",
        description="Voice bridge token issued",
        meta_data={"expires_in_minutes": duration},
    )
    db.add(audit_entry)
    db.commit()

    return VoiceTokenResponse(voice_token=token, expires_in_minutes=duration)


@router.get(
    "/verify-session", response_model=VerifyResponse,
    summary="Verify current session",
    description="Lightweight session check returning the authenticated user's basic profile.")
async def verify_session(
    current_user: dict = Depends(get_current_active_user),
):
    """
    Lightweight session check used by the voice bridge after connecting.
    Returns the authenticated user's basic profile if the bearer token is
    still valid, without requiring a separate token parameter.
    """
    return VerifyResponse(
        valid=True,
        user={
            "username": current_user.get("username"),
            "user_id": current_user.get("user_id"),
            "is_admin": current_user.get("is_admin", False),
            "role": current_user.get("role", "user"),
        },
    )