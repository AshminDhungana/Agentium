"""Single source of cron-math for the scheduled-task sweeps.

Both the ScheduledTask dispatcher and the EventTrigger SCHEDULE evaluator
call these so their notion of "is this cron due" cannot drift.
"""
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Timezone-aware current UTC time — the single clock for all sweeps."""
    return datetime.now(timezone.utc)


def as_aware(dt: Optional[datetime], tz: str = "UTC") -> Optional[datetime]:
    """Attach a timezone to a naive datetime; pass aware values through unchanged."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def next_run(cron_expression: str, timezone: str = "UTC", base: Optional[datetime] = None) -> Optional[datetime]:
    """Next cron schedule strictly after `base` (default: now), in the given tz.

    Returns None when the expression is empty or exhausted.
    """
    if not cron_expression:
        return None
    try:
        from croniter import croniter
    except ImportError:
        return None
    tz = ZoneInfo(timezone or "UTC")
    base_aware = as_aware(base, timezone) or utc_now()
    base_aware = base_aware.astimezone(tz)
    try:
        return croniter(cron_expression, base_aware).get_next(datetime)
    except Exception:
        return None


def is_due(cron_expression: str, timezone: str = "UTC", last_run: Optional[datetime] = None) -> bool:
    """True when the next cron time after last_run falls at or before now."""
    nxt = next_run(cron_expression, timezone=timezone, base=last_run)
    if nxt is None:
        return False
    return nxt <= utc_now()