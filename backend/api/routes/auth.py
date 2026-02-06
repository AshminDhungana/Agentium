"""
Authentication API for frontend.
Database-backed with user approval workflow.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.database import get_db
from backend.core.auth import create_access_token, verify_token, get_current_active_user
from backend.models.entities.user import User
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# Request/Response Models
class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)

class SignupResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[int] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class VerifyResponse(BaseModel):
    valid: bool
    user: Optional[dict] = None

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)

# Keep backward compatibility for sovereign credentials
# (for initial setup or emergency access)
SOVEREIGN_CREDENTIALS = {
    "admin": "admin"  # Change in production!
}

@router.post("/signup", response_model=SignupResponse)
async def signup(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    """
    User signup request.
    Creates a pending user account that requires admin approval.
    """
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.username == request.username) | 
        (User.email == request.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user (starts as pending/inactive)
    user = User.create_user(
        db=db,
        username=request.username,
        email=request.email,
        password=request.password
    )
    
    # Log the signup
    AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="user",
        actor_id=request.username,
        action="signup_request",
        description=f"New user registered: {request.username} (pending approval)",
        meta_data={
            "user_id": user.id,
            "email": request.email,
            "auto_approved": False
        }
    )
    
    return SignupResponse(
        success=True,
        message="Account created successfully. Awaiting admin approval.",
        user_id=user.id
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    User login with username and password.
    Returns JWT token for authenticated sessions.
    """
    # First try database authentication
    user = User.authenticate(db, request.username, request.password)
    
    # Fallback to sovereign credentials for backward compatibility
    if not user:
        if request.username in SOVEREIGN_CREDENTIALS:
            if SOVEREIGN_CREDENTIALS[request.username] == request.password:
                # For sovereign accounts, create a mock user object
                # In production, consider migrating sovereign users to database
                token_data = {
                    "sub": request.username,
                    "role": "sovereign",
                    "is_admin": True,
                    "is_active": True
                }
                access_token = create_access_token(token_data)
                
                # Log successful login
                AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.AUTHENTICATION,
                    actor_type="user",
                    actor_id=request.username,
                    action="login_success",
                    description="Sovereign user logged in successfully"
                )
                
                return LoginResponse(
                    access_token=access_token,
                    token_type="bearer",
                    user={
                        "username": request.username,
                        "role": "sovereign",
                        "is_admin": True
                    }
                )
        
        # Log failed login attempt
        AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.AUTHENTICATION,
            actor_type="user",
            actor_id=request.username,
            action="login_failed",
            description="Failed login attempt",
            success=False
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or account not approved"
        )
    
    # Check if user is active and approved
    if not user.is_active or user.is_pending:
        AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.AUTHENTICATION,
            actor_type="user",
            actor_id=request.username,
            action="login_failed_inactive",
            description="Login attempt on inactive/pending account",
            success=False,
            meta_data={
                "user_id": user.id,
                "is_active": user.is_active,
                "is_pending": user.is_pending
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending approval or deactivated"
        )
    
    # Create JWT token
    token_data = {
        "sub": user.username,
        "user_id": user.id,
        "role": "user",
        "is_admin": user.is_admin,
        "is_active": user.is_active
    }
    access_token = create_access_token(token_data)
    
    # Log successful login
    AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="user",
        actor_id=user.username,
        action="login_success",
        description="User logged in successfully",
        meta_data={
            "user_id": user.id,
            "is_admin": user.is_admin
        }
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=user.to_dict()
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_token_endpoint(
    token: str
):
    """
    Verify if a JWT token is valid.
    """
    payload = verify_token(token)
    
    if not payload:
        return VerifyResponse(valid=False)
    
    return VerifyResponse(
        valid=True,
        user={
            "username": payload.get("sub"),
            "user_id": payload.get("user_id"),
            "is_admin": payload.get("is_admin", False),
            "role": payload.get("role", "user")
        }
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Change own password.
    """
    # Get user from database
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify old password
    if not User.verify_password(request.old_password, user.hashed_password):
        AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.AUTHENTICATION,
            actor_type="user",
            actor_id=current_user["username"],
            action="password_change_failed",
            description="Password change failed - incorrect old password",
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    user.hashed_password = User.hash_password(request.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    
    AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="user",
        actor_id=current_user["username"],
        action="password_changed",
        description="Password changed successfully"
    )
    
    return {
        "status": "success",
        "message": "Password updated successfully"
    }