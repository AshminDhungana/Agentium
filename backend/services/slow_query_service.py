"""
slow_query_service.py — pg_stat_statements query analytics.

Encapsulates every read/reset operation against pg_stat_statements so both
the admin API route and the Celery audit task share a single implementation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

_SUPPORTED_WARNING_LOGGED = False


@dataclass
class SlowQuery:
    """One row from pg_stat_statements, normalised for the API."""
    query_hash: str
    query_preview: str
    call_count: int
    avg_duration_ms: float
    total_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    rows_per_call: float
    last_seen: Optional[str]


def _extension_available(db: Session) -> bool:
    """Return True if pg_stat_statements is installed in this database."""
    global _SUPPORTED_WARNING_LOGGED
    try:
        result = db.execute(
            text(
                "SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'"
            )
        ).fetchone()
        return result is not None
    except Exception as exc:
        if not _SUPPORTED_WARNING_LOGGED:
            logger.warning(
                "[SlowQueryService] Could not probe pg_extension: %s. "
                "Slow-query data will be unavailable.",
                exc,
            )
            _SUPPORTED_WARNING_LOGGED = True
        return False


def _has_stats_info_column(db: Session) -> bool:
    """
    pg_stat_statements.stats_since was added in PG 14.
    Older versions have no per-statement timestamp.
    """
    try:
        db.execute(
            text("SELECT stats_since FROM pg_stat_statements LIMIT 0")
        )
        return True
    except Exception:
        return False


def get_slow_queries(
    db: Session,
    limit: int = 20,
    min_avg_ms: float = 500.0,
) -> list[SlowQuery]:
    """
    Return the top-N slowest queries (by mean execution time) from
    pg_stat_statements, filtering out internal housekeeping statements.

    Args:
        db:         Active SQLAlchemy session.
        limit:      Maximum rows to return (default 20).
        min_avg_ms: Only include queries whose mean duration ≥ this value (ms).

    Returns:
        Sorted list of SlowQuery objects (slowest first).
    """
    if not _extension_available(db):
        return []

    has_ts = _has_stats_info_column(db)
    ts_col = "stats_since::text" if has_ts else "NULL"

    sql = text(f"""
        SELECT
            queryid::text                              AS query_hash,
            LEFT(query, 200)                           AS query_preview,
            calls                                      AS call_count,
            (mean_exec_time)::numeric(12,3)            AS avg_duration_ms,
            (total_exec_time)::numeric(16,3)           AS total_duration_ms,
            (min_exec_time)::numeric(12,3)             AS min_duration_ms,
            (max_exec_time)::numeric(12,3)             AS max_duration_ms,
            CASE WHEN calls > 0
                 THEN (rows::float / calls)
                 ELSE 0
            END                                        AS rows_per_call,
            {ts_col}                                   AS last_seen
        FROM  pg_stat_statements
        WHERE mean_exec_time >= :min_ms
          AND query NOT ILIKE '%pg_stat_statements%'
          AND query NOT ILIKE '%pg_catalog%'
          AND query NOT ILIKE '%information_schema%'
        ORDER BY mean_exec_time DESC
        LIMIT :lim
    """)

    try:
        rows = db.execute(sql, {"min_ms": min_avg_ms, "lim": limit}).fetchall()
        return [
            SlowQuery(
                query_hash=str(r.query_hash),
                query_preview=str(r.query_preview),
                call_count=int(r.call_count),
                avg_duration_ms=float(r.avg_duration_ms),
                total_duration_ms=float(r.total_duration_ms),
                min_duration_ms=float(r.min_duration_ms),
                max_duration_ms=float(r.max_duration_ms),
                rows_per_call=float(r.rows_per_call),
                last_seen=str(r.last_seen) if r.last_seen else None,
            )
            for r in rows
        ]
    except Exception as exc:
        logger.warning("[SlowQueryService] get_slow_queries failed: %s", exc)
        return []


def reset_stats(db: Session) -> bool:
    """
    Reset pg_stat_statements counters (admin only).
    Returns True on success, False if the extension is unavailable.
    """
    if not _extension_available(db):
        return False
    try:
        db.execute(text("SELECT pg_stat_statements_reset()"))
        db.commit()
        logger.info("[SlowQueryService] pg_stat_statements reset.")
        return True
    except Exception as exc:
        logger.warning("[SlowQueryService] reset_stats failed: %s", exc)
        return False


def get_summary(db: Session) -> dict:
    """
    Return a lightweight summary dict (total statements tracked, total
    execution time, extension availability).  Used by the health endpoint.
    """
    if not _extension_available(db):
        return {
            "available": False,
            "reason": "pg_stat_statements extension not installed",
        }
    try:
        row = db.execute(
            text(
                "SELECT COUNT(*) AS stmt_count, "
                "       COALESCE(SUM(total_exec_time), 0)::numeric(16,3) AS total_ms "
                "FROM pg_stat_statements "
                "WHERE query NOT ILIKE '%pg_stat_statements%'"
            )
        ).fetchone()
        return {
            "available": True,
            "statement_count": int(row.stmt_count),
            "total_execution_ms": float(row.total_ms),
        }
    except Exception as exc:
        logger.warning("[SlowQueryService] get_summary failed: %s", exc)
        return {"available": False, "reason": str(exc)}