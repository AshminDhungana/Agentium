"""
Dashboard Summary API
─────────────────────
GET /api/v1/dashboard/summary

Returns pre-aggregated stats for the frontend Dashboard in a single round-trip,
replacing the two parallel GET /agents + GET /tasks/ calls the browser used to
make independently.

The response is intentionally lightweight — it is designed for the stat cards
and small activity widgets.  Pages that need full agent / task objects (e.g. the
dedicated Agents page) continue to use their own endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List

from fastapi        import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.schemas.examples    import ErrorResponseExample, SuccessResponseExample
from backend.models.database         import get_db
from backend.models.entities         import Agent, Task
from backend.models.entities.agents  import AgentStatus
from backend.core.auth               import get_current_active_user

router = APIRouter(tags=["Dashboard"])


# ── Internal constants ────────────────────────────────────────────────────────

_ACTIVE_STATUSES = frozenset({
    AgentStatus.ACTIVE,
    AgentStatus.WORKING,
    AgentStatus.DELIBERATING,
})

_PENDING_TASK_STATUSES = frozenset({"pending", "deliberating"})

_AGENT_STATUS_WEIGHT: Dict[AgentStatus, int] = {
    AgentStatus.WORKING:      0,
    AgentStatus.ACTIVE:       1,
    AgentStatus.DELIBERATING: 2,
    AgentStatus.INITIALIZING: 3,
    AgentStatus.SUSPENDED:    4,
}


# ── Helper serialisers ────────────────────────────────────────────────────────

def _agent_summary(agent: Agent) -> Dict[str, Any]:
    """Lightweight dict for the active-agents widget (top-6)."""
    d = agent.to_dict()
    return {
        "id":                 d.get("id"),
        "name":               d.get("name"),
        "status":             d.get("status"),
        "agent_type":         d.get("agent_type"),
        "current_task_title": d.get("current_task_title"),
        "health_score":       d.get("health_score"),
    }


def _task_summary(task: Task) -> Dict[str, Any]:
    """Lightweight dict for the recent-tasks widget (latest-5)."""
    d = task.to_dict()
    return {
        "id":         d.get("id"),
        "title":      d.get("title"),
        "status":     d.get("status"),
        "priority":   d.get("priority"),
        "progress":   d.get("progress", 0),
        "updated_at": d.get("updated_at"),
        "created_at": d.get("created_at"),
    }


def _task_date_key(task: Task) -> datetime:
    """Sort key for most-recently-updated ordering."""
    ts = task.updated_at or task.created_at
    if ts is None:
        return datetime.min
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return datetime.min
    return ts  # already a datetime


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get(
    "/dashboard/summary",
    summary="Get dashboard summary",
    description="Pre-aggregated stats for the frontend Dashboard in a single round-trip.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
def get_dashboard_summary(
    current_user: dict    = Depends(get_current_active_user),
    db:           Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Aggregated dashboard summary — agents + tasks in a single call.

    Intended for the frontend Dashboard page so it can populate all stat
    cards and activity widgets without making N separate API calls.
    Responses are cheap to generate (no heavy joins) and can be cached at
    the HTTP layer or behind Redis if needed in the future.
    """

    # ── Agents ────────────────────────────────────────────────────────────────
    all_agents: List[Agent] = (
        db.query(Agent)
        .filter(Agent.is_terminated.is_(False))
        .all()
    )

    active_count   = sum(1 for a in all_agents if a.status in _ACTIVE_STATUSES)
    working_count  = sum(1 for a in all_agents if a.status == AgentStatus.WORKING)
    suspended_count= sum(1 for a in all_agents if a.status == AgentStatus.SUSPENDED)

    # Top-6 agents sorted by "busyness" for the widget
    visible_agents = [
        a for a in all_agents
        if a.status != AgentStatus.TERMINATED
    ]
    visible_agents.sort(key=lambda a: _AGENT_STATUS_WEIGHT.get(a.status, 99))
    top_agents = visible_agents[:6]

    # ── Tasks ─────────────────────────────────────────────────────────────────
    all_tasks: List[Task] = db.query(Task).all()

    pending_count     = sum(1 for t in all_tasks if t.status in _PENDING_TASK_STATUSES)
    in_progress_count = sum(1 for t in all_tasks if t.status == "in_progress")
    completed_count   = sum(1 for t in all_tasks if t.status == "completed")
    failed_count      = sum(1 for t in all_tasks if t.status == "failed")

    recent_tasks = sorted(all_tasks, key=_task_date_key, reverse=True)[:5]

    # ── Response ──────────────────────────────────────────────────────────────
    return {
        "agents": {
            "total":     len(all_agents),
            "active":    active_count,
            "working":   working_count,
            "suspended": suspended_count,
        },
        "tasks": {
            "total":       len(all_tasks),
            "pending":     pending_count,
            "in_progress": in_progress_count,
            "completed":   completed_count,
            "failed":      failed_count,
        },
        "recent_tasks":  [_task_summary(t) for t in recent_tasks],
        "active_agents": [_agent_summary(a) for a in top_agents],
        "generated_at":  datetime.utcnow().isoformat(),
    }