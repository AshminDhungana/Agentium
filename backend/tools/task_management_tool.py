"""Task Management Tool — first-class programmatic task CRUD for agents.

Exposes a single `task_management` tool with actions `create | get | update |
list | close | help`. It is wired into the existing Task/DAG models
(`backend.models.entities.task.Task`) and registered through the standard
`ToolRegistry.register_tool` pattern.

Tier policy (enforced inside `execute`, not just at registration):
  * Lead+  (0xxxx / 1xxxx / 2xxxx) may create and close tasks, and update any
    field of any task.
  * Task   (3xxxx–6xxxx) agents may only update the *status* of a task that is
    assigned to them (`Task.assigned_task_agent_ids` contains their id).
  * Any authorized tier may `get` or `list` tasks.

The service layer (`ToolCreationService.execute_tool`) injects `agent_id`
(= the calling agent's id) and `db` for tools that declare those parameters;
this tool opens its own session via `get_db_context()` for isolation from a
potentially poisoned caller session.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Agent tiers that may use this tool (Head/Council/Lead/Task).
_AUTHORIZED_TIERS = [f"{i}xxxx" for i in range(7)]
# Tiers allowed to create / close / freely edit tasks.
_GOVERNANCE_PREFIXES = {"0", "1", "2"}


def _tier_prefix(agent_id: Optional[str]) -> str:
    return (agent_id or "")[:1]


def _is_governance(agent_id: Optional[str]) -> bool:
    return _tier_prefix(agent_id) in _GOVERNANCE_PREFIXES


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _serialize(task) -> Dict[str, Any]:
    assigned = task.assigned_task_agent_ids
    if not isinstance(assigned, list):
        assigned = []
    return {
        "id": str(task.id),
        "agentium_id": task.agentium_id,
        "title": task.title or "",
        "description": task.description or "",
        "status": task.status.value if task.status else "pending",
        "priority": task.priority.value if task.priority else "normal",
        "task_type": task.task_type.value if task.task_type else "execution",
        "progress": task.completion_percentage or 0,
        "created_by": task.created_by,
        "lead_agent_id": task.lead_agent_id,
        "assigned_task_agent_ids": assigned,
        "parent_task_id": task.parent_task_id,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if getattr(task, "updated_at", None) else None,
    }


class TaskManagementTool:
    TOOL_NAME = "task_management"
    AUTHORIZED_TIERS = _AUTHORIZED_TIERS

    # ── Entry point ──────────────────────────────────────────────────────────

    async def execute(
        self,
        action: str,
        agent_id: Optional[str] = None,
        db: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if action == "help":
            return {
                "status": "success",
                "description": (
                    "First-class task management for agents. Actions: "
                    "create, get, update, list, close. Lead+ agents (0xxxx/1xxxx/2xxxx) "
                    "may create and close tasks and edit any field; Task agents "
                    "(3xxxx-6xxxx) may only update the status of tasks assigned to them."
                ),
                "actions": ["create", "get", "update", "list", "close"],
            }
        if action == "create":
            return self._create(agent_id, **kwargs)
        if action == "get":
            return self._get(**kwargs)
        if action == "update":
            return self._update(agent_id, **kwargs)
        if action == "list":
            return self._list(**kwargs)
        if action == "close":
            return self._close(agent_id, **kwargs)
        return {"status": "error", "error": f"Unknown action: {action}"}

    # ── Actions ──────────────────────────────────────────────────────────────

    def _create(self, agent_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        if not _is_governance(agent_id):
            return {
                "status": "error",
                "error": "Only Lead+ agents (0xxxx/1xxxx/2xxxx) may create tasks.",
            }
        description = (kwargs.get("description") or "").strip()
        if not description:
            return {"status": "error", "error": "description is required to create a task"}

        from backend.models.entities.task import (
            Task,
            TaskPriority,
            TaskStatus,
            TaskType,
        )
        from backend.models.entities.task_events import TaskEvent, TaskEventType
        from backend.models.database import get_db_context

        title = (kwargs.get("title") or "").strip() or None
        try:
            priority = TaskPriority(kwargs.get("priority", "normal"))
        except ValueError:
            priority = TaskPriority.NORMAL
        try:
            task_type = TaskType(kwargs.get("task_type", "execution"))
        except ValueError:
            task_type = TaskType.EXECUTION

        assigned = kwargs.get("assigned_to") or []
        if not isinstance(assigned, list):
            assigned = [assigned]

        with get_db_context() as db:
            task = Task(
                title=title,
                description=description,
                priority=priority,
                task_type=task_type,
                status=TaskStatus.PENDING,
                created_by=(agent_id or "system")[:10],
                lead_agent_id=kwargs.get("lead_agent_id"),
                assigned_task_agent_ids=assigned,
                parent_task_id=kwargs.get("parent_task_id"),
                due_date=_parse_dt(kwargs.get("due_date")),
                constitutional_basis=kwargs.get("constitutional_basis"),
            )
            db.add(task)
            db.flush()
            db.add(
                TaskEvent(
                    task_id=task.id,
                    event_type=TaskEventType.TASK_CREATED,
                    actor_id=(agent_id or "system")[:10],
                    actor_type="agent",
                    data={
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority.value,
                        "task_type": task.task_type.value,
                        "created_by": task.created_by,
                    },
                )
            )
            out = _serialize(task)
        return {"status": "success", "task": out}

    def _get(self, **kwargs: Any) -> Dict[str, Any]:
        task_id = kwargs.get("task_id") or kwargs.get("id")
        if not task_id:
            return {"status": "error", "error": "task_id is required for action 'get'"}
        from backend.models.entities.task import Task
        from backend.models.database import get_db_context

        with get_db_context() as db:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task is None:
                task = db.query(Task).filter(Task.agentium_id == str(task_id)).first()
            if task is None:
                return {"status": "error", "error": f"Task '{task_id}' not found"}
            out = _serialize(task)
        return {"status": "success", "task": out}

    def _update(self, agent_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        task_id = kwargs.get("task_id") or kwargs.get("id")
        if not task_id:
            return {"status": "error", "error": "task_id is required for action 'update'"}

        from backend.models.entities.task import Task
        from backend.models.database import get_db_context

        with get_db_context() as db:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task is None:
                task = db.query(Task).filter(Task.agentium_id == str(task_id)).first()
            if task is None:
                return {"status": "error", "error": f"Task '{task_id}' not found"}

            governance = _is_governance(agent_id)
            assigned = task.assigned_task_agent_ids or []
            if not isinstance(assigned, list):
                assigned = []

            # Task-tier agents may ONLY update status, and only on their own task.
            if not governance:
                if (agent_id or "") not in assigned:
                    return {
                        "status": "error",
                        "error": "Task-tier agents may only update tasks assigned to them.",
                    }
                if "status" not in kwargs:
                    return {
                        "status": "error",
                        "error": "Task-tier agents may only update the 'status' field.",
                    }
                allowed = {"status"}
                extra = set(kwargs.keys()) & (
                    {"title", "description", "priority", "task_type",
                     "assigned_to", "lead_agent_id", "parent_task_id",
                     "due_date", "progress", "result_summary"}
                )
                if extra:
                    return {
                        "status": "error",
                        "error": f"Task-tier agents cannot update: {sorted(extra)}",
                    }

            # Apply field updates.
            if "title" in kwargs:
                task.title = (kwargs["title"] or "").strip() or None
            if "description" in kwargs:
                task.description = kwargs["description"]
            if "priority" in kwargs:
                from backend.models.entities.task import TaskPriority
                try:
                    task.priority = TaskPriority(kwargs["priority"])
                except ValueError:
                    pass
            if "task_type" in kwargs:
                from backend.models.entities.task import TaskType
                try:
                    task.task_type = TaskType(kwargs["task_type"])
                except ValueError:
                    pass
            if "assigned_to" in kwargs:
                val = kwargs["assigned_to"] or []
                task.assigned_task_agent_ids = val if isinstance(val, list) else [val]
            if "lead_agent_id" in kwargs:
                task.lead_agent_id = kwargs["lead_agent_id"]
            if "parent_task_id" in kwargs:
                task.parent_task_id = kwargs["parent_task_id"]
            if "due_date" in kwargs:
                task.due_date = _parse_dt(kwargs["due_date"])
            if "progress" in kwargs:
                try:
                    task.completion_percentage = int(kwargs["progress"])
                except (ValueError, TypeError):
                    pass
            if "result_summary" in kwargs:
                task.result_summary = kwargs["result_summary"]

            if "status" in kwargs:
                err = self._set_status(task, kwargs["status"])
                if err:
                    return {"status": "error", "error": err}

            out = _serialize(task)
        return {"status": "success", "task": out}

    def _list(self, **kwargs: Any) -> Dict[str, Any]:
        from backend.models.entities.task import Task
        from backend.models.database import get_db_context

        status_filter = kwargs.get("status_filter") or kwargs.get("status")
        assigned_to = kwargs.get("assigned_to")
        parent_task_id = kwargs.get("parent_task_id")
        limit = kwargs.get("limit", 100)
        try:
            limit = max(1, min(int(limit), 1000))
        except (ValueError, TypeError):
            limit = 100

        with get_db_context() as db:
            query = db.query(Task)
            if status_filter:
                from backend.models.entities.task import TaskStatus
                try:
                    query = query.filter(Task.status == TaskStatus(status_filter))
                except ValueError:
                    pass
            if parent_task_id:
                query = query.filter(Task.parent_task_id == parent_task_id)
            if assigned_to:
                query = query.filter(Task.assigned_task_agent_ids.contains([assigned_to]))
            tasks = query.order_by(Task.created_at.desc()).limit(limit).all()
            items = [_serialize(t) for t in tasks]
        return {"status": "success", "count": len(items), "tasks": items}

    def _close(self, agent_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        if not _is_governance(agent_id):
            return {
                "status": "error",
                "error": "Only Lead+ agents (0xxxx/1xxxx/2xxxx) may close tasks.",
            }
        task_id = kwargs.get("task_id") or kwargs.get("id")
        if not task_id:
            return {"status": "error", "error": "task_id is required for action 'close'"}

        outcome = (kwargs.get("outcome") or "completed").lower()
        if outcome not in {"completed", "cancelled"}:
            return {"status": "error", "error": "outcome must be 'completed' or 'cancelled'"}

        from backend.models.entities.task import Task
        from backend.models.database import get_db_context

        with get_db_context() as db:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task is None:
                task = db.query(Task).filter(Task.agentium_id == str(task_id)).first()
            if task is None:
                return {"status": "error", "error": f"Task '{task_id}' not found"}
            if kwargs.get("result_summary"):
                task.result_summary = kwargs["result_summary"]
            err = self._set_status(task, outcome)
            if err:
                return {"status": "error", "error": err}
            out = _serialize(task)
        return {"status": "success", "task": out}

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _set_status(task, proposed: str) -> Optional[str]:
        """Validate and apply a status change via the task state machine.

        Returns an error string on failure, or None on success.
        """
        from backend.models.entities.task import TaskStatus
        from backend.services.task_state_machine import (
            IllegalStateTransition,
            TaskStateMachine,
        )

        try:
            new_status = TaskStatus(proposed)
        except ValueError:
            return (
                f"Invalid status '{proposed}'. Valid: "
                f"{[s.value for s in TaskStatus]}"
            )
        current = task.status
        if current == new_status:
            return None
        try:
            TaskStateMachine.validate_transition(current, new_status)
        except IllegalStateTransition as exc:
            return str(exc)
        task.status = new_status
        if new_status == TaskStatus.COMPLETED:
            from datetime import datetime as _dt
            task.completed_at = _dt.utcnow()
            task.completion_percentage = task.completion_percentage or 100
        return None


task_management_tool = TaskManagementTool()


async def execute(action: str, **kwargs: Any) -> Dict[str, Any]:
    """Module-level entry point — delegates to the singleton instance."""
    return await task_management_tool.execute(action, **kwargs)


# Required by ToolFactory.load_tool() dynamic loader (same as other tools)
tool_instance = task_management_tool
