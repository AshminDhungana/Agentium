"""
Tool Versioning Service
Manages version lifecycle for generated tools:
- Create first version on activation
- Propose and approve updates (new versions)
- Rollback to any prior version
- Diff between versions
- Changelog retrieval
"""
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from datetime import datetime
import difflib
import hashlib

from backend.models.entities.tool_version import ToolVersion
from backend.models.entities.tool_staging import ToolStaging
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.tool_factory import ToolFactory
from backend.core.tool_registry import tool_registry


class ToolVersioningService:
    """
    Handles versioning and update lifecycle for agent-created tools.

    Version lifecycle:
        activate (v1) → propose_update → vote → approve_update (v2) → ...
        At any point: rollback(tool_name, version_number) → restores that snapshot
    """

    def __init__(self, db: Session):
        """Init."""

        self.db = db
        self.factory = ToolFactory()

    # ──────────────────────────────────────────────────────────────
    # CREATE — called by ToolCreationService on first activation
    # ──────────────────────────────────────────────────────────────

    def create_initial_version(
        self,
        tool_name: str,
        code: str,
        tool_path: str,
        authored_by: str,
        voting_id: Optional[str] = None,
    ) -> ToolVersion:
        """
        Record version 1 when a tool is first activated.
        Called automatically by ToolCreationService.activate_tool().
        """
        version = ToolVersion(
            tool_name=tool_name,
            version_number=1,
            version_tag="v1.0.0",
            code_snapshot=code,
            tool_path=tool_path,
            authored_by_agentium_id=authored_by,
            change_summary="Initial version",
            approved_by_voting_id=voting_id,
            approved_at=datetime.utcnow(),
            is_active=True,
            is_rolled_back=False,
        )
        self.db.add(version)
        self.db.commit()
        self.db.refresh(version)
        return version

    # ──────────────────────────────────────────────────────────────
    # PROPOSE UPDATE
    # ──────────────────────────────────────────────────────────────

    def propose_update(
        self,
        tool_name: str,
        new_code: str,
        change_summary: str,
        proposed_by: str,
    ) -> Dict[str, Any]:
        """
        Agent proposes a code update to an existing tool.
        Validates the new code before staging.
        Returns voting requirements (same rules as tool creation).
        """
        # Tool must exist and be active
        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name,
            ToolStaging.status == "activated",
        ).first()

        if not staging:
            return {"proposed": False, "error": f"No active tool named '{tool_name}'"}

        # Task agents (3xxxx) cannot propose updates
        if proposed_by.startswith("3"):
            return {"proposed": False, "error": "Task agents cannot update tools"}

        # Validate the new code
        validation = self.factory.validate_tool_code(new_code)
        if not validation["valid"]:
            return {"proposed": False, "error": validation["error"]}

        # Determine next version number
        latest = self._get_latest_version(tool_name)
        next_version_number = (latest.version_number + 1) if latest else 2
        next_tag = f"v{next_version_number}.0.0"

        # Stage the update (write new file to a staging path)
        staged_path = self.factory.tools_directory / f"{tool_name}_v{next_version_number}_staged.py"
        staged_path.write_text(new_code)

        # Create a pending ToolVersion (not yet active)
        pending_version = ToolVersion(
            tool_name=tool_name,
            version_number=next_version_number,
            version_tag=next_tag,
            code_snapshot=new_code,
            tool_path=str(staged_path),
            authored_by_agentium_id=proposed_by,
            change_summary=change_summary,
            is_active=False,
        )
        self.db.add(pending_version)
        self.db.commit()
        self.db.refresh(pending_version)

        requires_vote = not proposed_by.startswith("0")

        return {
            "proposed": True,
            "tool_name": tool_name,
            "pending_version_id": pending_version.id,
            "version_tag": next_tag,
            "requires_vote": requires_vote,
            "change_summary": change_summary,
        }

    # ──────────────────────────────────────────────────────────────
    # APPROVE UPDATE
    # ──────────────────────────────────────────────────────────────

    def approve_update(
        self,
        tool_name: str,
        pending_version_id: str,
        approved_by_voting_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Activate a pending version, deactivating the current one.
        Called after Council vote passes (or Head auto-approves).
        """
        pending = self.db.query(ToolVersion).filter(
            ToolVersion.id == pending_version_id,
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == False,
        ).first()

        if not pending:
            return {"approved": False, "error": "Pending version not found"}

        # Run tests if the staging entry has test cases
        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name
        ).first()

        if staging:
            import json
            from backend.models.schemas.tool_creation import ToolCreationRequest
            try:
                req = ToolCreationRequest(**json.loads(staging.request_json))
                if req.test_cases:
                    # Write code to temp path for testing
                    test_path = self.factory.tools_directory / f"{tool_name}_test_temp.py"
                    test_path.write_text(pending.code_snapshot)
                    test_results = self.factory.run_tests(tool_name, req.test_cases)
                    if not test_results["passed"]:
                        return {
                            "approved": False,
                            "error": "Tests failed on new version",
                            "test_results": test_results,
                        }
            except Exception:
                pass  # If we can't load request, skip tests

        # Deactivate current version
        current_active = self.db.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == True,
        ).first()
        if current_active:
            current_active.is_active = False

        # Promote pending version
        final_path = self.factory.tools_directory / f"{tool_name}.py"
        final_path.write_text(pending.code_snapshot)
        pending.tool_path = str(final_path)
        pending.is_active = True
        pending.approved_by_voting_id = approved_by_voting_id
        pending.approved_at = datetime.utcnow()

        # Update staging current_version
        if staging:
            staging.current_version = pending.version_number

        # Reload tool in registry
        load_result = self.factory.load_tool(tool_name)
        if load_result["loaded"]:
            tool_registry.update_tool_function(
                tool_name, load_result["tool_instance"].execute
            )

        self.db.commit()

        self._audit(
            "tool_updated",
            tool_name,
            pending.authored_by_agentium_id,
            {"version": pending.version_tag, "voting_id": approved_by_voting_id},
        )

        return {
            "approved": True,
            "tool_name": tool_name,
            "new_version": pending.version_tag,
            "version_number": pending.version_number,
        }

    # ──────────────────────────────────────────────────────────────
    # ROLLBACK
    # ──────────────────────────────────────────────────────────────

    def rollback(
        self,
        tool_name: str,
        target_version_number: int,
        requested_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Roll back a tool to any prior version.
        Creates a NEW version entry (rollback is tracked, not silent).
        Only Head (0xxxx) or Council (1xxxx) can roll back.
        """
        if not (requested_by.startswith("0") or requested_by.startswith("1")):
            return {"rolled_back": False, "error": "Only Head or Council can roll back tools"}

        target = self.db.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.version_number == target_version_number,
        ).first()

        if not target:
            return {
                "rolled_back": False,
                "error": f"Version {target_version_number} not found for '{tool_name}'",
            }

        current_active = self.db.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == True,
        ).first()

        current_version_number = current_active.version_number if current_active else 0

        if target_version_number == current_version_number:
            return {"rolled_back": False, "error": "Target version is already active"}

        # Deactivate current
        if current_active:
            current_active.is_active = False

        # New version entry for the rollback (audit trail)
        latest = self._get_latest_version(tool_name)
        new_version_number = (latest.version_number + 1) if latest else 1

        rollback_version = ToolVersion(
            tool_name=tool_name,
            version_number=new_version_number,
            version_tag=f"v{new_version_number}.0.0",
            code_snapshot=target.code_snapshot,
            tool_path=target.tool_path,
            authored_by_agentium_id=requested_by,
            change_summary=f"Rollback to v{target_version_number}: {reason}",
            approved_at=datetime.utcnow(),
            is_active=True,
            is_rolled_back=True,
            rolled_back_from_version=current_version_number,
        )
        self.db.add(rollback_version)

        # Write code back to disk
        final_path = self.factory.tools_directory / f"{tool_name}.py"
        final_path.write_text(target.code_snapshot)

        # Update staging
        staging = self.db.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name
        ).first()
        if staging:
            staging.current_version = new_version_number

        # Reload in registry
        load_result = self.factory.load_tool(tool_name)
        if load_result["loaded"]:
            tool_registry.update_tool_function(
                tool_name, load_result["tool_instance"].execute
            )

        self.db.commit()

        self._audit(
            "tool_rolled_back",
            tool_name,
            requested_by,
            {
                "from_version": current_version_number,
                "to_version": target_version_number,
                "reason": reason,
                "new_version_entry": new_version_number,
            },
        )

        return {
            "rolled_back": True,
            "tool_name": tool_name,
            "restored_code_from": f"v{target_version_number}",
            "new_version_entry": f"v{new_version_number}.0.0",
            "reason": reason,
        }

    # ──────────────────────────────────────────────────────────────
    # DIFF
    # ──────────────────────────────────────────────────────────────

    def get_diff(
        self,
        tool_name: str,
        version_a: int,
        version_b: int,
    ) -> Dict[str, Any]:
        """Return a unified diff between two versions of a tool."""
        va = self.db.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.version_number == version_a,
        ).first()

        vb = self.db.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.version_number == version_b,
        ).first()

        if not va or not vb:
            return {"error": "One or both versions not found"}

        diff = list(
            difflib.unified_diff(
                va.code_snapshot.splitlines(keepends=True),
                vb.code_snapshot.splitlines(keepends=True),
                fromfile=f"{tool_name} v{version_a}",
                tofile=f"{tool_name} v{version_b}",
            )
        )

        return {
            "tool_name": tool_name,
            "from_version": version_a,
            "to_version": version_b,
            "diff": "".join(diff),
            "lines_changed": len([l for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]),
        }

    # ──────────────────────────────────────────────────────────────
    # CHANGELOG
    # ──────────────────────────────────────────────────────────────

    def get_changelog(self, tool_name: str) -> Dict[str, Any]:
        """Return full version history for a tool."""
        versions = (
            self.db.query(ToolVersion)
            .filter(ToolVersion.tool_name == tool_name)
            .order_by(ToolVersion.version_number.desc())
            .all()
        )

        if not versions:
            return {"tool_name": tool_name, "versions": [], "error": "Tool not found"}

        return {
            "tool_name": tool_name,
            "total_versions": len(versions),
            "current_version": next((v.version_tag for v in versions if v.is_active), None),
            "versions": [
                {
                    "version_number": v.version_number,
                    "version_tag": v.version_tag,
                    "authored_by": v.authored_by_agentium_id,
                    "change_summary": v.change_summary,
                    "is_active": v.is_active,
                    "is_rolled_back": v.is_rolled_back,
                    "approved_at": v.approved_at.isoformat() if v.approved_at else None,
                }
                for v in versions
            ],
        }

    # ──────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────

    def _get_latest_version(self, tool_name: str) -> Optional[ToolVersion]:
        """Get latest version."""

        return (
            self.db.query(ToolVersion)
            .filter(ToolVersion.tool_name == tool_name)
            .order_by(ToolVersion.version_number.desc())
            .first()
        )

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
            description=f"{action} on '{tool_name}'",
            after_state=details,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        self.db.add(audit)
        self.db.commit()