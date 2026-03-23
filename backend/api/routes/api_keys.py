"""
API Routes for API Key Management - Phase 5.4

Provides REST endpoints for:
- Health monitoring and status checks
- Manual key recovery from cooldown
- Budget management
- Key rotation
- Health reports
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.user_config import UserModelConfig, ProviderType
from backend.services.api_key_manager import api_key_manager, APIKeyHealthStatus
from backend.core.auth import get_current_user

router = APIRouter(prefix="/api-keys", tags=["API Key Resilience"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class KeyHealthResponse(BaseModel):
    id: str
    provider: str
    priority: int
    status: str
    failure_count: int
    cooldown_until: Optional[str]
    monthly_budget_usd: float
    current_spend_usd: float
    budget_remaining_pct: float


class ProviderHealthSummary(BaseModel):
    total_keys: int
    healthy: int
    cooldown: int
    rate_limited: int
    exhausted: int
    error: int
    keys: List[KeyHealthResponse]


class HealthReportResponse(BaseModel):
    overall_status: str
    providers: dict
    summary: dict
    generated_at: str


class RecoverKeyRequest(BaseModel):
    force: bool = Field(default=False, description="Force recovery even if cooldown not expired")


class RecoverKeyResponse(BaseModel):
    success: bool
    message: str
    key_id: str
    new_status: str


class UpdateBudgetRequest(BaseModel):
    monthly_budget_usd: float = Field(..., ge=0, description="Monthly budget in USD (0 = unlimited)")


class UpdateBudgetResponse(BaseModel):
    success: bool
    key_id: str
    monthly_budget_usd: float
    current_spend_usd: float
    remaining_usd: float


class RotateKeyRequest(BaseModel):
    new_api_key: str = Field(..., min_length=10, description="New API key (will be encrypted)")
    new_key_masked: Optional[str] = Field(default=None, description="Masked version for display (e.g., ...sk-abc)")


class RotateKeyResponse(BaseModel):
    success: bool
    old_key_id: str
    new_key_id: str
    message: str


class ProviderAvailabilityResponse(BaseModel):
    provider: str
    available: bool
    healthy_keys_count: int


class FailoverTestResponse(BaseModel):
    tested_provider: str
    attempted_keys: int
    successful_key_id: Optional[str]
    failed_keys: List[str]
    latency_ms: float


class CreateKeyRequest(BaseModel):
    """Request body for adding a new API key."""
    provider: str = Field(..., description="Provider name, e.g. 'openai', 'anthropic'")
    api_key: str = Field(..., min_length=10, description="Raw API key (encrypted at rest)")
    config_name: str = Field(..., min_length=1, description="Human-readable label")
    model_name: str = Field(..., min_length=1, description="Default model for this key")
    monthly_budget_usd: float = Field(default=0.0, ge=0, description="Monthly budget (0 = unlimited)")
    priority: int = Field(default=1, ge=1, description="Failover priority — lower = higher priority")
    is_default: bool = Field(default=False, description="Set as default config for agents")


class CreateKeyResponse(BaseModel):
    success: bool
    key_id: str
    provider: str
    config_name: str
    genesis_triggered: bool
    message: str


# =============================================================================
# Routes
# =============================================================================

@router.post("/", response_model=CreateKeyResponse, status_code=201)
async def create_api_key(
    request: CreateKeyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Save a new API key and auto-trigger the Genesis Protocol if the system
    has not been initialized yet.

    Flow:
      1. Encrypt and persist the key as a UserModelConfig row.
      2. If Head 00001 does not exist (genesis not run), fire
         POST /genesis/initialize in a background task so the HTTP
         response is returned immediately and the frontend can poll
         GET /genesis/status for progress.
      3. Return whether genesis was triggered so the frontend can show
         the appropriate status message without an extra round-trip.
    """
    from backend.core.security import encrypt_api_key
    from backend.models.entities.user_config import ProviderType

    # ── Resolve provider enum ────────────────────────────────────────────────
    try:
        provider_enum = ProviderType(request.provider.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{request.provider}'. "
                   f"Valid values: {[p.value for p in ProviderType]}",
        )

    # ── Encrypt key ──────────────────────────────────────────────────────────
    try:
        encrypted = encrypt_api_key(request.api_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Key encryption failed: {exc}")

    masked = f"...{request.api_key[-4:]}"

    # ── If is_default, demote any existing default for same provider ─────────
    if request.is_default:
        db.query(UserModelConfig).filter_by(
            provider=provider_enum, is_default=True
        ).update({"is_default": False})
        db.flush()

    # ── Persist ──────────────────────────────────────────────────────────────
    key = UserModelConfig(
        provider=provider_enum,
        config_name=request.config_name,
        model_name=request.model_name,
        api_key=encrypted,
        api_key_masked=masked,
        monthly_budget_usd=request.monthly_budget_usd,
        priority=request.priority,
        is_default=request.is_default,
        is_active=True,
        status="active",
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    # ── Auto-trigger Genesis if not yet initialized ──────────────────────────
    # Check whether Head 00001 already exists.  If not, fire genesis in the
    # background so the user doesn't have to navigate to /models and manually
    # trigger it — adding a key IS the trigger.
    from backend.models.entities.agents import HeadOfCouncil
    from backend.services.initialization_service import InitializationService

    genesis_triggered = False
    head_exists = db.query(HeadOfCouncil).filter_by(
        agentium_id="00001", is_active=True
    ).first()

    if not head_exists:
        genesis_triggered = True

        async def _run_genesis() -> None:
            # Always open a fresh session — never reuse the request session
            # inside a background task (it gets closed when the request ends).
            from backend.models.database import get_db as _get_db
            with next(_get_db()) as new_db:
                svc = InitializationService(new_db)
                try:
                    await svc.run_genesis_protocol()
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).error(
                        "Auto-genesis after key creation failed: %s", exc, exc_info=True
                    )

        background_tasks.add_task(_run_genesis)

    return CreateKeyResponse(
        success=True,
        key_id=str(key.id),
        provider=provider_enum.value,
        config_name=request.config_name,
        genesis_triggered=genesis_triggered,
        message=(
            "API key saved and Genesis Protocol started. "
            "Poll GET /api/v1/genesis/status for progress."
            if genesis_triggered
            else "API key saved successfully."
        ),
    )


@router.get("/health", response_model=HealthReportResponse)
async def get_health_report(
    provider: Optional[str] = Query(None, description="Filter by specific provider"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive health report for all API keys.

    Returns overall system status and per-provider breakdown.
    """
    report = api_key_manager.get_key_health_report(provider, db)
    return report


@router.get("/health/{provider}", response_model=ProviderHealthSummary)
async def get_provider_health(
    provider: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed health status for a specific provider.
    """
    report = api_key_manager.get_key_health_report(provider, db)
    
    if provider not in report["providers"]:
        raise HTTPException(status_code=404, detail=f"No keys found for provider: {provider}")
    
    return report["providers"][provider]


@router.get("/availability", response_model=List[ProviderAvailabilityResponse])
async def get_provider_availability(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Quick check of which providers have healthy keys available.
    
    Returns list of all providers with availability status.
    """
    availability = api_key_manager.get_provider_availability(db)
    
    # Get counts for each provider
    result = []
    for provider, available in availability.items():
        count = db.query(UserModelConfig).filter_by(
            provider=provider,
            is_active=True
        ).filter(
            UserModelConfig.priority < 999
        ).count()
        
        result.append({
            "provider": provider,
            "available": available,
            "healthy_keys_count": count if available else 0
        })
    
    return result


@router.post("/test-failover", response_model=FailoverTestResponse)
async def test_failover(
    provider: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Test the failover mechanism for a provider.
    
    This attempts to get an active key without making actual API calls.
    Useful for verifying failover configuration.
    """
    import time
    
    start = time.time()
    
    # Get all keys for provider
    keys = db.query(UserModelConfig).filter_by(
        provider=provider,
        is_active=True
    ).order_by(UserModelConfig.priority.asc()).all()
    
    attempted = 0
    failed = []
    successful_id = None
    
    for key in keys:
        attempted += 1
        is_healthy = api_key_manager._is_key_healthy(key)
        
        if is_healthy:
            successful_id = str(key.id)
            break
        else:
            failed.append(str(key.id))
    
    latency = (time.time() - start) * 1000
    
    return {
        "tested_provider": provider,
        "attempted_keys": attempted,
        "successful_key_id": successful_id,
        "failed_keys": failed,
        "latency_ms": round(latency, 2)
    }


@router.get("/{key_id}/status", response_model=KeyHealthResponse)
async def get_key_status(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed status for a specific API key.
    """
    key = db.query(UserModelConfig).filter_by(id=key_id, is_active=True).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    # Calculate status
    status = api_key_manager._get_key_status(key)
    
    # Reset monthly spend if needed
    api_key_manager._reset_monthly_spend_if_needed(key)
    
    budget_pct = 100.0
    if key.monthly_budget_usd > 0:
        budget_pct = ((key.monthly_budget_usd - key.current_spend_usd) / key.monthly_budget_usd) * 100
    
    return {
        "id": str(key.id),
        "provider": key.provider.value if hasattr(key.provider, 'value') else str(key.provider),
        "priority": key.priority,
        "status": status,
        "failure_count": key.failure_count,
        "cooldown_until": key.cooldown_until.isoformat() if key.cooldown_until else None,
        "monthly_budget_usd": key.monthly_budget_usd,
        "current_spend_usd": round(key.current_spend_usd, 4),
        "budget_remaining_pct": round(max(0, budget_pct), 2)
    }


@router.post("/{key_id}/recover", response_model=RecoverKeyResponse)
async def recover_key(
    key_id: str,
    request: RecoverKeyRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Manually recover an API key from cooldown or error state.
    
    This resets failure count, clears cooldown, and sets status to ACTIVE.
    """
    key = db.query(UserModelConfig).filter_by(id=key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    # Check if in cooldown
    if key.cooldown_until and datetime.utcnow() < key.cooldown_until and not request.force:
        remaining = (key.cooldown_until - datetime.utcnow()).total_seconds()
        raise HTTPException(
            status_code=400,
            detail=f"Key still in cooldown for {remaining:.0f} seconds. Use force=true to override."
        )
    
    success = api_key_manager.recover_key(key_id, db)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to recover key")
    
    return {
        "success": True,
        "message": f"Key {key_id} recovered successfully",
        "key_id": key_id,
        "new_status": APIKeyHealthStatus.HEALTHY
    }


@router.post("/{key_id}/budget", response_model=UpdateBudgetResponse)
async def update_key_budget(
    key_id: str,
    request: UpdateBudgetRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update monthly budget limit for a specific API key.
    
    Set monthly_budget_usd=0 for unlimited budget.
    """
    key = db.query(UserModelConfig).filter_by(id=key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    success = api_key_manager.update_budget(key_id, request.monthly_budget_usd, db)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update budget")
    
    # Refresh to get updated values
    db.refresh(key)
    
    return {
        "success": True,
        "key_id": key_id,
        "monthly_budget_usd": key.monthly_budget_usd,
        "current_spend_usd": round(key.current_spend_usd, 4),
        "remaining_usd": round(max(0, key.monthly_budget_usd - key.current_spend_usd), 4)
    }


@router.post("/{key_id}/rotate", response_model=RotateKeyResponse)
async def rotate_api_key(
    key_id: str,
    request: RotateKeyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Rotate an API key with zero downtime.
    
    1. Creates new key with temporary lower priority
    2. Tests new key
    3. Swaps priorities (new becomes primary)
    4. Old key enters 1-hour cooldown then can be deleted
    """
    from backend.core.security import encrypt_api_key
    
    key = db.query(UserModelConfig).filter_by(id=key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    # Encrypt the new key
    encrypted_key = encrypt_api_key(request.new_api_key)
    masked = request.new_key_masked or f"...{request.new_api_key[-4:]}"
    
    # Perform rotation
    new_key = api_key_manager.rotate_key(key_id, encrypted_key, masked, db)
    
    if not new_key:
        raise HTTPException(status_code=400, detail="Key rotation failed. New key may be invalid.")
    
    return {
        "success": True,
        "old_key_id": key_id,
        "new_key_id": str(new_key.id),
        "message": (
            f"Key rotated successfully. New key is now primary (priority {new_key.priority}). "
            f"Old key will be available for 1 hour before deletion."
        )
    }


@router.delete("/{key_id}")
async def delete_key(
    key_id: str,
    force: bool = Query(False, description="Force delete even if key is active"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete an API key configuration.
    
    By default, only keys in cooldown or error state can be deleted.
    Use force=true to delete active keys (use with caution).
    """
    key = db.query(UserModelConfig).filter_by(id=key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    # Check if safe to delete
    if not force:
        status = api_key_manager._get_key_status(key)
        if status == APIKeyHealthStatus.HEALTHY:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Key is healthy. Use force=true to force deletion, "
                    f"or mark it as failed first."
                )
            )
        
        # Check if it's the only key for this provider
        other_keys = db.query(UserModelConfig).filter(
            UserModelConfig.provider == key.provider,
            UserModelConfig.is_active == True,
            UserModelConfig.id != key_id
        ).count()
        
        if other_keys == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the only key for this provider. Add another key first."
            )
    
    # Soft delete
    key.is_active = False
    db.commit()
    
    return {
        "success": True,
        "message": f"Key {key_id} deleted successfully",
        "key_id": key_id
    }


@router.get("/{key_id}/spend-history")
async def get_spend_history(
    key_id: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get spend history for a specific API key from ModelUsageLog.
    """
    from backend.models.entities.user_config import ModelUsageLog
    from sqlalchemy import func
    
    key = db.query(UserModelConfig).filter_by(id=key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    since = datetime.utcnow() - timedelta(days=days)
    
    # Aggregate daily spend
    daily_spend = db.query(
        func.date(ModelUsageLog.created_at).label('date'),
        func.sum(ModelUsageLog.cost_usd).label('cost'),
        func.sum(ModelUsageLog.total_tokens).label('tokens'),
        func.count().label('requests')
    ).filter(
        ModelUsageLog.config_id == key_id,
        ModelUsageLog.created_at >= since
    ).group_by(
        func.date(ModelUsageLog.created_at)
    ).all()
    
    return {
        "key_id": key_id,
        "provider": key.provider.value if hasattr(key.provider, 'value') else str(key.provider),
        "period_days": days,
        "total_spend_usd": round(sum(d.cost or 0 for d in daily_spend), 4),
        "total_tokens": sum(d.tokens or 0 for d in daily_spend),
        "total_requests": sum(d.requests for d in daily_spend),
        "daily_breakdown": [
            {
                "date": str(d.date),
                "cost_usd": round(d.cost or 0, 4),
                "tokens": d.tokens or 0,
                "requests": d.requests
            }
            for d in daily_spend
        ]
    }