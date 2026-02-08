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
from backend.services.token_optimizer import idle_budget  # Import the global budget manager

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

# Budget Models - Match existing BudgetControl.tsx interface
class BudgetLimits(BaseModel):
    daily_token_limit: int
    daily_cost_limit: float

class BudgetUsage(BaseModel):
    tokens_used_today: int
    tokens_remaining: int
    cost_used_today_usd: float
    cost_remaining_usd: float
    cost_percentage_used: float
    cost_percentage_tokens: float

class OptimizerStatus(BaseModel):
    idle_mode_active: bool
    time_since_last_activity_seconds: float

class BudgetStatus(BaseModel):
    current_limits: BudgetLimits
    usage: BudgetUsage
    can_modify: bool
    optimizer_status: OptimizerStatus

class BudgetUpdateRequest(BaseModel):
    daily_token_limit: int = Field(..., ge=1000, le=10000000)
    daily_cost_limit: float = Field(..., ge=0, le=1000)

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

# Budget Endpoints
@router.get("/budget", response_model=BudgetStatus)
async def get_budget(
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Get current API budget status from token optimizer.
    Matches the interface expected by BudgetControl.tsx component.
    """
    try:
        # Get budget status from the global idle_budget manager
        budget_status = idle_budget.get_status()
        
        # Calculate token percentage
        token_percentage = (
            (budget_status['tokens_used'] / budget_status['tokens_limit']) * 100
            if budget_status['tokens_limit'] > 0 else 0
        )
        
        # Calculate cost percentage
        cost_percentage = (
            (budget_status['cost_used'] / budget_status['cost_limit']) * 100
            if budget_status['cost_limit'] > 0 else 0
        )
        
        # Get idle mode status
        idle_mode_active = getattr(idle_budget, 'idle_mode_active', False)
        time_since_activity = getattr(idle_budget, 'time_since_last_activity', 0)
        
        return BudgetStatus(
            current_limits=BudgetLimits(
                daily_token_limit=budget_status['tokens_limit'],
                daily_cost_limit=budget_status['cost_limit']
            ),
            usage=BudgetUsage(
                tokens_used_today=budget_status['tokens_used'],
                tokens_remaining=budget_status['tokens_remaining'],
                cost_used_today_usd=budget_status['cost_used'],
                cost_remaining_usd=budget_status['cost_remaining'],
                cost_percentage_used=round(cost_percentage, 2),
                cost_percentage_tokens=round(token_percentage, 2)
            ),
            can_modify=current_admin.get("is_admin", False),
            optimizer_status=OptimizerStatus(
                idle_mode_active=idle_mode_active,
                time_since_last_activity_seconds=time_since_activity
            )
        )
        
    except Exception as e:
        # Fallback to safe defaults if budget manager is not available
        print(f"Budget fetch error: {e}")
        return BudgetStatus(
            current_limits=BudgetLimits(
                daily_token_limit=100000,
                daily_cost_limit=5.0
            ),
            usage=BudgetUsage(
                tokens_used_today=0,
                tokens_remaining=100000,
                cost_used_today_usd=0.0,
                cost_remaining_usd=5.0,
                cost_percentage_used=0.0,
                cost_percentage_tokens=0.0
            ),
            can_modify=current_admin.get("is_admin", False),
            optimizer_status=OptimizerStatus(
                idle_mode_active=False,
                time_since_last_activity_seconds=0.0
            )
        )


@router.post("/budget", response_model=BudgetStatus)
async def update_budget(
    request: BudgetUpdateRequest,
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Update daily budget limits.
    Only accessible by admin users.
    """
    try:
        # Update the budget limits
        idle_budget.daily_token_limit = request.daily_token_limit
        idle_budget.daily_cost_limit = request.daily_cost_limit
        
        # Log the change
        AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.CONFIGURATION,
            actor_type="user",
            actor_id=current_admin["username"],
            action="budget_updated",
            description=f"Budget limits updated: tokens={request.daily_token_limit}, cost=${request.daily_cost_limit}",
            meta_data={
                "daily_token_limit": request.daily_token_limit,
                "daily_cost_limit": request.daily_cost_limit,
                "updated_by": current_admin["username"]
            }
        )
        
        # Return updated budget status
        return await get_budget(current_admin)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update budget: {str(e)}"
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