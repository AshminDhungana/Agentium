"""
Tool Deprecation Service
Handles the full deprecation lifecycle:
  active → deprecated (soft-disable, still callable with warning)
         → sunset scheduled (countdown to hard removal)
         → sunset executed (removed from registry + disk cleanup)

Rules:
  - Only Head (0xxxx) or Council (1xxxx) can deprecate
  - Deprecated tools remain callable but emit warnings in analytics
  - Sunset date required for hard removal (minimum 7 days notice)
  - Replacement tool can be specified to auto-redirect callers
"""
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from backend.models.entities.tool_staging import ToolStaging
from backend.models.entities.tool_usage_log import ToolUsageLog
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.core.tool_registry import tool_registry


MINIMUM_SUNSET_DAYS = 7  # At least 7 days warning before hard removal


class ToolDeprecationService:
    """
    Manages soft-disable, sunset scheduling, and cleanup of tools.
    """

    def __init__(self, db: Session):
        """Init."""

        self.db = db

    # ──────────────────────────────────────────────────────────────
    # DEPRECATE (soft disable)
    # ──────────────────────────────────────────────────────────────

    def deprecate_tool(
        self,
        tool_name: str,
        deprecated_by: str,
        reason: str,
        replacement_tool_name: Optional[str] = None,
        sunset_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Soft-deprecate a tool.
        - Tool remains in registry but marked deprecated
        - All future calls are logged with a deprecation warning
        - Optional: schedule sunset (hard removal) after N days
        """
        if not (deprecated_by.startswith("0") or deprecated_by.startswith("1")):
            return {"deprecated": False, "error": "Only Head or Council can deprecate tools"}

        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name,
            ToolStaging.status == "activated",
        ).first()

        if not staging:
            return {"deprecated": False, "error": f"No active tool named '{tool_name}'"}

        # Validate replacement exists if specified
        if replacement_tool_name:
            replacement = self.db.query(ToolStaging).filter(
                ToolStaging.tool_name == replacement_tool_name,
                ToolStaging.status == "activated",
            ).first()
            if not replacement:
                return {
                    "deprecated": False,
                    "error": f"Replacement tool '{replacement_tool_name}' not found or not active",
                }

        # Calculate sunset date if requested
        sunset_at = None
        if sunset_days is not None:
            if sunset_days < MINIMUM_SUNSET_DAYS:
                return {
                    "deprecated": False,
                    "error": f"Minimum sunset period is {MINIMUM_SUNSET_DAYS} days",
                }
            sunset_at = datetime.utcnow() + timedelta(days=sunset_days)

        # Update staging record
        staging.status = "deprecated"
        staging.deprecated_at = datetime.utcnow()
        staging.deprecated_by_agentium_id = deprecated_by
        staging.deprecation_reason = reason
        staging.replacement_tool_name = replacement_tool_name
        staging.sunset_at = sunset_at

        # Mark tool in registry as deprecated (non-breaking — still callable)
        tool_registry.mark_deprecated(tool_name, reason, replacement_tool_name)

        self.db.commit()

        self._audit(
            "tool_deprecated",
            tool_name,
            deprecated_by,
            {
                "reason": reason,
                "replacement": replacement_tool_name,
                "sunset_at": sunset_at.isoformat() if sunset_at else None,
            },
        )

        return {
            "deprecated": True,
            "tool_name": tool_name,
            "deprecated_by": deprecated_by,
            "reason": reason,
            "replacement_tool_name": replacement_tool_name,
            "sunset_at": sunset_at.isoformat() if sunset_at else None,
            "note": "Tool is still callable but marked deprecated. Use sunset to hard-remove.",
        }

    # ──────────────────────────────────────────────────────────────
    # SCHEDULE SUNSET
    # ──────────────────────────────────────────────────────────────

    def schedule_sunset(
        self,
        tool_name: str,
        requested_by: str,
        sunset_days: int,
    ) -> Dict[str, Any]:
        """
        Schedule a sunset date for a deprecated (or active) tool.
        After sunset_at, the tool will be hard-removed on next cleanup run.
        """
        if not (requested_by.startswith("0") or requested_by.startswith("1")):
            return {"scheduled": False, "error": "Only Head or Council can schedule sunsets"}

        if sunset_days < MINIMUM_SUNSET_DAYS:
            return {
                "scheduled": False,
                "error": f"Minimum sunset period is {MINIMUM_SUNSET_DAYS} days",
            }

        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name,
            ToolStaging.status.in_(["activated", "deprecated"]),
        ).first()

        if not staging:
            return {"scheduled": False, "error": f"Tool '{tool_name}' not found or already sunset"}

        sunset_at = datetime.utcnow() + timedelta(days=sunset_days)
        staging.sunset_at = sunset_at

        self.db.commit()

        return {
            "scheduled": True,
            "tool_name": tool_name,
            "sunset_at": sunset_at.isoformat(),
            "days_until_removal": sunset_days,
        }

    # ──────────────────────────────────────────────────────────────
    # EXECUTE SUNSET (hard removal)
    # ──────────────────────────────────────────────────────────────

    def execute_sunset(
        self,
        tool_name: str,
        forced_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Hard-remove a tool that has passed its sunset date.
        - Removes from tool registry
        - Deletes generated file from disk
        - Marks staging record as 'sunset'
        Can be forced early by Head (0xxxx) only.
        """
        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name,
        ).first()

        if not staging:
            return {"executed": False, "error": f"Tool '{tool_name}' not found"}

        if staging.status == "sunset":
            return {"executed": False, "error": "Tool already sunset"}

        # Check sunset date unless forced by Head
        if forced_by and not forced_by.startswith("0"):
            return {"executed": False, "error": "Only Head can force an early sunset"}

        if not forced_by:
            if not staging.sunset_at:
                return {"executed": False, "error": "No sunset date scheduled. Use schedule_sunset first."}
            if datetime.utcnow() < staging.sunset_at:
                remaining = (staging.sunset_at - datetime.utcnow()).days
                return {
                    "executed": False,
                    "error": f"Sunset date not reached. {remaining} days remaining.",
                    "sunset_at": staging.sunset_at.isoformat(),
                }

        # Remove from registry
        tool_registry.deregister_tool(tool_name)

        # Delete file from disk
        from pathlib import Path
        tool_path = Path(staging.tool_path)
        if tool_path.exists():
            tool_path.unlink()
            deleted_file = True
        else:
            deleted_file = False

        # Update record
        staging.status = "sunset"

        self.db.commit()

        self._audit(
            "tool_sunset",
            tool_name,
            forced_by or "scheduler",
            {
                "forced": forced_by is not None,
                "file_deleted": deleted_file,
            },
        )

        return {
            "executed": True,
            "tool_name": tool_name,
            "file_deleted": deleted_file,
            "forced_by": forced_by,
        }

    # ──────────────────────────────────────────────────────────────
    # RESTORE (undo deprecation)
    # ──────────────────────────────────────────────────────────────

    def restore_tool(
        self,
        tool_name: str,
        restored_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Restore a deprecated tool back to active status.
        Cannot restore sunset (hard-removed) tools.
        """
        if not (restored_by.startswith("0") or restored_by.startswith("1")):
            return {"restored": False, "error": "Only Head or Council can restore tools"}

        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name,
            ToolStaging.status == "deprecated",
        ).first()

        if not staging:
            return {
                "restored": False,
                "error": f"Tool '{tool_name}' not found or not in deprecated state",
            }

        staging.status = "activated"
        staging.deprecated_at = None
        staging.deprecated_by_agentium_id = None
        staging.deprecation_reason = None
        staging.sunset_at = None

        tool_registry.unmark_deprecated(tool_name)

        self.db.commit()

        self._audit("tool_restored", tool_name, restored_by, {"reason": reason})

        return {
            "restored": True,
            "tool_name": tool_name,
            "restored_by": restored_by,
            "reason": reason,
        }

    # ──────────────────────────────────────────────────────────────
    # BATCH CLEANUP (called by scheduler)
    # ──────────────────────────────────────────────────────────────

    def run_sunset_cleanup(self) -> Dict[str, Any]:
        """
        Called by a background scheduler (e.g. Celery beat).
        Executes sunset on all tools whose sunset_at has passed.
        """
        now = datetime.utcnow()
        due = self.db.query(ToolStaging).filter(
            ToolStaging.sunset_at <= now,
            ToolStaging.status.in_(["deprecated", "activated"]),
        ).all()

        results = []
        for staging in due:
            result = self.execute_sunset(staging.tool_name)
            results.append({"tool_name": staging.tool_name, "result": result})

        return {
            "tools_sunset": len(results),
            "results": results,
            "run_at": now.isoformat(),
        }

    # ──────────────────────────────────────────────────────────────
    # LIST DEPRECATED
    # ──────────────────────────────────────────────────────────────

    def list_deprecated_tools(self) -> Dict[str, Any]:
        """Return all deprecated and sunset tools with their metadata."""
        tools = self.db.query(ToolStaging).filter(
            ToolStaging.status.in_(["deprecated", "sunset"]),
        ).all()

        return {
            "total": len(tools),
            "tools": [t.to_dict() for t in tools],
        }

    # ──────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────

    def _audit(self, action: str, tool_name: str, actor: str, details: dict):
        """Audit."""

        audit = AuditLog(
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            actor_type="agent",
            actor_id=actor,
            action=action,
            target_type="tool",
            target_id=tool_name,
            description=f"{action} on tool '{tool_name}'",
            after_state=details,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        self.db.add(audit)
        self.db.commit()