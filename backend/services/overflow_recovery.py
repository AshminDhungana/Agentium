"""
Overflow Recovery Service (Task 7.1).

When all agent-ID slots for a tier are exhausted, there is normally no recovery
path: ``ReincarnationService._generate_next_id`` raises ``ValueError`` and new
agents cannot be spawned.

This service implements the recovery flow:

1. A spawn failure (ID-pool exhaustion) or a proactive low-free-slot check
   triggers ``maybe_trigger_overflow_review``.
2. The Head of Council spawns a *temporary* secondary Head (an in-DB ``0xxxx``
   agent — the Head prefix range is otherwise empty) whose sole job is to review
   idle agents and report which can be safely liquidated.
3. While the review runs, new Task-Agent spawns and ``dispatch_task`` are gated
   behind a Redis flag (``overflow_review:in_progress``) so slots free up
   without new load. Lead/Council spawns remain allowed so the review can act.
4. The temporary Head liquidates idle agents that have no active tasks, then
   *hard-reclaims* their rows. This is required because ``_generate_next_id``
   counts every row sharing a prefix (including terminated ones), so normal
   archival liquidation alone would not free the slot. Reclaim is scoped to this
   flow only and runs only on already-safely-liquidated agents.
5. The temporary Head self-terminates (liquidated + row deleted) and the flag is
   cleared, so new task assignment resumes automatically.

The flow is idempotent: the Redis lock + TTL guarantees a single review; if the
temporary Head dies, the TTL clears the flag and a later spawn failure retries.
"""

import logging
import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.entities.agents import Agent, HeadOfCouncil, AgentStatus, AgentType
from backend.models.entities.task import Task, TaskStatus
from backend.models.entities.constitution import Ethos
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.reincarnation_service import ReincarnationService, ID_RANGES

logger = logging.getLogger(__name__)

OVERFLOW_PROACTIVE_THRESHOLD = 50  # free task slots at/below which we proactively review
OVERFLOW_REVIEW_KEY = "overflow_review:in_progress"
OVERFLOW_REPORT_KEY = "overflow_review:report"
OVERFLOW_REVIEW_TTL = 3600  # seconds; safety net so a dead temp head unblocks spawning
IDLE_THRESHOLD_DAYS = 7  # mirrors EnhancedIdleGovernanceEngine.IDLE_THRESHOLD_DAYS


class CapacityRecoveryInProgress(Exception):
    """Raised when a spawn/dispatch is paused because overflow recovery is running."""


def _sync_redis():
    import redis
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return redis.Redis.from_url(url, decode_responses=True)


