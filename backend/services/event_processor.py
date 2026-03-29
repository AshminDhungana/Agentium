"""
Phase 13.6 — Intelligent Event Processor
==========================================
Core service for processing inbound webhook events, evaluating threshold
breaches, polling external APIs, correlating events, and managing the
dead-letter queue.
"""
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis
from sqlalchemy.orm import Session

from backend.models.entities.event_trigger import (
    EventLog,
    EventLogStatus,
    EventTrigger,
    TriggerType,
)

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ── Helpers ───────────────────────────────────────────────────────────────────

def verify_hmac(secret: str, body: bytes, signature: str) -> bool:
    """Validate HMAC-SHA256: signature must be 'sha256=<hex>'."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature[7:])


def _is_duplicate(correlation_id: str) -> bool:
    """24-hour Redis deduplication by correlation_id."""
    r = _get_redis()
    key = f"agentium:event:dedup:{correlation_id}"
    if r.exists(key):
        return True
    r.setex(key, 86400, "1")
    return False


def _is_trigger_paused(trigger: EventTrigger) -> bool:
    """Return True when the trigger's circuit breaker is active."""
    if trigger.paused_until and trigger.paused_until > datetime.utcnow():
        return True
    return False


def _check_rate_limit(trigger: EventTrigger, db: Session) -> bool:
    """
    If a trigger fires more than max_fires_per_minute within the last
    60 seconds, pause the trigger.  Returns True if rate is exceeded.
    """
    r = _get_redis()
    key = f"agentium:event:ratelimit:{trigger.id}"
    current = r.get(key)
    if current and int(current) >= trigger.max_fires_per_minute:
        trigger.paused_until = datetime.utcnow() + timedelta(
            seconds=trigger.pause_duration_seconds
        )
        db.commit()
        logger.warning(
            "Event trigger %s rate-limited — paused for %ss",
            trigger.name, trigger.pause_duration_seconds,
        )
        return True
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60)
    pipe.execute()
    return False


# ── Webhook Processing ────────────────────────────────────────────────────────

