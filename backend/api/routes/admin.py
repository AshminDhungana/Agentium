"""
Admin routes for Agentium.
Protected endpoints for administrative functions.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.core.auth import get_current_active_user
from backend.models.database import get_db
from backend.models.entities import Agent, Task, AgentHealthReport, ViolationReport
from backend.models.entities.user import User

router = APIRouter()


def require_admin(current_user: dict = Depends(get_current_active_user)):
    """Dependency to require admin privileges."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


@router.get("/admin/budget")
async def get_budget(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get current API budget and usage statistics.
    Returns nested structure expected by BudgetControl.tsx frontend.
    """
    # Check if user can modify budget (admin or sovereign)
    can_modify = current_user.get("is_admin", False) or current_user.get("role") == "sovereign"
    
    # Return nested structure matching frontend expectations
    return {
        "current_limits": {
            "daily_token_limit": 200000,
            "daily_cost_limit": 100.0
        },
        "usage": {
            "tokens_used_today": 50000,
            "tokens_remaining": 150000,
            "cost_used_today_usd": 25.50,
            "cost_remaining_usd": 74.50,
            "cost_percentage_used": 25.5,
            "cost_percentage_tokens": 25.0
        },
        "can_modify": can_modify,
        "optimizer_status": {
            "idle_mode_active": False,
            "time_since_last_activity_seconds": 120
        }
    }


@router.post("/admin/budget")
async def update_budget(
    request: dict,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update budget limits (Admin or Sovereign only).
    """
    # Check permissions - allow admin or sovereign
    if not (current_user.get("is_admin") or current_user.get("role") == "sovereign"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can modify budget settings"
        )
    
    daily_token_limit = request.get("daily_token_limit")
    daily_cost_limit = request.get("daily_cost_limit")
    
    # Validate inputs
    if daily_token_limit is None or daily_cost_limit is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="daily_token_limit and daily_cost_limit are required"
        )
    
    if daily_token_limit < 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token limit must be at least 1,000"
        )
    
    if daily_cost_limit < 0 or daily_cost_limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cost limit must be between $0 and $1,000"
        )
    
    # TODO: Implement actual budget persistence
    # For now, just return success
    
    return {
        "success": True,
        "message": "Budget updated successfully",
        "new_limits": {
            "daily_token_limit": daily_token_limit,
            "daily_cost_limit": daily_cost_limit
        }
    }


@router.get("/admin/users/pending")
async def get_pending_users(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get all pending user approvals."""
    users = db.query(User).filter(User.is_pending == True).all()
    
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "is_pending": u.is_pending,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ],
        "total": len(users)
    }


@router.get("/admin/users")
async def get_all_users(
    include_pending: bool = False,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get all users with optional pending filter."""
    query = db.query(User)
    
    if not include_pending:
        query = query.filter(User.is_pending == False)
    
    users = query.all()
    
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "is_pending": u.is_pending,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "updated_at": u.updated_at.isoformat() if u.updated_at else None
            }
            for u in users
        ],
        "total": len(users)
    }


@router.post("/admin/users/{user_id}/approve")
async def approve_user(
    user_id: int,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve a pending user."""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.is_pending:
        raise HTTPException(status_code=400, detail="User is not pending approval")
    
    user.is_pending = False
    user.is_active = True
    db.commit()
    
    return {
        "success": True,
        "message": f"User {user.username} approved successfully"
    }


@router.post("/admin/users/{user_id}/reject")
async def reject_user(
    user_id: int,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reject and delete a pending user."""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.is_pending:
        raise HTTPException(status_code=400, detail="Can only reject pending users")
    
    username = user.username
    db.delete(user)
    db.commit()
    
    return {
        "success": True,
        "message": f"User {username} rejected and removed"
    }


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a user."""
    current_admin_id = admin.get("user_id")
    
    if user_id == current_admin_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    username = user.username
    db.delete(user)
    db.commit()
    
    return {
        "success": True,
        "message": f"User {username} deleted successfully"
    }


@router.post("/admin/users/{user_id}/change-password")
async def change_user_password(
    user_id: int,
    new_password: str,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin change user password."""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.hashed_password = User.hash_password(new_password)
    db.commit()
    
    return {
        "success": True,
        "message": f"Password changed for user {user.username}"
    }