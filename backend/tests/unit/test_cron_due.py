# backend/tests/unit/test_cron_due.py
from datetime import datetime, timezone, timedelta
import pytest

from backend.services.scheduling.cron_due import utc_now, as_aware, next_run, is_due


def test_utc_now_is_timezone_aware():
    assert utc_now().tzinfo is not None


def test_as_aware_attaches_utc_to_naive():
    naive = datetime(2026, 9, 17, 12, 0)
    aware = as_aware(naive, "UTC")
    assert aware.utcoffset() == timedelta(0)


def test_as_aware_passes_aware_through():
    aware = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert as_aware(aware) == aware


def test_next_run_is_strictly_after_base():
    base = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)
    # "0 9 * * *" = daily at 09:00; next run is tomorrow 09:00
    nxt = next_run("0 9 * * *", base=base)
    assert nxt > base
    assert nxt.hour == 9


def test_next_run_respects_timezone():
    base = datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)
    nxt = next_run("0 9 * * *", timezone="UTC", base=base)
    assert nxt.tzinfo is not None
    assert nxt.utcoffset() == timedelta(0)
    assert nxt.hour == 9


def test_next_run_returns_none_for_empty_expression():
    assert next_run("", base=utc_now()) is None


def test_is_due_fires_when_scheduled_time_reached():
    past = utc_now() - timedelta(hours=1)
    # A "every minute" cron whose last run was an hour ago is certainly due.
    assert is_due("* * * * *", last_run=past)


def test_is_due_not_fired_when_not_time_yet():
    far_future = utc_now() + timedelta(days=30)
    # Next run after far_future is > now, so not due.
    assert not is_due("* * * * *", last_run=far_future)