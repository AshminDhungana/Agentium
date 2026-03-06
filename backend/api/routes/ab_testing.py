"""
A/B Model Testing API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from backend.models.database import get_db
from backend.models.entities.ab_testing import (
    Experiment, ExperimentStatus, RunStatus, ModelPerformanceCache, ExperimentRun
)
from backend.services.ab_testing_service import ABTestingService
from backend.api.dependencies.auth import get_current_user
from backend.models.entities.user import User
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

router = APIRouter(prefix="/ab-testing", tags=["A/B Model Testing"])


# ── Auth dependency ───────────────────────────────────────────────────────────

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require the caller to be an admin / sovereign user."""
    if not (getattr(current_user, "is_admin", False) or getattr(current_user, "isSovereign", False)):
        raise HTTPException(status_code=403, detail="Admin access required for A/B Testing")
    return current_user


# ── Pydantic request schemas ──────────────────────────────────────────────────

class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    task_template: str = Field(..., min_length=1)
    config_ids: List[str] = Field(..., min_items=2)
    description: Optional[str] = ""
    system_prompt: Optional[str] = None
    iterations: int = Field(default=1, ge=1, le=10)


class QuickTestRequest(BaseModel):
    task: str = Field(..., min_length=1)
    config_ids: List[str] = Field(..., min_items=2)


# ── Pydantic response schemas ─────────────────────────────────────────────────

class ExperimentSummaryOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: str
    models_tested: int
    progress: float
    total_runs: int
    completed_runs: int
    failed_runs: int
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class PaginatedExperimentsOut(BaseModel):
    items: List[ExperimentSummaryOut]
    total: int
    limit: int
    offset: int


class ExperimentRunOut(BaseModel):
    id: str
    model: str                              # mapped from model_name
    config_id: str
    iteration: int                          # mapped from iteration_number
    status: str
    tokens: Optional[int]                  # mapped from tokens_used
    latency_ms: Optional[int]
    cost_usd: Optional[float]
    quality_score: Optional[float]          # mapped from overall_quality_score
    critic_plan_score: Optional[float]
    critic_code_score: Optional[float]
    critic_output_score: Optional[float]
    constitutional_violations: int
    output_preview: Optional[str]
    error_message: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class ModelComparisonOut(BaseModel):
    config_id: str
    model_name: str
    avg_tokens: int
    avg_cost_usd: float
    avg_latency_ms: int
    avg_quality_score: float
    success_rate: float
    total_runs: int
    completed_runs: int
    failed_runs: int


class WinnerOut(BaseModel):
    config_id: Optional[str]
    model: str
    reason: str
    confidence: float


class ComparisonOut(BaseModel):
    winner: WinnerOut
    model_comparisons: dict
    created_at: Optional[str]


class ExperimentDetailOut(ExperimentSummaryOut):
    task_template: str
    system_prompt: Optional[str]
    test_iterations: int
    runs: List[ExperimentRunOut]
    comparison: Optional[ComparisonOut]


class ABTestingStatsOut(BaseModel):
    total_experiments: int
    completed_experiments: int
    running_experiments: int
    total_model_runs: int
    cached_recommendations: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _experiment_progress(experiment: Experiment) -> float:
    total = len(experiment.runs)
    if total == 0:
        return 0.0
    done = len([r for r in experiment.runs if r.status != RunStatus.PENDING])
    return round(done / total * 100, 1)


def _run_counts(experiment: Experiment) -> dict:
    total = len(experiment.runs)
    completed = len([r for r in experiment.runs if r.status == RunStatus.COMPLETED])
    failed = len([r for r in experiment.runs if r.status == RunStatus.FAILED])
    return {"total": total, "completed": completed, "failed": failed}


