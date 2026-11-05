"""Integration tests for Tool Versioning Rollback (Task 21.5.3).

Verifies POST /tool-management/{tool_name}/versions/rollback completes
in under 5 minutes (300s) without data corruption.
"""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

# Pytest markers
pytestmark = [
    pytest.mark.integration,
    pytest.mark.rollback,
    pytest.mark.sla,
]

from backend.services.tool_versioning import ToolVersioningService
from backend.models.entities.tool_version import ToolVersion
from backend.models.entities.tool_staging import ToolStaging
from backend.models.entities.audit import AuditLog
from backend.core.tool_registry import tool_registry
from tests.conftest import assert_completes_under


# ──────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def head_agent_id():
    """Mock Head of Council agent ID (0xxxx tier)."""
    return "00001"


@pytest.fixture
def council_agent_id():
    """Mock Council agent ID (1xxxx tier)."""
    return "10001"


@pytest.fixture
def task_agent_id():
    """Mock Task agent ID (3xxxx tier) - should be rejected for rollback."""
    return "30001"


def _make_tool_code(tool_name: str, version: int) -> str:
    """Generate tool code in the format expected by ToolFactory.load_tool()."""
    class_name = tool_name.replace('-', '_').replace(' ', '_').title()
    return f'''"""
Test tool {tool_name} version {version}
"""
from typing import Dict, Any

class {class_name}Tool:
    """Test tool for rollback."""

    def __init__(self):
        self.tool_name = "{tool_name}"
        self.version = {version}

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input and return result."""
        return {{"version": {version}, "result": "processed", "input": input_data}}

# Export tool instance
tool_instance = {class_name}Tool()
'''


@pytest.fixture
def tool_with_versions(db_session: Session, head_agent_id: str):
    """
    Create a tool with 5 versions (v1-v5), v5 active.
    Minimal fixture - directly creates DB entries for fast, unit-test style tests.
    """
    tool_name = "test_rollback_tool"
    tool_path = Path("backend/tools/generated") / f"{tool_name}.py"

    # Ensure tools directory exists
    tool_path.parent.mkdir(parents=True, exist_ok=True)

    service = ToolVersioningService(db_session)

    # First, create the ToolStaging entry (as if the tool was already activated)
    staging = ToolStaging(
        tool_name=tool_name,
        status="activated",
        current_version=5,
        request_json='{"name": "test_rollback_tool", "description": "Test tool for rollback", "authorized_tiers": ["0xxxx", "1xxxx", "2xxxx"]}',
        proposed_by_agentium_id=head_agent_id,
        tool_path=str(tool_path),
    )
    db_session.add(staging)
    db_session.commit()
    db_session.refresh(staging)

    # Create 5 versions directly in DB (minimal fixture approach)
    versions = []
    from datetime import datetime
    for i in range(1, 6):
        code = _make_tool_code(tool_name, i)

        version = ToolVersion(
            tool_name=tool_name,
            version_number=i,
            version_tag=f"v{i}.0.0",
            code_snapshot=code,
            tool_path=str(tool_path),
            authored_by_agentium_id=head_agent_id,
            change_summary=f"Version {i}",
            approved_at=datetime.utcnow(),
            is_active=(i == 5),
            is_rolled_back=False,
        )
        db_session.add(version)
        versions.append(version)

    db_session.commit()

    # Write the active version (v5) to disk
    tool_path.write_text(versions[4].code_snapshot)

    # Load and register the tool properly
    load_result = service.factory.load_tool(tool_name)
    if load_result["loaded"]:
        tool_registry.register_tool(
            name=tool_name,
            description="Test tool for rollback",
            function=load_result["tool_instance"].execute,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )

    # Verify v5 is active
    active = db_session.query(ToolVersion).filter(
        ToolVersion.tool_name == tool_name,
        ToolVersion.is_active == True,
    ).first()
    assert active.version_number == 5

    yield {
        "tool_name": tool_name,
        "tool_path": tool_path,
        "versions": versions,
        "head_agent_id": head_agent_id,
    }

    # Cleanup
    if tool_path.exists():
        tool_path.unlink()
    # Clean up any staged files
    for staged in tool_path.parent.glob(f"{tool_name}_v*_staged.py"):
        staged.unlink()
    for test_temp in tool_path.parent.glob(f"{tool_name}_test_temp.py"):
        test_temp.unlink()


# ──────────────────────────────────────────────────────────────────────────────
# TESTS
# ──────────────────────────────────────────────────────────────────────────────

class TestToolRollbackSLA:
    """SLA verification tests."""

    def test_rollback_to_prior_version_completes_under_5min(
        self, tool_with_versions, db_session: Session, head_agent_id: str
    ):
        """Rollback from v5 to v3 must complete within 300 seconds."""
        tool_name = tool_with_versions["tool_name"]
        service = ToolVersioningService(db_session)

        with assert_completes_under(300):
            result = service.rollback(
                tool_name=tool_name,
                target_version_number=3,
                requested_by=head_agent_id,
                reason="Test rollback for SLA verification",
            )

        assert result["rolled_back"] is True
        assert result["restored_code_from"] == "v3"
        assert "new_version_entry" in result


