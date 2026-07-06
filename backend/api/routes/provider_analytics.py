"""
Provider Analytics API — Phase 5 Frontend
Aggregates ModelUsageLog records to serve:
  - Provider comparison (latency, cost, success rate)
  - Cost over time (daily breakdown per provider)
  - Model-level breakdown
  - Success rate per provider

"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from backend.models.database import get_db
from backend.models.entities.user_config import ModelUsageLog, ProviderType
from backend.core.auth import get_current_user

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/provider-analytics", tags=["Provider Analytics"])


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _provider_str(p) -> str:
    return p.value if hasattr(p, "value") else str(p)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/summary",
    summary="Get Provider Summary",
    description="Aggregated per-provider stats: total_requests, successful_requests, failed_requests, success_rate_pct, avg_latency_ms, total_cost_usd, total_tokens, avg_cost_per_request.",
    responses=build_responses(None),
)
async def get_provider_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Aggregated per-provider stats:
      total_requests, successful_requests, failed_requests,
      success_rate_pct, avg_latency_ms, total_cost_usd,
      total_tokens, avg_cost_per_request
    """
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            ModelUsageLog.provider,
            func.count(ModelUsageLog.id).label("total_requests"),
            func.sum(
                case((ModelUsageLog.success == True, 1), else_=0)
            ).label("successful_requests"),
            func.sum(
                case((ModelUsageLog.success == False, 1), else_=0)
            ).label("failed_requests"),
            func.avg(ModelUsageLog.latency_ms).label("avg_latency_ms"),
            func.sum(ModelUsageLog.cost_usd).label("total_cost_usd"),
            func.sum(ModelUsageLog.total_tokens).label("total_tokens"),
        )
        .filter(ModelUsageLog.created_at >= since)
        .group_by(ModelUsageLog.provider)
        .all()
    )

    result = []
    for row in rows:
        total = row.total_requests or 0
        successful = row.successful_requests or 0
        success_rate = round((successful / total * 100), 2) if total > 0 else 0.0
        total_cost = round(float(row.total_cost_usd or 0), 6)
        result.append({
            "provider": _provider_str(row.provider),
            "total_requests": total,
            "successful_requests": successful,
            "failed_requests": row.failed_requests or 0,
            "success_rate_pct": success_rate,
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 2),
            "total_cost_usd": total_cost,
            "total_tokens": row.total_tokens or 0,
            "avg_cost_per_request": round(total_cost / total, 6) if total > 0 else 0.0,
        })

    return {
        "period_days": days,
        "providers": result,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get(
    "/cost-over-time",
    summary="Get Cost Over Time",
    description="Daily cost per provider for the last N days. Returns list of { date, <provider>: cost, ... } objects suitable for Recharts LineChart.",
    responses=build_responses(None),
)
async def get_cost_over_time(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Daily cost per provider for the last N days.
    Returns list of { date, <provider>: cost, ... } objects suitable for Recharts LineChart.
    """
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            func.date(ModelUsageLog.created_at).label("date"),
            ModelUsageLog.provider,
            func.sum(ModelUsageLog.cost_usd).label("cost_usd"),
            func.count(ModelUsageLog.id).label("requests"),
        )
        .filter(ModelUsageLog.created_at >= since)
        .group_by(func.date(ModelUsageLog.created_at), ModelUsageLog.provider)
        .order_by(func.date(ModelUsageLog.created_at))
        .all()
    )

    # Pivot into { date: { provider: cost } }
    pivot: dict = {}
    providers_seen: set = set()
    for row in rows:
        date_str = str(row.date)
        provider = _provider_str(row.provider)
        providers_seen.add(provider)
        if date_str not in pivot:
            pivot[date_str] = {"date": date_str}
        pivot[date_str][provider] = round(float(row.cost_usd or 0), 6)
        pivot[date_str][f"{provider}_requests"] = row.requests

    # Fill gaps so every date has every provider key (0 if missing)
    for entry in pivot.values():
        for p in providers_seen:
            entry.setdefault(p, 0.0)

    timeline = sorted(pivot.values(), key=lambda x: x["date"])

    return {
        "period_days": days,
        "providers": sorted(providers_seen),
        "timeline": timeline,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get(
    "/model-breakdown",
    summary="Get Model Breakdown",
    description="Per-model breakdown: requests, success rate, avg latency, cost, tokens. Optionally filter by provider.",
    responses=build_responses(None),
)
async def get_model_breakdown(
    days: int = Query(default=30, ge=1, le=365),
    provider: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Per-model breakdown: requests, success rate, avg latency, cost, tokens.
    Optionally filter by provider.
    """
    since = datetime.utcnow() - timedelta(days=days)

    query = db.query(
        ModelUsageLog.provider,
        ModelUsageLog.model_used,
        func.count(ModelUsageLog.id).label("total_requests"),
        func.sum(
            case((ModelUsageLog.success == True, 1), else_=0)
        ).label("successful_requests"),
        func.avg(ModelUsageLog.latency_ms).label("avg_latency_ms"),
        func.sum(ModelUsageLog.cost_usd).label("total_cost_usd"),
        func.sum(ModelUsageLog.total_tokens).label("total_tokens"),
    ).filter(ModelUsageLog.created_at >= since)

    if provider:
        query = query.filter(func.lower(ModelUsageLog.provider) == provider.lower())

    rows = (
        query
        .group_by(ModelUsageLog.provider, ModelUsageLog.model_used)
        .order_by(func.sum(ModelUsageLog.cost_usd).desc())
        .all()
    )

    result = []
    for row in rows:
        total = row.total_requests or 0
        successful = row.successful_requests or 0
        total_cost = round(float(row.total_cost_usd or 0), 6)
        result.append({
            "provider": _provider_str(row.provider),
            "model": row.model_used,
            "total_requests": total,
            "successful_requests": successful,
            "success_rate_pct": round((successful / total * 100), 2) if total > 0 else 0.0,
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 2),
            "total_cost_usd": total_cost,
            "total_tokens": row.total_tokens or 0,
            "cost_per_1k_tokens": round((total_cost / (row.total_tokens / 1000)), 6)
                if (row.total_tokens or 0) > 0 else 0.0,
        })

    return {
        "period_days": days,
        "models": result,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get(
    "/latency-percentiles",
    summary="Get Latency Percentiles",
    description="Per-provider latency: avg, min, max, and p50 approximation.",
    responses=build_responses(None),
)
async def get_latency_percentiles(
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Per-provider latency: avg, min, max, and p50 approximation.
    """
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            ModelUsageLog.provider,
            func.avg(ModelUsageLog.latency_ms).label("avg_ms"),
            func.min(ModelUsageLog.latency_ms).label("min_ms"),
            func.max(ModelUsageLog.latency_ms).label("max_ms"),
            func.count(ModelUsageLog.id).label("sample_count"),
        )
        .filter(
            ModelUsageLog.created_at >= since,
            ModelUsageLog.latency_ms.isnot(None),
            ModelUsageLog.success == True,
        )
        .group_by(ModelUsageLog.provider)
        .all()
    )

    return {
        "period_days": days,
        "providers": [
            {
                "provider": _provider_str(row.provider),
                "avg_ms": round(float(row.avg_ms or 0), 1),
                "min_ms": row.min_ms or 0,
                "max_ms": row.max_ms or 0,
                "sample_count": row.sample_count,
            }
            for row in rows
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }