"""
Admin API routes for Agentium.
Protected endpoints for administrative functions.

Budget endpoints:
  - GET  /admin/budget         → live usage from ModelUsageLog + limits from system_settings
  - POST /admin/budget         → persist new limits to system_settings, update in-memory manager
  - GET  /admin/budget/history → per-day and per-provider breakdown from real API logs

User management endpoints:
  - GET  /admin/users/pending              → users awaiting approval
  - GET  /admin/users                      → approved users (supports ?search=, ?limit=, ?offset=)
  - POST /admin/users/{id}/approve         → approve pending registration
  - POST /admin/users/{id}/reject          → reject + delete pending user
  - DELETE /admin/users/{id}               → delete approved user
  - POST /admin/users/{id}/change-password → admin password override (body, not query param)
  - POST /admin/users/{id}/role            → change RBAC role

Phase 17.1 DDoS endpoints:
  - GET    /admin/blocked-ips      → list currently blocked IPs with remaining TTL
  - DELETE /admin/blocked-ips/{ip} → manually unblock an IP (kill-switch)
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from backend.core.auth import get_current_active_user
from backend.models.database import get_db
from backend.models.entities.user import User, VALID_ROLES, ROLE_PRIMARY_SOVEREIGN
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────────────────────────────────────

def require_admin(current_user: dict = Depends(get_current_active_user)):
    """Dependency: requires admin flag on the JWT payload."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


def _can_modify_budget(current_user: dict) -> bool:
    """Admin or sovereign role may change budget limits."""
    return current_user.get("is_admin", False) or current_user.get("role") == "sovereign"


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────────

class BudgetUpdateRequest(BaseModel):
    daily_token_limit: int = Field(..., ge=1000, description="Minimum 1,000 tokens/day")
    daily_cost_limit: float = Field(..., ge=0.0, description="Daily cost cap in USD")


class AdminPasswordChangeRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


class RoleChangeRequest(BaseModel):
    new_role: str = Field(
        ...,
        description=f"Must be one of: {', '.join(sorted(VALID_ROLES))}",
    )


class BlockedIPResponse(BaseModel):
    """Response schema for a single blocked IP entry."""
    ip: str
    ttl_seconds: int   # remaining seconds; -1 = no expiry; -2 = key gone


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_budget_limits(db: Session) -> Dict[str, Any]:
    try:
        rows = db.execute(
            text(
                "SELECT key, value FROM system_settings "
                "WHERE key IN ('daily_token_limit', 'daily_cost_limit')"
            )
        ).fetchall()

        result = {}
        for row in rows:
            key, value = row[0], row[1]
            if key == "daily_token_limit":
                result["daily_token_limit"] = int(value)
            elif key == "daily_cost_limit":
                result["daily_cost_limit"] = float(value)

        from backend.services.token_optimizer import idle_budget
        result.setdefault("daily_token_limit", idle_budget.daily_token_limit)
        result.setdefault("daily_cost_limit", idle_budget.daily_cost_limit)
        return result

    except Exception:
        from backend.services.token_optimizer import idle_budget
        return {
            "daily_token_limit": idle_budget.daily_token_limit,
            "daily_cost_limit": idle_budget.daily_cost_limit,
        }


