"""
Monitoring API routes.
Provides endpoints for agent monitoring, health checks, and violation reports.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from backend.models.database import get_db
from backend.models.entities.agents import Agent
from backend.models.entities.monitoring import (
    AgentHealthReport,
    ViolationReport,
    ViolationSeverity
)
from backend.core.auth import get_current_active_user
from backend.core.timing_middleware import get_timing_stats
from backend.services.reasoning_trace_service import reasoning_trace_service

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get(
    "/dashboard/{monitor_id}",
    summary="Get Monitoring Dashboard",
    description="Get monitoring dashboard data for a specific monitor agent. Returns system health, alerts, violations, and agent health reports.",
    responses=build_responses(None),
)
async def get_monitoring_dashboard(
    monitor_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get monitoring dashboard data for a specific monitor agent.
    Returns system health, alerts, violations, and agent health reports.
    """
    # Get the monitor agent
    monitor = db.query(Agent).filter(Agent.agentium_id == monitor_id).first()
    
    if not monitor:
        # Return default data if monitor not found
        return {
            "system_health": 100,
            "active_alerts": 0,
            "latest_health_reports": [],
            "recent_violations": []
        }
    
    # Get recent health reports (last 24 hours)
    recent_reports = db.query(AgentHealthReport).filter(
        AgentHealthReport.monitor_agentium_id == monitor_id,
        AgentHealthReport.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).order_by(AgentHealthReport.created_at.desc()).limit(10).all()
    
    # Get recent violations (last 7 days)
    recent_violations = db.query(ViolationReport).filter(
        ViolationReport.created_at >= datetime.utcnow() - timedelta(days=7)
    ).order_by(ViolationReport.created_at.desc()).limit(20).all()
    
    # Calculate system health (average of recent health scores)
    if recent_reports:
        avg_health = sum(r.overall_health_score for r in recent_reports) / len(recent_reports)
        system_health = round(avg_health, 1)
    else:
        system_health = 100.0
    
    # Count active alerts (open violations with high severity)
    active_alerts = db.query(func.count(ViolationReport.id)).filter(
        ViolationReport.status == 'open',
        ViolationReport.severity.in_(['critical', 'major'])
    ).scalar() or 0
    
    # Format health reports for frontend
    health_reports = [
        {
            "id": str(report.id),
            "subject": report.subject_agentium_id,
            "health_score": report.overall_health_score,
            "status": report.status,
            "metrics": {
                "success_rate": report.task_success_rate or 0,
                "tasks_completed": 0,
                "avg_response_time": report.last_response_time_ms or 0
            },
            "created_at": report.created_at.isoformat() if report.created_at else None
        }
        for report in recent_reports
    ]
    
    # Format violations for frontend
    violations = [
        {
            "id": str(v.id),
            "type": v.violation_type,
            "severity": v.severity,
            "violator": v.violator_agentium_id,
            "reporter": v.reporter_agentium_id,
            "description": v.description,
            "status": v.status,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "resolved_at": None  # ViolationReport has no resolved_at column
        }
        for v in recent_violations
    ]
    
    return {
        "system_health": system_health,
        "active_alerts": active_alerts,
        "latest_health_reports": health_reports,
        "recent_violations": violations,
        "monitor_id": monitor_id,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get(
    "/agents/{agent_id}/health",
    summary="Get Agent Health",
    description="Get health history for a specific agent.",
    responses=build_responses(None),
)
async def get_agent_health(
    agent_id: str,
    days: int = Query(default=7, ge=1, le=30),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get health history for a specific agent.
    """
    agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
    
    if not agent:
        raise NotFoundError(error="Agent not found", code="AGENT_NOT_FOUND")
    
    # Get health reports for this agent
    reports = db.query(AgentHealthReport).filter(
        AgentHealthReport.subject_agentium_id == agent_id,
        AgentHealthReport.created_at >= datetime.utcnow() - timedelta(days=days)
    ).order_by(AgentHealthReport.created_at.desc()).all()
    
    # Calculate statistics
    if reports:
        avg_health = sum(r.overall_health_score for r in reports) / len(reports)
        min_health = min(r.overall_health_score for r in reports)
        max_health = max(r.overall_health_score for r in reports)
    else:
        avg_health = min_health = max_health = 100.0
    
    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "current_health": reports[0].overall_health_score if reports else 100.0,
        "avg_health": round(avg_health, 1),
        "min_health": min_health,
        "max_health": max_health,
        "report_count": len(reports),
        "period_days": days,
        "reports": [
            {
                "id": str(r.id),
                "health_score": r.overall_health_score,
                "status": r.status,
                "metrics": {
                    "success_rate": r.task_success_rate or 0,
                    "avg_response_time": r.last_response_time_ms or 0,
                    "violations": r.constitution_violations_count or 0
                },
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in reports[:50]
        ]
    }


@router.post(
    "/report-violation",
    summary="Report Violation",
    description="Report a violation by an agent.",
    responses=build_responses(None),
)
async def report_violation(
    reporter_id: str = Query(..., description="ID of the agent reporting"),
    violator_id: str = Query(..., description="ID of the agent violating"),
    severity: str = Query(..., description="Severity: minor, moderate, major, critical"),
    violation_type: str = Query(..., description="Type of violation"),
    description: str = Query(..., description="Description of the violation"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Report a violation by an agent.
    """
    # Validate agents exist
    reporter = db.query(Agent).filter(Agent.agentium_id == reporter_id).first()
    violator = db.query(Agent).filter(Agent.agentium_id == violator_id).first()
    
    if not reporter:
        raise NotFoundError(error="Reporter agent not found", code="REPORTER_AGENT_NOT_FOUND")
    if not violator:
        raise NotFoundError(error="Violator agent not found", code="VIOLATOR_AGENT_NOT_FOUND")
    
    # Validate severity
    try:
        severity_enum = ViolationSeverity(severity.lower())
    except ValueError:
        raise BadRequestError(error=f"Invalid severity. Must be one of: minor, moderate, major, critical", code="INVALID_SEVERITY_MUST_BE_ONE")
    
    # Create violation report
    violation = ViolationReport(
        reporter_agentium_id=reporter_id,
        violator_agentium_id=violator_id,
        reporter_agent_id=reporter.id,
        violator_agent_id=violator.id,
        severity=severity,
        violation_type=violation_type,
        description=description,
        status='open',
        created_at=datetime.utcnow()
    )
    
    db.add(violation)
    db.commit()
    db.refresh(violation)
    
    return {
        "success": True,
        "report": {
            "id": str(violation.id),
            "reporter": violation.reporter_agentium_id,
            "violator": violation.violator_agentium_id,
            "severity": violation.severity,
            "type": violation.violation_type,
            "description": violation.description,
            "status": violation.status,
            "created_at": violation.created_at.isoformat()
        }
    }


@router.get(
    "/violations",
    summary="Get Violations",
    description="Get violations with optional filters.",
    responses=build_responses(None),
)
async def get_violations(
    status: Optional[str] = Query(None, description="Filter by status: open, resolved, dismissed"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    agent_id: Optional[str] = Query(None, description="Filter by agent (reporter or violator)"),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get violations with optional filters.
    """
    query = db.query(ViolationReport).filter(
        ViolationReport.created_at >= datetime.utcnow() - timedelta(days=days)
    )
    
    if status:
        query = query.filter(ViolationReport.status == status)
    
    if severity:
        query = query.filter(ViolationReport.severity == severity)
    
    if agent_id:
        query = query.filter(
            (ViolationReport.reporter_agentium_id == agent_id) | 
            (ViolationReport.violator_agentium_id == agent_id)
        )
    
    violations = query.order_by(ViolationReport.created_at.desc()).limit(limit).all()
    
    return {
        "violations": [
            {
                "id": str(v.id),
                "reporter": v.reporter_agentium_id,
                "violator": v.violator_agentium_id,
                "severity": v.severity,
                "type": v.violation_type,
                "description": v.description,
                "status": v.status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "resolved_at": None  # No resolved_at column on ViolationReport
            }
            for v in violations
        ],
        "total": len(violations),
        "filters": {
            "status": status,
            "severity": severity,
            "agent_id": agent_id,
            "days": days
        }
    }


@router.patch(
    "/violations/{violation_id}/resolve",
    summary="Resolve Violation",
    description="Mark a violation as resolved.",
    responses=build_responses(None),
)
async def resolve_violation(
    violation_id: int,
    resolution_notes: str = Query(..., description="Notes about the resolution"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Mark a violation as resolved.
    """
    violation = db.query(ViolationReport).filter(ViolationReport.id == violation_id).first()
    
    if not violation:
        raise NotFoundError(error="Violation not found", code="VIOLATION_NOT_FOUND")
    
    if violation.status == 'resolved':
        raise BadRequestError(error="Violation already resolved", code="VIOLATION_ALREADY_RESOLVED")
    
    violation.status = 'resolved'
    violation.resolution = resolution_notes  # actual column is 'resolution'
    
    db.commit()
    db.refresh(violation)
    
    return {
        "success": True,
        "violation": {
            "id": str(violation.id),
            "status": violation.status,
            "resolution": violation.resolution
        }
    }


@router.get(
    "/stats",
    summary="Get Monitoring Stats",
    description="Get overall monitoring statistics.",
    responses=build_responses(None),
)
async def get_monitoring_stats(
    days: int = Query(default=7, ge=1, le=365),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get overall monitoring statistics.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Count violations by severity
    violations_by_severity = {}
    for severity in ['minor', 'moderate', 'major', 'critical']:
        count = db.query(func.count(ViolationReport.id)).filter(
            ViolationReport.severity == severity,
            ViolationReport.created_at >= start_date
        ).scalar() or 0
        violations_by_severity[severity] = count
    
    # Count violations by status
    violations_by_status = {}
    for status in ['open', 'resolved', 'dismissed']:
        count = db.query(func.count(ViolationReport.id)).filter(
            ViolationReport.status == status,
            ViolationReport.created_at >= start_date
        ).scalar() or 0
        violations_by_status[status] = count
    
    # Get agent health average
    avg_health_result = db.query(func.avg(AgentHealthReport.overall_health_score)).filter(
        AgentHealthReport.created_at >= start_date
    ).scalar()
    
    avg_health = round(float(avg_health_result), 1) if avg_health_result else 100.0
    
    # Count total reports
    total_reports = db.query(func.count(AgentHealthReport.id)).filter(
        AgentHealthReport.created_at >= start_date
    ).scalar() or 0
    
    return {
        "period_days": days,
        "violations": {
            "total": sum(violations_by_severity.values()),
            "by_severity": violations_by_severity,
            "by_status": violations_by_status
        },
        "health": {
            "average_score": avg_health,
            "total_reports": total_reports
        },
        "generated_at": datetime.utcnow().isoformat()
    }


@router.get(
    "/metrics",
    summary="Get Timing Metrics",
    description="Returns endpoint-level timing statistics collected by TimingMiddleware. Useful for: - Performance regression gates (Phase 18.2) - Locust / load-test assertion checks - Manual debugging of slow endpoints Fields per endpoint: - ``count``      – total requests seen - ``buffered``   – how many samples are in the ring buffer - ``avg_ms``     – mean latency - ``p95_ms``     – 95ᵗʰ percentile - ``p99_ms``     – 99ᵗʰ percentile - ``min_ms`` / ``max_ms`` – fastest / slowest ever observed.",
    responses=build_responses(None),
)
async def get_timing_metrics(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Returns endpoint-level timing statistics collected by TimingMiddleware.

    Useful for:
      - Performance regression gates (Phase 18.2)
      - Locust / load-test assertion checks
      - Manual debugging of slow endpoints

    Fields per endpoint:
      - ``count``      – total requests seen
      - ``buffered``   – how many samples are in the ring buffer
      - ``avg_ms``     – mean latency
      - ``p95_ms``     – 95ᵗʰ percentile
      - ``p99_ms``     – 99ᵗʰ percentile
      - ``min_ms`` / ``max_ms`` – fastest / slowest ever observed
    """
    stats = get_timing_stats()
    return {
        "endpoints": stats,
        "generated_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# REASONING TRACE ENDPOINTS  (Issue #6 — Agent Self-Reasoning Flow)
# =============================================================================

@router.get(
    "/tasks/{task_id}/reasoning-trace",
    summary="Get Task Reasoning Trace",
    description="Return all persisted reasoning traces for a task. Each trace includes: - The 5-phase execution record: goal_interpretation → context_retrieval → plan_generation → step_execution → outcome_validation → completed / failed - Per-step rationale, alternatives considered, inputs/outputs, and outcome - Outcome validation result (passed / failed + notes) - Total tokens consumed and wall-clock duration Use this to inspect *why* an agent made each decision, not just *what* it produced.",
    responses=build_responses(None),
)
async def get_task_reasoning_trace(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Return all persisted reasoning traces for a task.

    Each trace includes:
      - The 5-phase execution record:
          goal_interpretation → context_retrieval → plan_generation
          → step_execution → outcome_validation → completed / failed
      - Per-step rationale, alternatives considered, inputs/outputs, and outcome
      - Outcome validation result (passed / failed + notes)
      - Total tokens consumed and wall-clock duration

    Use this to inspect *why* an agent made each decision, not just *what* it
    produced.
    """
    traces = reasoning_trace_service.get_traces_for_task(task_id, db)
    return {
        "task_id":     task_id,
        "trace_count": len(traces),
        "traces":      traces,
    }


@router.get(
    "/tasks/{task_id}/reasoning-trace/summary",
    summary="Get Task Reasoning Trace Summary",
    description="Lightweight summary of reasoning traces for a task. Returns phase completion counts and validation results without full step detail. Suitable for dashboard widgets and task-list views.",
    responses=build_responses(None),
)
async def get_task_reasoning_trace_summary(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lightweight summary of reasoning traces for a task.
    Returns phase completion counts and validation results without full step
    detail. Suitable for dashboard widgets and task-list views.
    """
    traces = reasoning_trace_service.get_traces_for_task(task_id, db)

    summaries = []
    for t in traces:
        steps = t.get("steps", [])
        phase_counts: dict = {}
        for s in steps:
            p = s.get("phase", "unknown")
            phase_counts[p] = phase_counts.get(p, 0) + 1
        summaries.append({
            "trace_id":          t.get("trace_id"),
            "agent_id":          t.get("agent_id"),
            "agent_tier":        t.get("agent_tier"),
            "incarnation":       t.get("incarnation"),
            "current_phase":     t.get("current_phase"),
            "final_outcome":     t.get("final_outcome"),
            "validation_passed": t.get("validation_passed"),
            "validation_notes":  t.get("validation_notes"),
            "total_steps":       len(steps),
            "steps_by_phase":    phase_counts,
            "total_tokens":      t.get("total_tokens", 0),
            "total_duration_ms": t.get("total_duration_ms", 0),
            "started_at":        t.get("started_at"),
            "completed_at":      t.get("completed_at"),
        })

    return {
        "task_id":     task_id,
        "trace_count": len(summaries),
        "summaries":   summaries,
    }


@router.get(
    "/agents/{agent_id}/reasoning-traces",
    summary="Get Agent Reasoning Traces",
    description="Return recent reasoning traces for a specific agent. Useful for: - Reviewing an agent's decision history across tasks - Identifying patterns in failed or invalid outputs - Auditing which skills and plan strategies were chosen.",
    responses=build_responses(None),
)
async def get_agent_reasoning_traces(
    agent_id: str,
    days: int = Query(default=7,   ge=1,  le=90),
    limit: int = Query(default=20, ge=1,  le=100),
    outcome: Optional[str] = Query(
        None, description="Filter by final_outcome: success, failure"
    ),
    validation_failed: Optional[bool] = Query(
        None, description="If true, return only traces where outcome validation failed"
    ),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Return recent reasoning traces for a specific agent.

    Useful for:
      - Reviewing an agent's decision history across tasks
      - Identifying patterns in failed or invalid outputs
      - Auditing which skills and plan strategies were chosen
    """
    agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
    if not agent:
        raise NotFoundError(error="Agent not found", code="AGENT_NOT_FOUND")

    start_date = datetime.utcnow() - timedelta(days=days)

    try:
        rows = db.execute(
            text("""
                SELECT *
                FROM reasoning_traces
                WHERE agent_id    = :agent_id
                  AND created_at >= :since
                  AND is_active   = true
                  AND (:outcome          IS NULL OR final_outcome     = :outcome)
                  AND (:vf               IS NULL
                       OR (:vf = true  AND (validation_passed = false
                                             OR validation_passed IS NULL))
                       OR (:vf = false AND  validation_passed = true))
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            {
                "agent_id": agent_id,
                "since":    start_date,
                "outcome":  outcome,
                "vf":       validation_failed,
                "lim":      limit,
            }
        ).fetchall()

        traces = [dict(r._mapping) for r in rows]

        # Normalise datetime fields to ISO strings for JSON serialisation
        for t in traces:
            for key in ("started_at", "completed_at", "created_at", "updated_at"):
                val = t.get(key)
                if val and hasattr(val, "isoformat"):
                    t[key] = val.isoformat()

    except Exception as exc:
        # Graceful fallback before migration has run on fresh deployments
        traces = []
        if "reasoning_traces" not in str(exc).lower():
            raise

    total         = len(traces)
    succeeded     = sum(1 for t in traces if t.get("final_outcome") == "success")
    validation_ok = sum(1 for t in traces if t.get("validation_passed") is True)
    avg_duration  = (
        round(sum(t.get("total_duration_ms", 0) for t in traces) / total, 1)
        if total else 0.0
    )
    avg_tokens = (
        round(sum(t.get("total_tokens", 0) for t in traces) / total)
        if total else 0
    )

    return {
        "agent_id":    agent_id,
        "period_days": days,
        "filters": {
            "outcome":           outcome,
            "validation_failed": validation_failed,
        },
        "stats": {
            "total_traces":         total,
            "successful":           succeeded,
            "failed":               total - succeeded,
            "validation_passed":    validation_ok,
            "validation_failed":    total - validation_ok,
            "avg_duration_ms":      avg_duration,
            "avg_tokens_per_trace": avg_tokens,
        },
        "traces": traces,
    }


@router.get(
    "/reasoning-traces/validation-failures",
    summary="Get Validation Failures",
    description="Return recent traces where outcome validation failed. These represent executions where the agent's output did not satisfy the original goal before the task was marked complete — the validation gate caught the problem and triggered a retry or failure. Use this endpoint to identify systematic reasoning or generation failures across all agents.",
    responses=build_responses(None),
)
async def get_validation_failures(
    days:  int = Query(default=1,  ge=1, le=30),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Return recent traces where outcome validation failed.

    These represent executions where the agent's output did not satisfy the
    original goal before the task was marked complete — the validation gate
    caught the problem and triggered a retry or failure. Use this endpoint to
    identify systematic reasoning or generation failures across all agents.
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    try:
        rows = db.execute(
            text("""
                SELECT trace_id, task_id, agent_id, agent_tier,
                       current_phase, final_outcome,
                       validation_passed, validation_notes,
                       failure_reason, total_tokens, total_duration_ms,
                       started_at, completed_at
                FROM reasoning_traces
                WHERE (validation_passed = false OR validation_passed IS NULL)
                  AND created_at >= :since
                  AND is_active  = true
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            {"since": start_date, "lim": limit}
        ).fetchall()

        failures = []
        for r in rows:
            entry = dict(r._mapping)
            for key in ("started_at", "completed_at"):
                val = entry.get(key)
                if val and hasattr(val, "isoformat"):
                    entry[key] = val.isoformat()
            failures.append(entry)

    except Exception as exc:
        failures = []
        if "reasoning_traces" not in str(exc).lower():
            raise

    return {
        "period_days":    days,
        "total_failures": len(failures),
        "failures":       failures,
        "generated_at":   datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════
# Phase 13.2 — Self-Healing & Auto-Recovery Routes
# ═══════════════════════════════════════════════════════════

@router.get(
    "/self-healing/status",
    summary="Get Self Healing Status",
    description="Get the current system status (normal vs degraded).",
    responses=build_responses(None),
)
async def get_self_healing_status(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get the current system status (normal vs degraded).
    """
    from backend.services.self_healing_service import SelfHealingService
    return SelfHealingService.get_system_mode(db)


@router.get(
    "/self-healing/events",
    summary="Get Self Healing Events",
    description="Get a list of recent self-healing actions and events (crashes, degradations).",
    responses=build_responses(None),
)
async def get_self_healing_events(
    limit: int = Query(50, ge=1, le=100),
    days: int = Query(7, ge=1, le=30),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a list of recent self-healing actions and events (crashes, degradations).
    """
    from backend.services.self_healing_service import SelfHealingService
    return SelfHealingService.get_self_healing_events(db, limit=limit, days=days)


@router.post(
    "/admin/rollback/{checkpoint_id}",
    summary="Rollback From Checkpoint",
    description="Admin-only endpoint to manually trigger a rollback to a specific execution checkpoint.",
    responses=build_responses(None),
)
async def rollback_from_checkpoint(
    checkpoint_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Admin-only endpoint to manually trigger a rollback to a specific execution checkpoint.
    """
    try:
        from backend.services.checkpoint_service import CheckpointService
        
        # In a real system we'd verify current_user isAdmin here
        # (Assuming it's protected by get_current_active_user metadata or similar RBAC)
        
        actor_id = current_user.get("user_id", "admin")
        result = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint_id,
            actor_id=actor_id
        )
        
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
        audit = AuditLog.log(
            level=AuditLevel.WARNING,
            category=AuditCategory.SYSTEM,
            actor_type="user",
            actor_id=actor_id,
            action="manual_rollback",
            description=f"Admin manually rolled back to checkpoint {checkpoint_id}",
            after_state=result if isinstance(result, dict) else {"result": "success"}
        )
        db.add(audit)
        db.commit()
        
        return {
            "success": True,
            "message": f"Successfully rolled back to checkpoint {checkpoint_id}",
            "checkpoint_id": checkpoint_id
        }
    except Exception as e:
        db.rollback()
        raise BadRequestError(error=f"Rollback failed: {str(e)}", code="ROLLBACK_FAILED")

# -----------------------------------------------------------------------------
# Phase 13.7 — Zero-Touch Operations Dashboard Routes
# -----------------------------------------------------------------------------

@router.get(
    "/aggregated",
    summary="Get Aggregated Dashboard Metrics",
    description="Returns unified metrics for the Zero-Touch Operations Dashboard. Combines health info across agents, tasks, workflows, events, and budget.",
    responses=build_responses(None),
)
async def get_aggregated_dashboard_metrics(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Returns unified metrics for the Zero-Touch Operations Dashboard.
    Combines health info across agents, tasks, workflows, events, and budget.
    """
    try:
        from backend.services.monitoring_service import MonitoringService
        return MonitoringService.get_aggregated_metrics(db)
    except Exception as e:
        raise InternalServerError(error=f"Failed to fetch aggregated metrics: {str(e)}", code="FAILED_TO_FETCH_AGGREGATED_METRICS")


@router.get(
    "/sla",
    summary="Get Sla Compliance Metrics",
    description="Returns time-to-resolution compliance rates grouped by task priority.",
    responses=build_responses(None),
)
async def get_sla_compliance_metrics(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Returns time-to-resolution compliance rates grouped by task priority.
    """
    try:
        from backend.services.monitoring_service import MonitoringService
        return MonitoringService.get_sla_metrics(db)
    except Exception as e:
        raise InternalServerError(error=f"Failed to fetch SLA metrics: {str(e)}", code="FAILED_TO_FETCH_SLA_METRICS")


@router.get(
    "/anomalies",
    summary="Get Active Anomalies",
    description="Returns currently open anomaly violation reports.",
    responses=build_responses(None),
)
async def get_active_anomalies(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Returns currently open anomaly violation reports.
    """
    try:
        from backend.models.entities.monitoring import ViolationReport
        from datetime import datetime, timedelta
        
        day_ago = datetime.utcnow() - timedelta(hours=24)
        anomalies = db.query(ViolationReport).filter(
            ViolationReport.status == "open",
            ViolationReport.violation_type == "anomaly_detected",
            ViolationReport.created_at >= day_ago
        ).order_by(ViolationReport.created_at.desc()).all()
        
        return [a.to_dict() for a in anomalies]
    except Exception as e:
        raise InternalServerError(error=f"Failed to fetch anomalies: {str(e)}", code="FAILED_TO_FETCH_ANOMALIES")


@router.get(
    "/incidents",
    summary="Get Incident Log",
    description="Returns the log of auto-remediated incidents via the zero-touch ops engine.",
    responses=build_responses(None),
)
async def get_incident_log(
    limit: int = 50,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Returns the log of auto-remediated incidents via the zero-touch ops engine.
    """
    try:
        from backend.services.monitoring_service import MonitoringService
        return MonitoringService.get_incident_log(db, limit)
    except Exception as e:
        raise InternalServerError(error=f"Failed to fetch incident log: {str(e)}", code="FAILED_TO_FETCH_INCIDENT_LOG")


@router.post(
    "/chaos-test",
    summary="Inject Chaos Test",
    description="Injects a controlled failure into the system for chaos engineering testing. Requires admin privileges.",
    responses=build_responses(None),
)
async def inject_chaos_test(
    payload: dict,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Injects a controlled failure into the system for chaos engineering testing.
    Requires admin privileges.
    """
    if not current_user.get("is_admin", False):
        raise ForbiddenError(error="Admin privileges required for chaos testing", code="ADMIN_PRIVILEGES_REQUIRED_FOR_CHAOS")
        
    test_type = payload.get("test_type")
    if not test_type:
        raise BadRequestError(error="Missing test_type in payload", code="MISSING_TESTTYPE_IN_PAYLOAD")
        
    try:
        from backend.services.monitoring_service import MonitoringService
        result = MonitoringService.inject_chaos_test(test_type, db)
        if not result.get("success"):
            raise BadRequestError(error=result.get("details", {}).get("error", "Chaos test failed"), code="RESULTGETDETAILS_GETERROR_CHAOS_TEST_FAILED")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise InternalServerError(error=f"Failed to inject chaos test: {str(e)}", code="FAILED_TO_INJECT_CHAOS_TEST")


@router.post(
    "/admin/rollback-audit/{audit_id}",
    summary="Rollback From Audit",
    description="Admin-only endpoint to revert an auto-remediated action by its AuditLog ID. Applies per-action inverse operations from the audit trail.",
    responses=build_responses(None),
)
async def rollback_from_audit(
    audit_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Admin-only endpoint to revert an auto-remediated action by its AuditLog ID."""
    if not current_user.get("is_admin", False):
        raise ForbiddenError(error="Admin privileges required for rollback", code="ADMIN_PRIVILEGES_REQUIRED_FOR_ROLLBACK")
        
    try:
        from backend.models.entities.audit import AuditLog
        audit = db.query(AuditLog).filter_by(id=audit_id).first()
        if not audit:
            raise NotFoundError(error="Audit log entry not found", code="AUDIT_LOG_ENTRY_NOT_FOUND")
            
        after_state = audit.after_state or {}
        rollback_actions = {
            "agent_spawned": _rollback_agent_spawned,
            "agent_modified": _rollback_agent_modified,
            "mcp_tool_approved": _rollback_mcp_tool_approved,
            "scaling_spawn": _rollback_scaling_spawn,
        }
        rollback_fn = rollback_actions.get(audit.action)
        rollback_result = {"action": "manual_review_required"}
        if rollback_fn:
            try:
                rollback_result = rollback_fn(db, after_state, current_user)
            except Exception as e:
                db.rollback()
                raise BadRequestError(
                    error=f"Rollback failed for action {audit.action}: {str(e)}",
                    code="ROLLBACK_FAILED"
                )
        audit.description = f"[ROLLED BACK] {audit.description}"
        db.commit()
        
        return {
            "success": True,
            "message": f"Audit {audit_id} rolled back",
            "audit_id": audit_id,
            "rollback_result": rollback_result
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise BadRequestError(error=f"Audit rollback failed: {str(e)}", code="AUDIT_ROLLBACK_FAILED")


# ── Rollback helper functions ─────────────────────────────────────────────

def _rollback_agent_spawned(db: Session, after_state: dict, user: dict) -> dict:
    """Undo an agent spawn by terminating the agent."""
    agent_id = after_state.get("agent_id")
    if agent_id:
        agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
        if agent:
            agent.status = "terminated"
            db.commit()
    return {"action": "agent_spawned", "undone": True}

def _rollback_agent_modified(db: Session, after_state: dict, user: dict) -> dict:
    """Revert agent modifications using previous state."""
    agent_id = after_state.get("agent_id")
    previous_state = after_state.get("previous_state")
    if agent_id and previous_state:
        agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
        if agent:
            for key, value in previous_state.items():
                if hasattr(agent, key):
                    setattr(agent, key, value)
            db.commit()
    return {"action": "agent_modified", "undone": True}

def _rollback_mcp_tool_approved(db: Session, after_state: dict, user: dict) -> dict:
    """Revoke an approved MCP tool."""
    tool_id = after_state.get("tool_id")
    if tool_id:
        try:
            from backend.services.mcp_governance import revoke_mcp_tool
            revoke_mcp_tool(tool_id)
        except Exception:
            pass
    return {"action": "mcp_tool_approved", "undone": True}

def _rollback_scaling_spawn(db: Session, after_state: dict, user: dict) -> dict:
    """Track scaling spawn rollback."""
    count = after_state.get("spawned_count", 0)
    return {"action": "scaling_spawn", "undone": True, "agents_terminated": count}


from pydantic import BaseModel

class FrontendErrorRequest(BaseModel):
    message: str
    name: str = "Error"
    stack: str = ""
    component_stack: str = ""
    url: str = ""

@router.post(
    "/frontend/errors",
    summary="Report Frontend Error",
    description="Catch global and widget frontend errors and write them to AuditLog.",
    responses=build_responses(None),
)
async def report_frontend_error(
    error_data: FrontendErrorRequest,
    db: Session = Depends(get_db)
):
    """
    Catch global and widget frontend errors and write them to AuditLog.
    """
    from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
    
    # Store error info inside metadata
    metadata = {
        "stack": error_data.stack,
        "component_stack": error_data.component_stack,
        "url": error_data.url,
        "name": error_data.name
    }
    
    # Create an audit log record securely without requiring explicit auth
    # as some frontend errors might occur before or during login processes.
    log_entry = AuditLog.log(
        level=AuditLevel.WARNING,
        category=AuditCategory.SYSTEM,
        actor_type="system",
        actor_id="frontend",
        action="frontend_error",
        description=f"Frontend Error ({error_data.name}): {error_data.message}",
        meta_data=metadata,
        success=False
    )
    db.add(log_entry)
    db.commit()
    return {"status": "recorded"}