class TestToolRollbackDataIntegrity:
    """Data integrity verification tests."""

    def test_rollback_restores_correct_code_snapshot(
        self, tool_with_versions, db_session: Session, head_agent_id: str
    ):
        """Disk code must match target version's code_snapshot exactly."""
        tool_name = tool_with_versions["tool_name"]
        tool_path = tool_with_versions["tool_path"]
        service = ToolVersioningService(db_session)

        # Get target version's code snapshot
        target_version = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.version_number == 3,
        ).first()
        expected_code = target_version.code_snapshot

        # Perform rollback
        service.rollback(
            tool_name=tool_name,
            target_version_number=3,
            requested_by=head_agent_id,
            reason="Verify code restoration",
        )

        # Read code from disk
        actual_code = tool_path.read_text()
        assert actual_code == expected_code

    def test_rollback_updates_tool_registry(
        self, tool_with_versions, db_session: Session, head_agent_id: str
    ):
        """tool_registry.get(tool_name) must return rolled-back function."""
        tool_name = tool_with_versions["tool_name"]
        service = ToolVersioningService(db_session)

        # Get the function from registry before rollback
        func_before = tool_registry.get_tool_function(tool_name)
        assert func_before is not None
        result_before = func_before({"test": "data"})

        # Perform rollback to v3
        result = service.rollback(
            tool_name=tool_name,
            target_version_number=3,
            requested_by=head_agent_id,
            reason="Verify registry update",
        )

        # Check what's in the registry after
        func_after = tool_registry.get_tool_function(tool_name)
        assert func_after is not None

        # Execute both to verify different behavior
        result_after = func_after({"test": "data"})

        # v5 returns version 5, v3 returns version 3
        assert result_before["version"] == 5
        assert result_after["version"] == 3

    def test_rollback_creates_new_version_entry(
        self, tool_with_versions, db_session: Session, head_agent_id: str
    ):
        """New ToolVersion with is_rolled_back=True, rolled_back_from_version set."""
        tool_name = tool_with_versions["tool_name"]
        service = ToolVersioningService(db_session)

        # Count versions before
        count_before = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name
        ).count()

        # Perform rollback
        result = service.rollback(
            tool_name=tool_name,
            target_version_number=3,
            requested_by=head_agent_id,
            reason="Verify new version entry",
        )

        # Count versions after
        count_after = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name
        ).count()

        assert count_after == count_before + 1

        # Verify new version properties
        new_version = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.version_number == 6,  # v5 + 1
        ).first()

        assert new_version is not None
        assert new_version.is_active is True
        assert new_version.is_rolled_back is True
        assert new_version.rolled_back_from_version == 5
        assert "Rollback to v3" in new_version.change_summary
        assert new_version.code_snapshot == tool_with_versions["versions"][2].code_snapshot  # v3 code

    def test_rollback_updates_staging_current_version(
        self, tool_with_versions, db_session: Session, head_agent_id: str
    ):
        """ToolStaging.current_version must match new rollback version."""
        tool_name = tool_with_versions["tool_name"]
        service = ToolVersioningService(db_session)

        staging_before = db_session.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name
        ).first()
        assert staging_before.current_version == 5

        service.rollback(
            tool_name=tool_name,
            target_version_number=3,
            requested_by=head_agent_id,
            reason="Verify staging update",
        )

        staging_after = db_session.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name
        ).first()
        assert staging_after.current_version == 6  # New rollback version

    def test_rollback_audit_log_created(
        self, tool_with_versions, db_session: Session, head_agent_id: str
    ):
        """AuditLog entry with action="tool_rolled_back", correct details."""
        tool_name = tool_with_versions["tool_name"]
        service = ToolVersioningService(db_session)

        # Count audit logs before
        count_before = db_session.query(AuditLog).filter(
            AuditLog.action == "tool_rolled_back",
            AuditLog.target_id == tool_name,
        ).count()

        service.rollback(
            tool_name=tool_name,
            target_version_number=3,
            requested_by=head_agent_id,
            reason="Verify audit log",
        )

        # Count audit logs after
        count_after = db_session.query(AuditLog).filter(
            AuditLog.action == "tool_rolled_back",
            AuditLog.target_id == tool_name,
        ).count()

        assert count_after == count_before + 1

        # Verify audit log details
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "tool_rolled_back",
            AuditLog.target_id == tool_name,
        ).order_by(AuditLog.created_at.desc()).first()

        assert audit.actor_id == head_agent_id
        assert audit.target_type == "tool"
        assert audit.target_id == tool_name
        import json
        after_state = json.loads(audit.after_state)
        assert after_state["from_version"] == 5
        assert after_state["to_version"] == 3
        assert after_state["reason"] == "Verify audit log"
        assert after_state["new_version_entry"] == 6


class TestToolRollbackAuth:
    """Authorization enforcement tests."""

    def test_rollback_rejects_unauthorized_agent(
        self, tool_with_versions, db_session: Session, task_agent_id: str
    ):
        """Task agent (3xxxx) gets 403 / rejected."""
        tool_name = tool_with_versions["tool_name"]
        service = ToolVersioningService(db_session)

        result = service.rollback(
            tool_name=tool_name,
            target_version_number=3,
            requested_by=task_agent_id,
            reason="Unauthorized attempt",
        )

        assert result["rolled_back"] is False
        assert "Only Head or Council can roll back" in result["error"]

        # Verify no state change
        active = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == True,
        ).first()
        assert active.version_number == 5


class TestToolRollbackErrorHandling:
    """Error handling tests."""

    def test_rollback_rejects_invalid_version(
        self, tool_with_versions, db_session: Session, head_agent_id: str
    ):
        """Non-existent version returns error, no state change."""
        tool_name = tool_with_versions["tool_name"]
        service = ToolVersioningService(db_session)

        # Try to rollback to version 99 (doesn't exist)
        result = service.rollback(
            tool_name=tool_name,
            target_version_number=99,
            requested_by=head_agent_id,
            reason="Invalid version test",
        )

        assert result["rolled_back"] is False
        assert "not found" in result["error"]

        # Verify no state change
        active = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == True,
        ).first()
        assert active.version_number == 5

        # Verify no new version created
        count = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name
        ).count()
        assert count == 5  # Still only 5 versions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])