def _get_todays_usage(db: Session) -> Dict[str, Any]:
    try:
        from backend.models.entities.user_config import ModelUsageLog

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        row = db.query(
            func.coalesce(func.sum(ModelUsageLog.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(ModelUsageLog.cost_usd), 0.0).label("cost"),
        ).filter(
            ModelUsageLog.created_at >= today_start
        ).one()

        return {
            "tokens_used_today": int(row.tokens),
            "cost_used_today_usd": round(float(row.cost), 6),
        }

    except Exception:
        return {"tokens_used_today": 0, "cost_used_today_usd": 0.0}


def _persist_budget_limits(db: Session, daily_token_limit: int, daily_cost_limit: float):
    for key, value in [
        ("daily_token_limit", str(daily_token_limit)),
        ("daily_cost_limit", str(daily_cost_limit)),
    ]:
        db.execute(
            text("""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (:key, :value, NOW())
                ON CONFLICT (key) DO UPDATE
                    SET value      = EXCLUDED.value,
                        updated_at = EXCLUDED.updated_at
            """),
            {"key": key, "value": value},
        )
    db.commit()


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _user_dict(u: User) -> dict:
    return {
        "id":           u.id,
        "username":     u.username,
        "email":        u.email,
        "is_active":    u.is_active,
        "is_admin":     u.is_admin,
        "is_pending":   u.is_pending,
        "role":         u.effective_role,
        "is_sovereign": u.is_sovereign,
        "can_veto":     u.can_veto,
        "created_at":   u.created_at.isoformat() if u.created_at else None,
        "updated_at":   u.updated_at.isoformat() if u.updated_at else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/v1/admin/budget
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/budget")
async def get_budget_status(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from backend.services.token_optimizer import token_optimizer

    limits = _get_budget_limits(db)
    raw_usage = _get_todays_usage(db)

    tokens_used = raw_usage["tokens_used_today"]
    cost_used = raw_usage["cost_used_today_usd"]
    daily_token_limit = limits["daily_token_limit"]
    daily_cost_limit = limits["daily_cost_limit"]

    token_pct = (
        round((tokens_used / daily_token_limit) * 100, 2)
        if daily_token_limit > 0 else 0
    )
    cost_pct = (
        round((cost_used / daily_cost_limit) * 100, 2)
        if daily_cost_limit > 0 else 0
    )

    return {
        "current_limits": {
            "daily_token_limit": daily_token_limit,
            "daily_cost_limit": daily_cost_limit,
        },
        "usage": {
            "tokens_used_today": tokens_used,
            "tokens_remaining": max(0, daily_token_limit - tokens_used),
            "cost_used_today_usd": cost_used,
            "cost_remaining_usd": round(max(0.0, daily_cost_limit - cost_used), 6),
            "cost_percentage_used": min(cost_pct, 100),
            "cost_percentage_tokens": min(token_pct, 100),
            "data_source": "api_usage_logs",
        },
        "can_modify": _can_modify_budget(current_user),
        "optimizer_status": {
            "idle_mode_active": token_optimizer.idle_mode_active,
            "time_since_last_activity_seconds": token_optimizer.get_idle_duration_seconds(),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/admin/budget
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/admin/budget")
async def update_budget(
    request: BudgetUpdateRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not _can_modify_budget(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators or sovereign can modify budget settings."
        )

    from backend.services.token_optimizer import idle_budget

    old_token_limit = idle_budget.daily_token_limit
    old_cost_limit = idle_budget.daily_cost_limit

    _persist_budget_limits(db, request.daily_token_limit, request.daily_cost_limit)
    idle_budget.update_limits(
        daily_token_limit=request.daily_token_limit,
        daily_cost_limit=request.daily_cost_limit,
    )

    return {
        "status": "success",
        "message": (
            "Budget updated and persisted. "
            "New values are now the system default and will survive restarts."
        ),
        "previous": {
            "daily_token_limit": old_token_limit,
            "daily_cost_limit": old_cost_limit,
        },
        "updated": {
            "daily_token_limit": request.daily_token_limit,
            "daily_cost_limit": request.daily_cost_limit,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/v1/admin/budget/history
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/budget/history")
async def get_budget_history(
    days: int = 7,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Day-by-day and per-provider breakdown of real API usage."""
    try:
        from backend.models.entities.user_config import ModelUsageLog

        since = datetime.utcnow() - timedelta(days=days)
        logs = db.query(ModelUsageLog).filter(ModelUsageLog.created_at >= since).all()

        daily: Dict[str, Any] = {}
        by_provider: Dict[str, Any] = {}

        for log in logs:
            day = log.created_at.strftime("%Y-%m-%d")
            cost = float(log.cost_usd or 0)
            tokens = log.total_tokens or 0
            provider = str(
                log.provider.value if hasattr(log.provider, "value") else log.provider
            )

            if day not in daily:
                daily[day] = {"tokens": 0, "requests": 0, "cost_usd": 0.0}
            daily[day]["tokens"] += tokens
            daily[day]["requests"] += 1
            daily[day]["cost_usd"] = round(daily[day]["cost_usd"] + cost, 6)

            if provider not in by_provider:
                by_provider[provider] = {"tokens": 0, "requests": 0, "cost_usd": 0.0}
            by_provider[provider]["tokens"] += tokens
            by_provider[provider]["requests"] += 1
            by_provider[provider]["cost_usd"] = round(
                by_provider[provider]["cost_usd"] + cost, 6
            )

        return {
            "period_days": days,
            "total_tokens": sum(d["tokens"] for d in daily.values()),
            "total_requests": len(logs),
            "total_cost_usd": round(sum(d["cost_usd"] for d in daily.values()), 6),
            "daily_breakdown": daily,
            "by_provider": by_provider,
            "data_source": "api_usage_logs",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch budget history: {str(e)}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# User management
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/users/pending")
async def get_pending_users(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get all users awaiting approval."""
    users = db.query(User).filter(User.is_pending == True).all()
    return {"users": [_user_dict(u) for u in users], "total": len(users)}


@router.get("/admin/users")
async def get_all_users(
    include_pending: bool = False,
    search: Optional[str] = Query(None, description="Filter by username or email (case-insensitive)"),
    limit: int = Query(200, ge=1, le=500, description="Max users to return (default 200)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if not include_pending:
        query = query.filter(User.is_pending == False)

    if search:
        term = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(User.username).like(term),
                func.lower(User.email).like(term),
            )
        )

    total = query.count()
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "users":  [_user_dict(u) for u in users],
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }


@router.post("/admin/users/{user_id}/approve")
async def approve_user(
    user_id: str,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve a pending user registration."""
    user = _get_user_or_404(db, user_id)
    if not user.is_pending:
        raise HTTPException(status_code=400, detail="User is not pending approval")

    user.is_pending = False
    user.is_active = True

    audit_entry = AuditLog.log(
        level=AuditLevel.INFO,
        category=AuditCategory.AUTHENTICATION,
        actor_type="admin",
        actor_id=admin.get("username", "unknown"),
        action="user_approved",
        target_type="user",
        target_id=str(user.id),
        description=f"Admin approved registration for user: {user.username}",
        meta_data={"approved_user_id": user.id, "approved_username": user.username},
    )
    db.add(audit_entry)
    db.commit()

    return {"success": True, "message": f"User {user.username} approved successfully"}


@router.post("/admin/users/{user_id}/reject")
async def reject_user(
    user_id: str,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reject and permanently remove a pending user."""
    user = _get_user_or_404(db, user_id)
    if not user.is_pending:
        raise HTTPException(status_code=400, detail="Can only reject pending users")

    username = user.username
    rejected_id = str(user.id)

    db.delete(user)

    audit_entry = AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.AUTHENTICATION,
        actor_type="admin",
        actor_id=admin.get("username", "unknown"),
        action="user_rejected",
        target_type="user",
        target_id=rejected_id,
        description=f"Admin rejected and removed pending user: {username}",
        meta_data={"rejected_username": username},
    )
    db.add(audit_entry)
    db.commit()

    return {"success": True, "message": f"User {username} rejected and removed"}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user account. Cannot delete your own account."""
    if user_id == admin.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = _get_user_or_404(db, user_id)
    username = user.username
    deleted_id = str(user.id)

    db.delete(user)

    audit_entry = AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.AUTHORIZATION,
        actor_type="admin",
        actor_id=admin.get("username", "unknown"),
        action="user_deleted",
        target_type="user",
        target_id=deleted_id,
        description=f"Admin permanently deleted user account: {username}",
        meta_data={"deleted_username": username},
    )
    db.add(audit_entry)
    db.commit()

    return {"success": True, "message": f"User {username} deleted successfully"}


@router.post("/admin/users/{user_id}/change-password")
async def change_user_password(
    user_id: str,
    request: AdminPasswordChangeRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin override: change any user's password."""
    user = _get_user_or_404(db, user_id)
    user.hashed_password = User.hash_password(request.new_password)
    user.updated_at = datetime.now(timezone.utc)

    audit_entry = AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.AUTHENTICATION,
        actor_type="admin",
        actor_id=admin.get("username", "unknown"),
        action="admin_password_change",
        target_type="user",
        target_id=str(user.id),
        description=f"Admin changed password for user: {user.username}",
        meta_data={"target_username": user.username},
    )
    db.add(audit_entry)
    db.commit()

    return {"success": True, "message": f"Password changed for user {user.username}"}


@router.post("/admin/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    request: RoleChangeRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if request.new_role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{request.new_role}'. Must be one of: {', '.join(sorted(VALID_ROLES))}",
        )

    if user_id == admin.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot change their own role.",
        )

    user = _get_user_or_404(db, user_id)
    old_role = user.effective_role

    user.role = request.new_role
    user.is_admin = (request.new_role == ROLE_PRIMARY_SOVEREIGN)
    user.updated_at = datetime.now(timezone.utc)

    audit_entry = AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.AUTHORIZATION,
        actor_type="admin",
        actor_id=admin.get("username", "unknown"),
        action="user_role_changed",
        target_type="user",
        target_id=str(user.id),
        description=(
            f"Admin changed role for {user.username}: "
            f"{old_role} → {request.new_role}"
        ),
        meta_data={
            "target_username": user.username,
            "old_role": old_role,
            "new_role": request.new_role,
        },
    )
    db.add(audit_entry)
    db.commit()

    return {
        "success": True,
        "message": f"Role updated for {user.username}",
        "previous_role": old_role,
        "new_role": request.new_role,
    }


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/v1/admin/slow-queries
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/slow-queries")
async def get_slow_queries(
    limit: int = 20,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from backend.services.slow_query_service import get_slow_queries as fetch_slow_queries
    import dataclasses

    try:
        queries = fetch_slow_queries(db, limit=limit, min_avg_ms=0.0)
        return {
            "success": True,
            "count": len(queries),
            "slow_queries": [dataclasses.asdict(q) for q in queries] 
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch slow queries: {str(e)}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Config history / restore (unchanged)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/config-history/{entity_type}/{entity_id}")
async def get_config_history(
    entity_type: str,
    entity_id: str,
    admin: dict = Depends(require_admin),
):
    from backend.services.config_versioning import ConfigVersioningService
    history = ConfigVersioningService.get_config_history(entity_type, entity_id)
    return {"history": history}


@router.post("/admin/config-restore/{entity_type}/{entity_id}")
async def restore_config_snapshot(
    entity_type: str,
    entity_id: str,
    commit: str,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from backend.services.config_versioning import ConfigVersioningService
    try:
        snapshot = ConfigVersioningService.restore_snapshot(entity_type, entity_id, commit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    if entity_type == "channel":
        from backend.models.entities.channels import ExternalChannel
        channel = db.query(ExternalChannel).filter(ExternalChannel.id == entity_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        for key in ["name", "config", "default_agent_id", "auto_create_tasks", "require_approval", "status"]:
            if key in snapshot:
                setattr(channel, key, snapshot[key])
        
    elif entity_type == "model_config":
        from backend.models.entities.user_config import UserModelConfig
        config = db.query(UserModelConfig).filter(UserModelConfig.id == entity_id).first()
        if not config:
            raise HTTPException(status_code=404, detail="Model config not found")
        for key in ["provider_name", "config_name", "api_base_url", "local_server_url", "default_model", "available_models", "is_default", "max_tokens", "temperature", "top_p", "timeout_seconds", "status"]:
            if key in snapshot:
                setattr(config, key, snapshot[key])
        _skipped_key_fields = [k for k in ("api_key_encrypted", "api_key_masked") if k in snapshot]
        if _skipped_key_fields:
            import logging as _log
            _log.getLogger(__name__).warning(
                "config-restore: skipped restoring sensitive field(s) %s for "
                "model_config %s — re-enter the API key manually if needed.",
                _skipped_key_fields,
                entity_id,
            )

    elif entity_type == "plugin":
        from backend.models.entities.plugin import PluginInstallation
        inst = db.query(PluginInstallation).filter(PluginInstallation.id == entity_id).first()
        if not inst:
            raise HTTPException(status_code=404, detail="Plugin installation not found")
        if "config" in snapshot:
            inst.config = snapshot["config"]
        
    elif entity_type == "constitution_article":
        from backend.models.entities.constitution import ConstitutionArticle
        article = db.query(ConstitutionArticle).filter(ConstitutionArticle.id == entity_id).first()
        if not article:
            raise HTTPException(status_code=404, detail="Constitution Article not found")
        for key in ["text", "commentary", "tier"]:
            if key in snapshot:
                setattr(article, key, snapshot[key])
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported entity type for restore: {entity_type}")
        
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")
        
    return {
        "success": True,
        "message": f"{entity_type} {entity_id} restored to {commit}",
        "warnings": (
            ["API key fields were not restored — re-enter the key manually if needed."]
            if entity_type == "model_config" and any(
                k in snapshot for k in ("api_key_encrypted", "api_key_masked")
            )
            else []
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Phase 17.1 — DDoS Blocklist Management
# ──────────────────────────────────────────────────────────────────────────────

def _get_redis_sync():
    """
    Return a synchronous Redis client for admin endpoints.
    Uses the same REDIS_URL as the rest of the application.
    """
    import os
    import redis as redis_lib
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return redis_lib.from_url(redis_url, decode_responses=True)


@router.get(
    "/admin/blocked-ips",
    response_model=List[BlockedIPResponse],
    summary="Phase 17.1 — List currently blocked IPs",
    description=(
        "Returns all IPs in the Redis blocklist with their remaining TTL. "
        "Uses SCAN so it is safe on large keyspaces. "
        "Requires admin privileges."
    ),
)
async def list_blocked_ips(
    admin: dict = Depends(require_admin),
):
    """
    Phase 17.1: List all IPs currently in the Redis blocklist.

    Uses cursor-based SCAN (non-blocking) and pipelines all TTL calls in a
    single round-trip. Results are sorted by remaining TTL ascending so the
    IPs closest to expiry appear first.
    """
    try:
        r = _get_redis_sync()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        )

    results: list[BlockedIPResponse] = []
    cursor = 0

    try:
        while True:
            cursor, keys = r.scan(cursor, match="agentium:blocked:ips:*", count=100)

            if keys:
                # Pipeline all TTL lookups in one round-trip
                pipe = r.pipeline(transaction=False)
                for k in keys:
                    pipe.ttl(k)
                ttls = pipe.execute()

                for key, ttl in zip(keys, ttls):
                    # key format: "agentium:blocked:ips:{ip}"
                    ip = key.split(":")[-1]
                    results.append(BlockedIPResponse(ip=ip, ttl_seconds=int(ttl)))

            if cursor == 0:
                break

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan blocked IPs: {exc}",
        )
    finally:
        try:
            r.close()
        except Exception:
            pass

    # Sort by TTL ascending: IPs expiring soonest shown first
    results.sort(key=lambda r: r.ttl_seconds)
    return results


@router.delete(
    "/admin/blocked-ips/{ip}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Phase 17.1 — Manually unblock an IP",
    description=(
        "Admin kill-switch: removes the IP from the Redis blocklist immediately. "
        "Also clears the 4xx error counters so Celery does not re-block on the "
        "next detection cycle. The action is audit-logged."
    ),
)
async def unblock_ip(
    ip: str,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Phase 17.1: Manually unblock an IP.

    - Deletes the blocklist key immediately.
    - Clears the 4xx sliding-window counter keys so the IP isn't re-blocked
      by the Celery task before its legitimate counters reset naturally.
    - Writes an AuditLog entry for compliance traceability.
    """
    try:
        r = _get_redis_sync()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        )

    try:
        block_key = f"agentium:blocked:ips:{ip}"
        deleted = r.delete(block_key)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP {ip} is not currently in the blocklist.",
            )

        # Clear 4xx counters so Celery won't immediately re-block this IP
        r.delete(f"agentium:4xx:{ip}", f"agentium:4xx:{ip}:wsum")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unblock IP: {exc}",
        )
    finally:
        try:
            r.close()
        except Exception:
            pass

    # Audit the manual unblock action
    try:
        audit_entry = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.SECURITY,
            actor_type="admin",
            actor_id=admin.get("username", "unknown"),
            action="ip_manually_unblocked",
            target_type="ip_address",
            target_id=ip,
            description=f"Admin manually unblocked IP: {ip}",
            meta_data={
                "ip": ip,
                "unblocked_by": admin.get("username", "unknown"),
            },
        )
        db.add(audit_entry)
        db.commit()
    except Exception as audit_exc:
        # Non-fatal: the unblock succeeded — don't roll it back over an audit failure
        import logging as _log
        _log.getLogger(__name__).warning(
            "unblock_ip: audit log write failed (non-fatal): %s", audit_exc
        )

    # 204 No Content — no response body needed