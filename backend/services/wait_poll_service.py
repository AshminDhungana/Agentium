"""
WaitPollService — evaluates active WaitConditions and resumes tasks.

Strategy handlers
-----------------
* HTTP_POLL  — GET/POST an endpoint; optionally check a JSONPath value.
* REDIS_KEY  — Check a Redis key for existence or value match.
* TIMEOUT    — Pure time-based; resolves once ``expires_at`` is reached.
* WEBHOOK    — Condition is resolved externally; poller just cleans up expired ones.
* MANUAL     — No automatic resolution; operator must call ``resolve_condition()``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.models.entities.wait_condition import (
    WaitCondition,
    WaitConditionStatus,
    WaitStrategy,
)
from backend.models.entities.task import Task, TaskStatus
from backend.models.entities.remote_execution import RemoteExecutionRecord, ExecutionStatus

logger = logging.getLogger(__name__)


class WaitPollService:
    """
    Stateless service — all methods are class methods so they can be called
    from Celery tasks without instantiation overhead.
    """

    # ─────────────────────────────────────────────────────────────────────
    # Public entry points
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def create_condition(
        cls,
        db: Session,
        task_id: str,
        strategy: WaitStrategy,
        config: Dict[str, Any],
        *,
        max_attempts: int = 60,
        poll_interval_seconds: int = 30,
        timeout_seconds: Optional[int] = None,
        created_by_agent_id: Optional[str] = None,
    ) -> WaitCondition:
        """
        Create a new WaitCondition and immediately activate it.

        If ``timeout_seconds`` is provided, ``expires_at`` is set accordingly
        regardless of strategy.
        """
        expires_at = None
        if timeout_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)
        elif strategy == WaitStrategy.TIMEOUT:
            secs = config.get("seconds", 60)
            expires_at = datetime.utcnow() + timedelta(seconds=secs)

        condition = WaitCondition(
            task_id=task_id,
            strategy=strategy,
            config=config,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
            expires_at=expires_at,
            created_by_agent_id=created_by_agent_id,
            status=WaitConditionStatus.ACTIVE,
        )
        db.add(condition)
        db.flush()
        logger.info("WaitCondition %s created for task %s (strategy=%s)",
                    condition.agentium_id, task_id, strategy.value)
        return condition

    @classmethod
    def poll_all_active(cls, db: Session) -> Dict[str, int]:
        """
        Evaluate every ACTIVE WaitCondition.  Called by the Celery beat task.

        Returns a summary dict: { resolved, expired, errors, skipped }.
        """
        summary = {"resolved": 0, "expired": 0, "errors": 0, "skipped": 0}

        active = (
            db.query(WaitCondition)
            .filter(WaitCondition.status == WaitConditionStatus.ACTIVE)
            .all()
        )

        for condition in active:
            try:
                result = cls._evaluate(db, condition)
                if result == "resolved":
                    summary["resolved"] += 1
                elif result == "expired":
                    summary["expired"] += 1
                else:
                    summary["skipped"] += 1
            except Exception as exc:
                summary["errors"] += 1
                logger.error("Error evaluating WaitCondition %s: %s",
                             condition.agentium_id, exc, exc_info=True)

        db.commit()
        logger.info("WaitPollService.poll_all_active summary: %s", summary)
        return summary

    @classmethod
    def resolve_condition(
        cls,
        db: Session,
        condition_id: str,
        data: Optional[Dict] = None,
    ) -> bool:
        """
        Manually resolve a WaitCondition (e.g. from a webhook handler).

        Returns True if the task was successfully resumed.
        """
        condition = db.query(WaitCondition).filter(
            WaitCondition.id == condition_id
        ).first()
        if not condition or condition.status != WaitConditionStatus.ACTIVE:
            return False

        condition.resolve(data)
        cls._resume_task(db, condition)
        db.commit()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Internal evaluation dispatch
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def _evaluate(cls, db: Session, condition: WaitCondition) -> str:
        """
        Evaluate a single condition.

        Returns: "resolved" | "expired" | "pending" | "failed"
        """
        # Hard deadline check (always first)
        if condition.is_overdue():
            condition.expire("deadline_exceeded")
            cls._handle_expired(db, condition)
            return "expired"

        # Attempt budget check
        if not condition.increment_attempt():
            condition.expire("max_attempts_exceeded")
            cls._handle_expired(db, condition)
            return "expired"

        # Strategy dispatch
        resolved, data = cls._check_strategy(db, condition)

        if resolved:
            # Check if the execution failed - if so, fail the task instead of resuming
            if data and data.get("status") == "failed":
                condition.resolve(data)
                cls._handle_failed_execution(db, condition, data.get("error"))
                return "failed"
            else:
                condition.resolve(data)
                cls._resume_task(db, condition)
                return "resolved"

        return "pending"

    @classmethod
    def _check_strategy(
        cls, db: Session, condition: WaitCondition
    ) -> Tuple[bool, Optional[Dict]]:
        """Dispatch to the appropriate strategy checker."""
        strategy = condition.strategy
        cfg      = condition.config or {}

        if strategy == WaitStrategy.HTTP_POLL:
            return cls._check_http(cfg)
        elif strategy == WaitStrategy.REDIS_KEY:
            return cls._check_redis(cfg)
        elif strategy == WaitStrategy.TIMEOUT:
            # Pure timeout — already handled by is_overdue(); if we get here,
            # it hasn't expired yet.
            return False, None
        elif strategy == WaitStrategy.EXECUTION:
            return cls._check_execution(db, cfg)
        elif strategy in (WaitStrategy.WEBHOOK, WaitStrategy.MANUAL):
            # These are resolved externally; nothing to poll.
            return False, None

        logger.warning("Unknown WaitStrategy: %s", strategy)
        return False, None

    # ── HTTP Poll ─────────────────────────────────────────────────────────

    @classmethod
    def _check_http(cls, cfg: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Poll an HTTP endpoint.

        Config keys:
          url             (required)
          method          GET | POST  (default: GET)
          headers         dict        (optional)
          body            dict        (optional, for POST)
          expected_status int         (default: 200)
          jsonpath        str         (optional dotted path, e.g. "data.status")
          expected_value  any         (optional; if omitted, status code suffices)
        """
        import httpx

        url     = cfg.get("url")
        if not url:
            return False, None

        method          = cfg.get("method", "GET").upper()
        headers         = cfg.get("headers", {})
        body            = cfg.get("body")
        expected_status = int(cfg.get("expected_status", 200))
        jsonpath        = cfg.get("jsonpath")
        expected_value  = cfg.get("expected_value")

        try:
            with httpx.Client(timeout=10) as client:
                if method == "POST":
                    resp = client.post(url, json=body, headers=headers)
                else:
                    resp = client.get(url, headers=headers)

            if resp.status_code != expected_status:
                return False, None

            if jsonpath is not None:
                try:
                    value = cls._extract_jsonpath(resp.json(), jsonpath)
                    if expected_value is not None and str(value) != str(expected_value):
                        return False, None
                    return True, {"status_code": resp.status_code, "value": value}
                except Exception:
                    return False, None

            return True, {"status_code": resp.status_code}

        except Exception as exc:
            logger.debug("HTTP poll failed: %s", exc)
            return False, None

    @staticmethod
    def _extract_jsonpath(data: Any, path: str) -> Any:
        """Resolve a simple dotted path like 'data.status' in a JSON dict."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    # ── Redis Key ─────────────────────────────────────────────────────────

    @classmethod
    def _check_redis(cls, cfg: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Config keys:
          key            (required)
          expected_value  optional; if omitted, key existence resolves condition
          match_type      exists | eq | gt  (default: exists)
        """
        import os
        import redis as sync_redis

        redis_url  = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
        key        = cfg.get("key")
        if not key:
            return False, None

        match_type     = cfg.get("match_type", "exists")
        expected_value = cfg.get("expected_value")

        try:
            r   = sync_redis.from_url(redis_url, decode_responses=True)
            val = r.get(key)

            if match_type == "exists":
                resolved = val is not None
            elif match_type == "eq":
                resolved = str(val) == str(expected_value)
            elif match_type == "gt":
                resolved = val is not None and float(val) > float(expected_value)
            else:
                resolved = val is not None

            return resolved, {"key": key, "value": val} if resolved else (False, None)

        except Exception as exc:
            logger.debug("Redis poll failed for key '%s': %s", key, exc)
            return False, None

    # ── Execution ───────────────────────────────────────────────────────────

    @classmethod
    def _check_execution(cls, db: Session, cfg: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Poll a RemoteExecutionRecord by execution_id.

        Config keys:
          execution_id   (required) — the execution_id returned by RemoteExecutorService
        """
        execution_id = cfg.get("execution_id")
        if not execution_id:
            logger.warning("_check_execution: missing execution_id in config")
            return False, None

        # Query database for the execution record using the passed session
        record = db.query(RemoteExecutionRecord).filter(
            RemoteExecutionRecord.execution_id == execution_id
        ).first()

        if not record:
            logger.debug("_check_execution: execution %s not yet in DB", execution_id)
            return False, None

        status = record.status
        if status == ExecutionStatus.COMPLETED:
            return True, {
                "execution_id": execution_id,
                "status": "completed",
                "summary": record.summary,
                "execution_time_ms": record.execution_time_ms,
            }
        elif status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT, ExecutionStatus.CANCELLED):
            return True, {
                "execution_id": execution_id,
                "status": "failed",
                "error": record.error_message,
            }
        else:
            # PENDING, RUNNING → still waiting
            return False, None

    # ─────────────────────────────────────────────────────────────────────
    # Task resumption
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def _resume_task(cls, db: Session, condition: WaitCondition) -> None:
        """Transition the parent task from WAITING → IN_PROGRESS."""
        task = db.query(Task).filter(Task.id == condition.task_id).first()
        if not task:
            logger.warning("Cannot resume: task %s not found", condition.task_id)
            return

        if task.status != TaskStatus.WAITING:
            logger.info("Task %s is not in WAITING state (current: %s); skip resume",
                        task.id, task.status)
            return

        try:
            task.set_status(TaskStatus.IN_PROGRESS, actor_id="wait_poll_service",
                            note=f"WaitCondition {condition.agentium_id} resolved")
            logger.info("Task %s resumed from WAITING → IN_PROGRESS", task.agentium_id)

            # Broadcast via WebSocket (best-effort)
            cls._broadcast_resolved(task, condition)
        except Exception as exc:
            logger.error("Failed to resume task %s: %s", task.id, exc)

    @classmethod
    def _handle_expired(cls, db: Session, condition: WaitCondition) -> None:
        """Transition the parent task to FAILED when the condition expires."""
        task = db.query(Task).filter(Task.id == condition.task_id).first()
        if not task or task.status != TaskStatus.WAITING:
            return
        try:
            task.fail(
                error_message=f"WaitCondition {condition.agentium_id} expired: "
                              f"{condition.failure_reason}",
                can_retry=False,
            )
            logger.warning("Task %s failed due to expired WaitCondition", task.agentium_id)
        except Exception as exc:
            logger.error("Failed to mark task %s as failed: %s", task.id, exc)

    @classmethod
    def _handle_failed_execution(cls, db: Session, condition: WaitCondition, error: str) -> None:
        """Transition the parent task to FAILED when the execution fails."""
        task = db.query(Task).filter(Task.id == condition.task_id).first()
        if not task or task.status != TaskStatus.WAITING:
            return
        try:
            # WAITING -> FAILED is a valid transition; WAITING -> ESCALATED is NOT.
            # Use set_status directly instead of task.fail() which tries to escalate.
            task.set_status(
                TaskStatus.FAILED,
                actor_id="wait_poll_service",
                note=f"WaitCondition {condition.agentium_id} execution failed: {error}",
            )
            logger.warning("Task %s failed due to failed execution", task.agentium_id)
        except Exception as exc:
            logger.error("Failed to mark task %s as failed: %s", task.id, exc)

    @classmethod
    def _broadcast_resolved(cls, task: Task, condition: WaitCondition) -> None:
        """Push a ``wait_resolved`` event to connected WebSocket clients."""
        try:
            import asyncio
            from backend.api.routes.websocket import manager

            payload = {
                "type":          "wait_resolved",
                "task_id":       str(task.id),
                "task_agentium": task.agentium_id,
                "condition_id":  str(condition.id),
                "strategy":      condition.strategy.value,
                "resolved_at":   condition.resolved_at.isoformat()
                                 if condition.resolved_at else None,
            }

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(manager.broadcast(payload))
            finally:
                loop.close()
        except Exception as exc:
            logger.debug("WebSocket broadcast for wait_resolved skipped: %s", exc)