class OverflowRecoveryService:
    """Static service implementing the temporary-Head overflow recovery flow."""

    # ─────────────────────────────────────────────────────────────
    # Capacity inspection
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def capacity_free_slots(db: Session) -> Dict[str, int]:
        """Return the number of free ID slots per tier from ``ID_RANGES``."""
        free: Dict[str, int] = {}
        for tier, cfg in ID_RANGES.items():
            total = cfg["max"] - cfg["min"] + 1
            used = 0
            for prefix in cfg["prefixes"]:
                used += db.query(func.count(Agent.id)).filter(
                    Agent.agentium_id.like(f"{prefix}%")
                ).scalar() or 0
            free[tier] = max(total - used, 0)
        return free

    # ─────────────────────────────────────────────────────────────
    # Redis flag (idempotency + pause gate)
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def is_review_in_progress() -> bool:
        try:
            return bool(_sync_redis().get(OVERFLOW_REVIEW_KEY))
        except Exception:
            return False

    @staticmethod
    def set_review_in_progress() -> None:
        try:
            _sync_redis().set(OVERFLOW_REVIEW_KEY, "1", ex=OVERFLOW_REVIEW_TTL, nx=True)
        except Exception as e:  # pragma: no cover - redis optional
            logger.warning(f"overflow: failed to set review flag: {e}")

    @staticmethod
    def clear_review_in_progress() -> None:
        try:
            r = _sync_redis()
            r.delete(OVERFLOW_REVIEW_KEY)
            r.delete(OVERFLOW_REPORT_KEY)
        except Exception as e:  # pragma: no cover - redis optional
            logger.warning(f"overflow: failed to clear review flag: {e}")

    @staticmethod
    def _store_report(report: Dict[str, Any]) -> None:
        try:
            import json
            _sync_redis().set(OVERFLOW_REPORT_KEY, json.dumps(report, default=str), ex=OVERFLOW_REVIEW_TTL)
        except Exception:  # pragma: no cover - redis optional
            pass

    @staticmethod
    def get_last_report() -> Optional[Dict[str, Any]]:
        try:
            import json
            raw = _sync_redis().get(OVERFLOW_REPORT_KEY)
            return json.loads(raw) if raw else None
        except Exception:  # pragma: no cover - redis optional
            return None

    # ─────────────────────────────────────────────────────────────
    # Orchestration
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def maybe_trigger_overflow_review(db: Session, reason: str = "capacity check") -> bool:
        """
        Trigger the overflow review if warranted and not already running.

        Returns True if a review was started (and completed), False otherwise.
        """
        if OverflowRecoveryService.is_review_in_progress():
            return False

        free = OverflowRecoveryService.capacity_free_slots(db)
        task_free = free.get("task", 0)
        # Proactive only fires when task slots are scarce; a reactive call
        # (reason="exhausted") always proceeds regardless of the threshold.
        if task_free > OVERFLOW_PROACTIVE_THRESHOLD and reason != "exhausted":
            return False

        # Claim the review with the lock before doing any work.
        OverflowRecoveryService.set_review_in_progress()
        try:
            temp_head = OverflowRecoveryService._spawn_overflow_review_head(db)
            report = OverflowRecoveryService.run_review(db, temp_head)
            OverflowRecoveryService._store_report(report)
            logger.info(f"overflow: review complete -> {report}")
            return True
        except Exception as e:  # pragma: no cover - defensive
            logger.exception(f"overflow: review failed: {e}")
            OverflowRecoveryService.clear_review_in_progress()
            return False

    @staticmethod
    def _spawn_overflow_review_head(db: Session) -> HeadOfCouncil:
        """Create the temporary secondary Head (in-DB ``0xxxx`` agent)."""
        new_id = ReincarnationService.generate_id_with_retry("head", db)

        ethos = Ethos(
            agent_type=AgentType.HEAD_OF_COUNCIL.value,
            mission_statement=(
                "Head of Council — supreme executive authority and final approver. "
                "Persona and conduct are defined by the Constitution, not by Ethos."
            ),
            core_values=json.dumps([]),
            behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]),
            capabilities=json.dumps([]),
            created_by_agentium_id="00001",
            agent_id="00000000-0000-0000-0000-000000000000",
            version=1,
        )
        db.add(ethos)
        db.flush()

        head = HeadOfCouncil(
            agentium_id=new_id,
            name=f"Overflow Recovery Head ({new_id})",
            description=(
                "Temporary Head spawned to review idle agents during capacity "
                "exhaustion. Self-terminates once slots are reclaimed."
            ),
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=True,
            is_temporary_overflow_head=True,
            ethos_id=ethos.id,
            created_by_agentium_id="00001",
        )
        ethos.agent_id = head.id
        db.add(head)
        db.flush()

        AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="system",
            actor_id="OVERFLOW_RECOVERY",
            action="overflow_head_spawned",
            target_type="agent",
            target_id=new_id,
            description=f"Temporary overflow Head {new_id} spawned (capacity recovery).",
        )
        db.flush()
        return head

    @staticmethod
    def _sync_detect_idle(db: Session) -> List[Agent]:
        """Sync mirror of idle detection (non-persistent, idle, excludes temp head)."""
        threshold = datetime.utcnow() - timedelta(days=IDLE_THRESHOLD_DAYS)
        return db.query(Agent).filter(
            Agent.is_active == True,                                   # noqa: E712
            Agent.status == AgentStatus.ACTIVE,
            Agent.is_persistent == False,                              # noqa: E712
            Agent.is_temporary_overflow_head == False,                # noqa: E712
            Agent.last_idle_action_at < threshold,
        ).all()

    @staticmethod
    def _has_active_tasks(db: Session, agentium_id: str) -> bool:
        return db.query(func.count(Task.id)).filter(
            Task.assigned_task_agent_ids.contains([agentium_id]),
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.DELIBERATING]),
            Task.is_active == True,                                   # noqa: E712
        ).scalar() > 0

    @staticmethod
    def run_review(db: Session, temp_head: HeadOfCouncil) -> Dict[str, Any]:
        """
        Review idle agents, reclaim safe ones, self-terminate the temp Head,
        and return a report. Clears the review flag on completion.
        """
        idle = OverflowRecoveryService._sync_detect_idle(db)
        liquidated: List[str] = []
        skipped: List[Dict[str, str]] = []

        for agent in idle:
            if OverflowRecoveryService._has_active_tasks(db, agent.agentium_id):
                skipped.append({"agentium_id": agent.agentium_id, "reason": "has active tasks"})
                continue
            try:
                ReincarnationService.liquidate_agent(
                    agent_id=agent.agentium_id,
                    liquidated_by=temp_head,
                    reason=(
                        "Overflow recovery: idle agent with no active tasks "
                        "reclaimed to free ID slots."
                    ),
                    db=db,
                )
                # Hard-reclaim the row so the ID slot is actually freed
                # (_generate_next_id counts ALL rows regardless of is_active).
                victim = db.query(Agent).filter_by(agentium_id=agent.agentium_id).first()
                if victim:
                    db.delete(victim)
                liquidated.append(agent.agentium_id)
            except Exception as e:
                skipped.append({"agentium_id": agent.agentium_id, "reason": f"error: {e}"})

        db.flush()

        # Self-terminate the temporary Head (liquidate, then hard-delete its row).
        try:
            ReincarnationService.liquidate_agent(
                agent_id=temp_head.agentium_id,
                liquidated_by=temp_head,
                reason="Overflow recovery review complete.",
                db=db,
                force=True,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"overflow: temp head liquidation skipped: {e}")
        temp_row = db.query(Agent).filter_by(agentium_id=temp_head.agentium_id).first()
        if temp_row:
            db.delete(temp_row)
        db.flush()
        db.commit()

        report = {
            "triggered_at": datetime.utcnow().isoformat(),
            "temp_head_id": temp_head.agentium_id,
            "idle_detected": len(idle),
            "liquidated": liquidated,
            "liquidated_count": len(liquidated),
            "skipped": skipped,
            "skipped_count": len(skipped),
        }
        OverflowRecoveryService.clear_review_in_progress()
        return report