def _serialize_run(run: ExperimentRun) -> dict:
    """Serialize an ExperimentRun with consistent field naming (DB → API)."""
    output = run.output_text or ""
    return {
        "id": run.id,
        "model": run.model_name,                        # DB: model_name → API: model
        "config_id": run.config_id,
        "iteration": run.iteration_number,              # DB: iteration_number → API: iteration
        "status": run.status.value,
        "tokens": run.tokens_used,                      # DB: tokens_used → API: tokens
        "latency_ms": run.latency_ms,
        "cost_usd": run.cost_usd,
        "quality_score": run.overall_quality_score,     # DB: overall_quality_score → API: quality_score
        "critic_plan_score": run.critic_plan_score,
        "critic_code_score": run.critic_code_score,
        "critic_output_score": run.critic_output_score,
        "constitutional_violations": run.constitutional_violations or 0,
        "output_preview": output[:400] if output else None,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _serialize_experiment_summary(experiment: Experiment) -> dict:
    counts = _run_counts(experiment)
    return {
        "id": experiment.id,
        "name": experiment.name,
        "description": experiment.description,
        "status": experiment.status.value,
        "models_tested": len(set(r.config_id for r in experiment.runs)),
        "progress": _experiment_progress(experiment),
        "total_runs": counts["total"],
        "completed_runs": counts["completed"],
        "failed_runs": counts["failed"],
        "created_at": experiment.created_at.isoformat() if experiment.created_at else None,
        "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
        "completed_at": experiment.completed_at.isoformat() if experiment.completed_at else None,
    }


def _serialize_experiment_detail(experiment: Experiment) -> dict:
    base = _serialize_experiment_summary(experiment)
    comparison = None
    if experiment.results:
        result = experiment.results[-1]
        comparison = {
            "winner": {
                "config_id": result.winner_config_id,
                "model": result.winner_model_name,
                "reason": result.selection_reason,
                "confidence": result.confidence_score or 0.0,
            },
            "model_comparisons": result.model_comparisons or {"models": []},
            "created_at": result.created_at.isoformat() if result.created_at else None,
        }
    return {
        **base,
        "task_template": experiment.task_template,
        "system_prompt": experiment.system_prompt,
        "test_iterations": experiment.test_iterations,
        "runs": [_serialize_run(r) for r in experiment.runs],
        "comparison": comparison,
    }


def _write_audit(
    db: Session,
    actor: str,
    action: str,
    target_id: str,
    description: str,
) -> None:
    """Write an audit log entry for A/B testing mutations."""
    try:
        audit = AuditLog(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="user",
            actor_id=actor,
            action=action,
            target_type="experiment",
            target_id=target_id,
            description=description,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(audit)
    except Exception:
        pass  # Never let audit logging crash the main request


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/experiments", response_model=ExperimentSummaryOut)
async def create_experiment(
    data: ExperimentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create and auto-start a new A/B test experiment."""
    service = ABTestingService(db)
    experiment = await service.create_experiment(
        name=data.name,
        task_template=data.task_template,
        config_ids=data.config_ids,
        description=data.description or "",
        system_prompt=data.system_prompt,
        iterations=data.iterations,
        created_by=current_user.username,
    )

    # Run in background so this endpoint returns immediately
    background_tasks.add_task(service.run_experiment, experiment.id)

    _write_audit(
        db, current_user.username, "experiment_created", experiment.id,
        f"Experiment '{experiment.name}' created with {len(data.config_ids)} models, {data.iterations} iteration(s)",
    )
    db.commit()

    return _serialize_experiment_summary(experiment)


@router.get("/experiments", response_model=PaginatedExperimentsOut)
async def list_experiments(
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List experiments with optional status filter and pagination."""
    query = db.query(Experiment).options(joinedload(Experiment.runs))

    if status:
        try:
            status_enum = ExperimentStatus(status)
            query = query.filter(Experiment.status == status_enum)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    total = query.count()
    experiments = (
        query
        .order_by(Experiment.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "items": [_serialize_experiment_summary(e) for e in experiments],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetailOut)
async def get_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get detailed experiment results including all runs and comparison."""
    experiment = (
        db.query(Experiment)
        .options(joinedload(Experiment.runs), joinedload(Experiment.results))
        .filter(Experiment.id == experiment_id)
        .first()
    )
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    return _serialize_experiment_detail(experiment)


@router.post("/experiments/{experiment_id}/cancel")
async def cancel_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Cancel a running or pending experiment."""
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    cancellable = {ExperimentStatus.RUNNING, ExperimentStatus.PENDING, ExperimentStatus.DRAFT}
    if experiment.status not in cancellable:
        raise HTTPException(400, f"Cannot cancel experiment with status: {experiment.status.value}")

    experiment.status = ExperimentStatus.CANCELLED
    experiment.completed_at = datetime.utcnow()

    _write_audit(
        db, current_user.username, "experiment_cancelled", experiment_id,
        f"Experiment '{experiment.name}' cancelled by {current_user.username}",
    )
    db.commit()

    return {"message": "Experiment cancelled", "id": experiment_id}


@router.delete("/experiments/{experiment_id}")
async def delete_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete an experiment and all its runs/results."""
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    # Block deletion of active experiments — background task may still be writing to them
    non_deletable = {ExperimentStatus.RUNNING, ExperimentStatus.PENDING}
    if experiment.status in non_deletable:
        raise HTTPException(
            400,
            f"Cannot delete experiment with status '{experiment.status.value}'. Cancel it first.",
        )

    name = experiment.name
    db.delete(experiment)

    _write_audit(
        db, current_user.username, "experiment_deleted", experiment_id,
        f"Experiment '{name}' deleted by {current_user.username}",
    )
    db.commit()

    return {"message": "Experiment deleted", "id": experiment_id}


@router.get("/recommendations")
async def get_model_recommendations(
    task_category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get model recommendations based on historical experiments (max 30 days old)."""
    from datetime import timedelta

    CACHE_TTL_DAYS = 30
    cutoff = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)

    query = (
        db.query(ModelPerformanceCache)
        .filter(ModelPerformanceCache.last_updated >= cutoff)
    )
    if task_category:
        query = query.filter(ModelPerformanceCache.task_category == task_category)

    entries = query.order_by(ModelPerformanceCache.avg_quality_score.desc()).all()

    recommendations = [
        {
            "task_category": e.task_category,
            "recommended_model": e.best_model_name,
            "avg_quality_score": e.avg_quality_score,
            "avg_cost_usd": e.avg_cost_usd,
            "avg_latency_ms": e.avg_latency_ms,
            "success_rate": e.success_rate,
            "sample_size": e.sample_size,
            "last_updated": e.last_updated.isoformat() if e.last_updated else None,
        }
        for e in entries
    ]

    return {"recommendations": recommendations, "total_categories": len(recommendations)}


@router.post("/quick-test", response_model=ExperimentSummaryOut)
async def quick_ab_test(
    data: QuickTestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Quick A/B test — creates the experiment and fires it in the background.
    Returns immediately with the experiment summary; the client should poll
    GET /experiments/{id} (or listen for the 'ab_test_update' WebSocket event)
    to get results.
    """
    service = ABTestingService(db)
    experiment = await service.create_experiment(
        name=f"Quick Test {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        task_template=data.task,
        config_ids=data.config_ids,
        iterations=1,
        created_by=current_user.username,
    )

    background_tasks.add_task(service.run_experiment, experiment.id)

    _write_audit(
        db, current_user.username, "quick_test_created", experiment.id,
        f"Quick test launched with {len(data.config_ids)} models",
    )
    db.commit()

    return _serialize_experiment_summary(experiment)


@router.get("/stats", response_model=ABTestingStatsOut)
async def get_ab_testing_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get overall A/B testing statistics in a single query."""
    try:
        # Single-query aggregate using CASE expressions — avoids 5 separate COUNT roundtrips
        row = db.query(
            func.count(Experiment.id).label("total"),
            func.count(
                case((Experiment.status == ExperimentStatus.COMPLETED, 1))
            ).label("completed"),
            func.count(
                case((Experiment.status == ExperimentStatus.RUNNING, 1))
            ).label("running"),
        ).one()

        total_runs = db.query(func.count(ExperimentRun.id)).scalar() or 0
        cache_entries = db.query(func.count(ModelPerformanceCache.id)).scalar() or 0

        return {
            "total_experiments": row.total or 0,
            "completed_experiments": row.completed or 0,
            "running_experiments": row.running or 0,
            "total_model_runs": total_runs,
            "cached_recommendations": cache_entries,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Error getting A/B testing stats: %s", e)
        return {
            "total_experiments": 0,
            "completed_experiments": 0,
            "running_experiments": 0,
            "total_model_runs": 0,
            "cached_recommendations": 0,
        }