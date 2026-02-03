"""
Admin API for system configuration and user management.
Only accessible by Admin users.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from backend.models.database import get_db
from backend.api.dependencies.auth import get_current_admin_user
from backend.models.entities.user import User
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

# Response Models
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    is_pending: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int

class ActionResponse(BaseModel):
    success: bool
    message: str

class PasswordChangeRequest(BaseModel):
    new_password: str = Field(..., min_length=8)

# Helper function to convert User to response
def user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        is_pending=user.is_pending,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )

@router.get("/users/pending", response_model=UserListResponse)
async def get_pending_users(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Get all pending user approval requests.
    """
    pending_users = db.query(User).filter(
        User.is_pending == True
    ).order_by(User.created_at.desc()).all()
    
    return UserListResponse(
        users=[user_to_response(u) for u in pending_users],
        total=len(pending_users)
    )


@router.get("/users", response_model=UserListResponse)
async def get_all_users(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user),
    include_pending: bool = False
):
    """
    Get all approved users. Use include_pending=true to see all users.
    """
    query = db.query(User)
    
    if not include_pending:
        query = query.filter(User.is_pending == False)
    
    users = query.order_by(User.created_at.desc()).all()
    
    return UserListResponse(
        users=[user_to_response(u) for u in users],
        total=len(users)
    )


@router.post("/users/{user_id}/approve", response_model=ActionResponse)
async def approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Approve a pending user account.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_pending:
        return ActionResponse(
            success=False,
            message="User is already approved"
        )
    
    # Approve the user
    user.is_pending = False
    user.is_active = True
    user.updated_at = datetime.utcnow()
    db.commit()
    
    # Log the approval
    AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHORIZATION,
        actor_type="user",
        actor_id=current_admin["username"],
        action="user_approved",
        description=f"Approved user account: {user.username}",
        target_type="user",
        target_id=str(user.id),
        meta_data={
            "approved_by": current_admin["username"],
            "user_id": user.id,
            "username": user.username
        }
    )
    
    return ActionResponse(
        success=True,
        message=f"User {user.username} approved successfully"
    )


@router.post("/users/{user_id}/reject", response_model=ActionResponse)
async def reject_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Reject and deactivate a pending user account.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_pending:
        return ActionResponse(
            success=False,
            message="Can only reject pending users"
        )
    
    # Reject the user (deactivate)
    user.is_pending = False
    user.is_active = False
    user.updated_at = datetime.utcnow()
    db.commit()
    
    # Log the rejection
    AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.AUTHORIZATION,
        actor_type="user",
        actor_id=current_admin["username"],
        action="user_rejected",
        description=f"Rejected user account: {user.username}",
        target_type="user",
        target_id=str(user.id),
        meta_data={
            "rejected_by": current_admin["username"],
            "user_id": user.id,
            "username": user.username
        }
    )
    
    return ActionResponse(
        success=True,
        message=f"User {user.username} rejected successfully"
    )


@router.delete("/users/{user_id}", response_model=ActionResponse)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Delete a user account (soft delete by deactivating).
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent deleting self
    if user.username == current_admin["username"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Prevent deleting the last admin
    if user.is_admin:
        admin_count = db.query(User).filter(
            User.is_admin == True,
            User.is_active == True,
            User.id != user_id
        ).count()
        
        if admin_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last active admin"
            )
    
    # Deactivate user instead of hard delete
    user.is_active = False
    user.updated_at = datetime.utcnow()
    db.commit()
    
    # Log the deletion
    AuditLog.log(
        level=AuditLevel.CRITICAL,
        category=AuditCategory.AUTHORIZATION,
        actor_type="user",
        actor_id=current_admin["username"],
        action="user_deleted",
        description=f"Deleted user account: {user.username}",
        target_type="user",
        target_id=str(user.id),
        meta_data={
            "deleted_by": current_admin["username"],
            "user_id": user.id,
            "username": user.username,
            "was_admin": user.is_admin
        }
    )
    
    return ActionResponse(
        success=True,
        message=f"User {user.username} deleted successfully"
    )


@router.post("/users/{user_id}/change-password", response_model=ActionResponse)
async def admin_change_password(
    user_id: int,
    request: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Admin: Change any user's password.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.hashed_password = User.hash_password(request.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    
    # Log the password change
    AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.AUTHORIZATION,
        actor_type="user",
        actor_id=current_admin["username"],
        action="admin_password_change",
        description=f"Admin changed password for user: {user.username}",
        target_type="user",
        target_id=str(user.id),
        meta_data={
            "changed_by": current_admin["username"],
            "target_user_id": user.id,
            "target_username": user.username
        }
    )
    
    return ActionResponse(
        success=True,
        message=f"Password for user {user.username} updated successfully"
    )