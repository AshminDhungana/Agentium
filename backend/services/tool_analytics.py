"""
Tool Analytics Service
Records every tool invocation in ToolUsageLog and surfaces
aggregated stats: call counts, error rates, p50/p95 latency,
top callers, usage over time.

Usage:
    analytics = ToolAnalyticsService(db)

    # Wrap a tool call:
    with analytics.record(tool_name, called_by, task_id, version) as ctx:
        result = tool.execute(**kwargs)
        ctx.set_output_size(len(str(result)))

    # Query:
    stats = analytics.get_tool_stats("my_tool")
    report = analytics.get_full_report()
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from contextlib import contextmanager
import hashlib
import json
import time

from backend.models.entities.tool_usage_log import ToolUsageLog


class _RecordingContext:
    """Context object passed into the `with analytics.record(...)` block."""

    def __init__(self):
        """Init."""

        self.success: bool = True
        self.error_message: Optional[str] = None
        self.output_size_bytes: Optional[int] = None

    def set_error(self, msg: str):
        """Set error."""

        self.success = False
        self.error_message = msg

    def set_output_size(self, size: int):
        """Set output size."""

        self.output_size_bytes = size


class ToolAnalyticsService:
    """
    Writes and reads ToolUsageLog rows.
    Designed to wrap tool calls with minimal overhead.
    """

    def __init__(self, db: Session):
        """Init."""

        self.db = db

    # ──────────────────────────────────────────────────────────────
    # RECORDING
    # ──────────────────────────────────────────────────────────────

    @contextmanager
    def record(
        self,
        tool_name: str,
        called_by: str,
        task_id: Optional[str] = None,
        tool_version: int = 1,
        input_kwargs: Optional[dict] = None,
    ):
        """
        Context manager to wrap a tool call and auto-record the result.

        Example:
            with analytics.record("my_tool", "20001", task_id="abc") as ctx:
                result = tool.execute(x=1)
                ctx.set_output_size(len(str(result)))
        """
        ctx = _RecordingContext()
        start = time.perf_counter()

        try:
            yield ctx
        except Exception as e:
            ctx.set_error(str(e))
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            input_hash = self._hash_input(input_kwargs) if input_kwargs else None
            self._write_log(
                tool_name=tool_name,
                tool_version=tool_version,
                called_by=called_by,
                task_id=task_id,
                success=ctx.success,
                error_message=ctx.error_message,
                latency_ms=latency_ms,
                input_hash=input_hash,
                output_size_bytes=ctx.output_size_bytes,
            )

    def log_call(
        self,
        tool_name: str,
        called_by: str,
        success: bool,
        latency_ms: float,
        task_id: Optional[str] = None,
        tool_version: int = 1,
        error_message: Optional[str] = None,
        input_kwargs: Optional[dict] = None,
        output_size_bytes: Optional[int] = None,
    ) -> None:
        """Direct log write (use when you can't use the context manager)."""
        self._write_log(
            tool_name=tool_name,
            tool_version=tool_version,
            called_by=called_by,
            task_id=task_id,
            success=success,
            error_message=error_message,
            latency_ms=latency_ms,
            input_hash=self._hash_input(input_kwargs) if input_kwargs else None,
            output_size_bytes=output_size_bytes,
        )

    # ──────────────────────────────────────────────────────────────
    # STATS — single tool
    # ──────────────────────────────────────────────────────────────

    def get_tool_stats(
        self,
        tool_name: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Return aggregated stats for a single tool over the last N days.
        """
        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            self.db.query(ToolUsageLog)
            .filter(
                ToolUsageLog.tool_name == tool_name,
                ToolUsageLog.invoked_at >= since,
            )
            .all()
        )

        if not rows:
            return {"tool_name": tool_name, "period_days": days, "total_calls": 0}

        latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
        errors = [r for r in rows if not r.success]

        return {
            "tool_name": tool_name,
            "period_days": days,
            "total_calls": len(rows),
            "successful_calls": len(rows) - len(errors),
            "failed_calls": len(errors),
            "error_rate_pct": round(len(errors) / len(rows) * 100, 2),
            "latency": self._latency_stats(latencies),
            "top_callers": self._top_callers(rows),
            "errors_breakdown": self._errors_breakdown(errors),
            "daily_breakdown": self._daily_breakdown(rows, days),
        }

    # ──────────────────────────────────────────────────────────────
    # STATS — all tools
    # ──────────────────────────────────────────────────────────────

    def get_full_report(self, days: int = 30) -> Dict[str, Any]:
        """
        Summary report across all tools.
        """
        since = datetime.utcnow() - timedelta(days=days)

        tool_totals = (
            self.db.query(
                ToolUsageLog.tool_name,
                func.count(ToolUsageLog.id).label("total"),
                func.sum(
                    func.cast(ToolUsageLog.success == False, func.Integer)
                ).label("errors"),
                func.avg(ToolUsageLog.latency_ms).label("avg_latency"),
            )
            .filter(ToolUsageLog.invoked_at >= since)
            .group_by(ToolUsageLog.tool_name)
            .order_by(desc("total"))
            .all()
        )

        tools_summary = [
            {
                "tool_name": row.tool_name,
                "total_calls": row.total,
                "failed_calls": int(row.errors or 0),
                "error_rate_pct": round((row.errors or 0) / row.total * 100, 2),
                "avg_latency_ms": round(row.avg_latency or 0, 2),
            }
            for row in tool_totals
        ]

        total_calls = sum(t["total_calls"] for t in tools_summary)
        total_errors = sum(t["failed_calls"] for t in tools_summary)

        return {
            "period_days": days,
            "total_tools_used": len(tools_summary),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "overall_error_rate_pct": round(total_errors / total_calls * 100, 2) if total_calls else 0,
            "tools": tools_summary,
        }

    # ──────────────────────────────────────────────────────────────
    # STATS — per-agent
    # ──────────────────────────────────────────────────────────────

    def get_agent_tool_usage(
        self,
        agentium_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """What tools has a specific agent been calling?"""
        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            self.db.query(ToolUsageLog)
            .filter(
                ToolUsageLog.called_by_agentium_id == agentium_id,
                ToolUsageLog.invoked_at >= since,
            )
            .all()
        )

        by_tool: Dict[str, list] = {}
        for r in rows:
            by_tool.setdefault(r.tool_name, []).append(r)

        return {
            "agentium_id": agentium_id,
            "period_days": days,
            "total_calls": len(rows),
            "tools_used": [
                {
                    "tool_name": name,
                    "calls": len(calls),
                    "errors": sum(1 for c in calls if not c.success),
                    "avg_latency_ms": round(
                        sum(c.latency_ms for c in calls if c.latency_ms) / len(calls), 2
                    ) if calls else 0,
                }
                for name, calls in by_tool.items()
            ],
        }

    # ──────────────────────────────────────────────────────────────
    # RECENT ERRORS
    # ──────────────────────────────────────────────────────────────

    def get_recent_errors(
        self,
        tool_name: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return the most recent failed calls."""
        q = self.db.query(ToolUsageLog).filter(ToolUsageLog.success == False)
        if tool_name:
            q = q.filter(ToolUsageLog.tool_name == tool_name)
        rows = q.order_by(ToolUsageLog.invoked_at.desc()).limit(limit).all()

        return {
            "tool_name": tool_name or "all",
            "errors": [r.to_dict() for r in rows],
        }

    # ──────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ──────────────────────────────────────────────────────────────

    def _write_log(self, **kwargs):
        """Write log."""

        log = ToolUsageLog(**kwargs, invoked_at=datetime.utcnow())
        self.db.add(log)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()  # Never let analytics writes break the main flow

    def _hash_input(self, kwargs: dict) -> str:
        """Hash input."""

        try:
            serialized = json.dumps(kwargs, sort_keys=True, default=str)
            return hashlib.sha256(serialized.encode()).hexdigest()
        except Exception:
            return "hash_error"

    def _latency_stats(self, latencies: List[float]) -> Dict[str, Any]:
        """Latency stats."""

        if not latencies:
            return {}
        sorted_l = sorted(latencies)
        n = len(sorted_l)
        return {
            "min_ms": round(sorted_l[0], 2),
            "max_ms": round(sorted_l[-1], 2),
            "avg_ms": round(sum(sorted_l) / n, 2),
            "p50_ms": round(sorted_l[int(n * 0.50)], 2),
            "p95_ms": round(sorted_l[int(n * 0.95)], 2),
            "p99_ms": round(sorted_l[int(n * 0.99)], 2),
        }

    def _top_callers(self, rows: List[ToolUsageLog], top_n: int = 5) -> List[Dict]:
        """Top callers."""

        counts: Dict[str, int] = {}
        for r in rows:
            counts[r.called_by_agentium_id] = counts.get(r.called_by_agentium_id, 0) + 1
        return [
            {"agentium_id": k, "calls": v}
            for k, v in sorted(counts.items(), key=lambda x: -x[1])[:top_n]
        ]

    def _errors_breakdown(self, errors: List[ToolUsageLog]) -> Dict[str, int]:
        """Errors breakdown."""

        breakdown: Dict[str, int] = {}
        for e in errors:
            key = (e.error_message or "unknown")[:80]
            breakdown[key] = breakdown.get(key, 0) + 1
        return breakdown

    def _daily_breakdown(
        self, rows: List[ToolUsageLog], days: int
    ) -> List[Dict[str, Any]]:
        """Calls per day for the last N days."""
        daily: Dict[str, int] = {}
        for r in rows:
            day = r.invoked_at.strftime("%Y-%m-%d")
            daily[day] = daily.get(day, 0) + 1

        # Fill in missing days with 0
        result = []
        for i in range(days - 1, -1, -1):
            day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            result.append({"date": day, "calls": daily.get(day, 0)})
        return result