class EventProcessorService:
    """Stateless service — all methods accept a SQLAlchemy session."""

    # ── Webhook ingestion ─────────────────────────────────────────────────

    @staticmethod
    def receive_webhook(
        db: Session,
        trigger_id: str,
        body: bytes,
        signature: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate an incoming webhook POST, deduplicate, and enqueue for
        processing.  Returns a dict describing the outcome.
        """
        trigger = (
            db.query(EventTrigger)
            .filter(EventTrigger.id == trigger_id, EventTrigger.is_active == True)
            .first()
        )
        if not trigger:
            return {"status": "error", "detail": "Trigger not found or inactive"}

        if trigger.trigger_type != TriggerType.WEBHOOK:
            return {"status": "error", "detail": "Trigger is not of type webhook"}

        if _is_trigger_paused(trigger):
            return {"status": "paused", "detail": "Trigger is rate-limited"}

        # HMAC validation
        secret = (trigger.config or {}).get("hmac_secret", "")
        if secret and not verify_hmac(secret, body, signature):
            return {"status": "error", "detail": "Invalid HMAC signature"}

        # Deduplication
        cid = correlation_id or str(uuid.uuid4())
        if _is_duplicate(cid):
            log = EventLog(
                trigger_id=trigger.id,
                event_payload=json.loads(body) if body else {},
                status=EventLogStatus.DUPLICATE,
                correlation_id=cid,
            )
            db.add(log)
            db.commit()
            return {"status": "duplicate", "correlation_id": cid}

        # Rate limit check
        if _check_rate_limit(trigger, db):
            return {"status": "paused", "detail": "Rate limit exceeded"}

        # Persist event
        payload = json.loads(body) if body else {}
        log = EventLog(
            trigger_id=trigger.id,
            event_payload=payload,
            status=EventLogStatus.PROCESSED,
            correlation_id=cid,
        )
        db.add(log)

        # Update trigger stats
        trigger.fire_count = (trigger.fire_count or 0) + 1
        trigger.last_fired_at = datetime.utcnow()
        db.commit()

        # Dispatch action asynchronously
        EventProcessorService._dispatch_action(trigger, payload, db)

        return {"status": "accepted", "correlation_id": cid, "log_id": log.id}

    # ── Threshold check (called from Celery beat) ─────────────────────────

    @staticmethod
    def check_thresholds(db: Session) -> Dict[str, Any]:
        """
        Evaluate all active threshold triggers against live Redis metrics.
        Returns a summary of fires and skips.
        """
        triggers = (
            db.query(EventTrigger)
            .filter(
                EventTrigger.trigger_type == TriggerType.THRESHOLD,
                EventTrigger.is_active == True,
            )
            .all()
        )
        r = _get_redis()
        results = {"checked": 0, "fired": 0, "skipped": 0}

        for trigger in triggers:
            results["checked"] += 1

            if _is_trigger_paused(trigger):
                results["skipped"] += 1
                continue

            cfg = trigger.config or {}
            metric_key = cfg.get("metric", "")
            operator = cfg.get("operator", "gt")
            threshold_value = cfg.get("value", 0)
            cooldown = cfg.get("cooldown_seconds", 60)

            # Cooldown check
            if trigger.last_fired_at:
                elapsed = (datetime.utcnow() - trigger.last_fired_at).total_seconds()
                if elapsed < cooldown:
                    results["skipped"] += 1
                    continue

            # Read metric from Redis
            raw = r.get(f"agentium:metrics:{metric_key}")
            if raw is None:
                results["skipped"] += 1
                continue

            try:
                current_value = float(raw)
            except (ValueError, TypeError):
                results["skipped"] += 1
                continue

            # Evaluate condition
            fired = False
            if operator == "gt" and current_value > float(threshold_value):
                fired = True
            elif operator == "lt" and current_value < float(threshold_value):
                fired = True
            elif operator == "eq" and current_value == float(threshold_value):
                fired = True
            elif operator == "gte" and current_value >= float(threshold_value):
                fired = True
            elif operator == "lte" and current_value <= float(threshold_value):
                fired = True

            if fired:
                if _check_rate_limit(trigger, db):
                    results["skipped"] += 1
                    continue

                payload = {
                    "metric": metric_key,
                    "operator": operator,
                    "threshold": threshold_value,
                    "current_value": current_value,
                    "fired_at": datetime.utcnow().isoformat(),
                }
                log = EventLog(
                    trigger_id=trigger.id,
                    event_payload=payload,
                    status=EventLogStatus.PROCESSED,
                    correlation_id=str(uuid.uuid4()),
                )
                db.add(log)
                trigger.fire_count = (trigger.fire_count or 0) + 1
                trigger.last_fired_at = datetime.utcnow()
                db.commit()

                EventProcessorService._dispatch_action(trigger, payload, db)
                results["fired"] += 1
            else:
                results["skipped"] += 1

        return results

    # ── External API polling (called from Celery beat) ────────────────────

    @staticmethod
    def poll_external_apis(db: Session) -> Dict[str, Any]:
        """
        Poll all active api_poll triggers.  Compute a hash of each
        response body and fire only when the hash changes.
        """
        import httpx

        triggers = (
            db.query(EventTrigger)
            .filter(
                EventTrigger.trigger_type == TriggerType.API_POLL,
                EventTrigger.is_active == True,
            )
            .all()
        )
        r = _get_redis()
        results = {"polled": 0, "fired": 0, "unchanged": 0, "errors": 0}

        for trigger in triggers:
            results["polled"] += 1

            if _is_trigger_paused(trigger):
                results["unchanged"] += 1
                continue

            cfg = trigger.config or {}
            url = cfg.get("url", "")
            headers = cfg.get("headers", {})

            if not url:
                results["errors"] += 1
                continue

            try:
                with httpx.Client(timeout=15) as client:
                    resp = client.get(url, headers=headers)
                    resp.raise_for_status()
                    body_hash = hashlib.sha256(resp.content).hexdigest()
            except Exception as exc:
                logger.warning("API poll failed for trigger %s: %s", trigger.name, exc)
                results["errors"] += 1
                continue

            # Compare hash
            hash_key = f"agentium:event:poll_hash:{trigger.id}"
            prev_hash = r.get(hash_key)

            if prev_hash == body_hash:
                results["unchanged"] += 1
                continue

            # Changed — store new hash and fire
            r.set(hash_key, body_hash)

            if _check_rate_limit(trigger, db):
                results["unchanged"] += 1
                continue

            payload = {
                "url": url,
                "previous_hash": prev_hash,
                "new_hash": body_hash,
                "polled_at": datetime.utcnow().isoformat(),
            }
            log = EventLog(
                trigger_id=trigger.id,
                event_payload=payload,
                status=EventLogStatus.PROCESSED,
                correlation_id=str(uuid.uuid4()),
            )
            db.add(log)
            trigger.fire_count = (trigger.fire_count or 0) + 1
            trigger.last_fired_at = datetime.utcnow()
            db.commit()

            EventProcessorService._dispatch_action(trigger, payload, db)
            results["fired"] += 1

        return results

    # ── Dead letter queue ─────────────────────────────────────────────────

    @staticmethod
    def get_dead_letters(
        db: Session, limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        logs = (
            db.query(EventLog)
            .filter(EventLog.status == EventLogStatus.DEAD_LETTER)
            .order_by(EventLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [log.to_dict() for log in logs]

    @staticmethod
    def retry_dead_letter(db: Session, log_id: str) -> Dict[str, Any]:
        """Re-process a dead-lettered event log entry."""
        log = db.query(EventLog).filter(EventLog.id == log_id).first()
        if not log:
            return {"status": "error", "detail": "Log not found"}
        if log.status != EventLogStatus.DEAD_LETTER:
            return {"status": "error", "detail": "Log is not in dead-letter state"}

        trigger = (
            db.query(EventTrigger)
            .filter(EventTrigger.id == log.trigger_id)
            .first()
        )
        if not trigger:
            return {"status": "error", "detail": "Trigger no longer exists"}

        try:
            EventProcessorService._dispatch_action(
                trigger, log.event_payload or {}, db
            )
            log.status = EventLogStatus.PROCESSED
            log.retry_count = (log.retry_count or 0) + 1
            db.commit()
            return {"status": "retried", "log_id": log_id}
        except Exception as exc:
            log.retry_count = (log.retry_count or 0) + 1
            log.error = str(exc)
            db.commit()
            logger.error("Dead-letter retry failed for %s: %s", log_id, exc)
            return {"status": "error", "detail": str(exc)}

    # ── Event correlation ─────────────────────────────────────────────────

    @staticmethod
    def correlate_events(db: Session, window_seconds: int = 60) -> Dict[str, Any]:
        """
        Group EventLog entries sharing a correlation_id prefix within
        a time window.  Deduplicate by marking extras as DUPLICATE.
        """
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        recent = (
            db.query(EventLog)
            .filter(
                EventLog.created_at >= cutoff,
                EventLog.status == EventLogStatus.PROCESSED,
                EventLog.correlation_id.isnot(None),
            )
            .order_by(EventLog.correlation_id, EventLog.created_at)
            .all()
        )

        groups: Dict[str, List[EventLog]] = {}
        for log in recent:
            # Group by first 8 chars of correlation_id (prefix)
            prefix = (log.correlation_id or "")[:8]
            groups.setdefault(prefix, []).append(log)

        consolidated = 0
        for prefix, logs in groups.items():
            if len(logs) <= 1:
                continue
            # Keep the first, mark rest as duplicate
            for extra in logs[1:]:
                extra.status = EventLogStatus.DUPLICATE
                consolidated += 1

        if consolidated:
            db.commit()

        return {"correlated_groups": len(groups), "duplicates_marked": consolidated}

    # ── Internal dispatch ─────────────────────────────────────────────────

    @staticmethod
    def _dispatch_action(
        trigger: EventTrigger, payload: Dict[str, Any], db: Session,
    ) -> None:
        """
        Execute the configured action for a trigger: start a workflow,
        create a task, or emit a WebSocket notification.
        """
        try:
            if trigger.target_workflow_id:
                from backend.services.workflow_engine import WorkflowEngine
                try:
                    WorkflowEngine.trigger_execution(
                        db,
                        trigger.target_workflow_id,
                        trigger=f"event:{trigger.trigger_type.value}",
                        context=payload,
                    )
                    logger.info(
                        "Event trigger %s dispatched workflow %s",
                        trigger.name, trigger.target_workflow_id,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to dispatch workflow for trigger %s: %s",
                        trigger.name, exc,
                    )

            # WebSocket broadcast regardless
            try:
                from backend.api.routes.websocket import manager
                import asyncio

                async def _broadcast():
                    await manager.broadcast(json.dumps({
                        "type": "event_trigger_fired",
                        "trigger_id": trigger.id,
                        "trigger_name": trigger.name,
                        "trigger_type": trigger.trigger_type.value,
                        "payload": payload,
                        "fired_at": datetime.utcnow().isoformat(),
                    }))

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_broadcast())
                except RuntimeError:
                    pass  # No event loop — skip WS broadcast in Celery
            except Exception:
                pass  # WS broadcast is best-effort
        except Exception as exc:
            logger.error("Dispatch action failed for trigger %s: %s", trigger.name, exc)
