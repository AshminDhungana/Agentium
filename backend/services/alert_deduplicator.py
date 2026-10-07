# backend/services/alert_deduplicator.py
"""
Alert Deduplicator - Prevents notification storms by suppressing
repeated identical alerts within a configurable time window.

Uses Redis sorted sets with TTL for distributed deduplication state.
Fail-open: if Redis unavailable, alerts are never suppressed.
"""
import time
from typing import Optional, Dict
from backend.models.entities.monitoring import ViolationSeverity
from backend.services.structured_logging import get_structured_logger
from backend.core.config import settings

logger = get_structured_logger(__name__)


class AlertDeduplicator:
    """
    Redis-backed alert deduplication with TTL-based windows.

    Key format: alert_dedup:{alert_type}:{affected_agent_id_or_system}:{severity}
    Window: configurable per alert_type, default 300 seconds (5 minutes)
    """

    def __init__(self):
        """Initialize deduplicator with Redis client."""
        from backend.services.channel_manager import get_redis_client
        self._redis = get_redis_client()
        self._default_window = getattr(settings, 'ALERT_DEDUP_WINDOW_SECONDS', 300)
        self._windows = getattr(settings, 'ALERT_DEDUP_WINDOWS', {})

    def _make_key(self, alert_type: str, affected_agent_id: Optional[str], severity: ViolationSeverity) -> str:
        """Generate Redis key for deduplication."""
        agent_part = affected_agent_id or "system"
        severity_part = severity.value if hasattr(severity, 'value') else str(severity)
        return f"alert_dedup:{alert_type}:{agent_part}:{severity_part}"

    def get_window_seconds(self, alert_type: str) -> int:
        """Get deduplication window for alert type."""
        return self._windows.get(alert_type, self._default_window)

    async def should_suppress(
        self,
        alert_type: str,
        affected_agent_id: Optional[str],
        severity: ViolationSeverity
    ) -> bool:
        """
        Check if alert should be suppressed (duplicate within window).

        Returns True to suppress, False to allow through.
        Fail-open: any Redis error returns False.
        """
        if not self._redis:
            return False  # Fail open - no Redis, no deduplication

        key = self._make_key(alert_type, affected_agent_id, severity)
        window = self.get_window_seconds(alert_type)
        now = time.time()
        cutoff = now - window

        try:
            # Remove expired entries
            await self._redis.zremrangebyscore(key, 0, cutoff)

            # Count current entries in window
            count = await self._redis.zcard(key)

            if count > 0:
                logger.info(
                    "Alert suppressed by deduplication",
                    alert_type=alert_type,
                    affected_agent_id=affected_agent_id,
                    severity=severity.value if hasattr(severity, 'value') else str(severity),
                    window_seconds=window,
                    existing_count=count
                )
                return True

            return False

        except Exception as e:
            logger.warning(
                "Deduplication check failed, failing open",
                alert_type=alert_type,
                error=str(e)
            )
            return False  # Fail open

    async def record_alert(
        self,
        alert_type: str,
        affected_agent_id: Optional[str],
        severity: ViolationSeverity
    ) -> None:
        """
        Record alert in deduplication store.

        Adds current timestamp to sorted set and sets TTL.
        Fail-open: Redis errors are logged but don't raise.
        """
        if not self._redis:
            return  # Fail open

        key = self._make_key(alert_type, affected_agent_id, severity)
        window = self.get_window_seconds(alert_type)
        now = time.time()

        try:
            # Add current timestamp as score and member
            await self._redis.zadd(key, {str(now): now})
            # Set TTL to window + buffer
            await self._redis.expire(key, window + 60)
        except Exception as e:
            logger.warning(
                "Failed to record alert for deduplication",
                alert_type=alert_type,
                error=str(e)
            )


# Global instance
_alert_deduplicator = None

def get_alert_deduplicator() -> AlertDeduplicator:
    """Get singleton AlertDeduplicator instance."""
    global _alert_deduplicator
    if _alert_deduplicator is None:
        _alert_deduplicator = AlertDeduplicator()
    return _alert_deduplicator