"""
Integration tests for MCPTool, ToolVersion, and ToolStaging models (3.3.10).
Verifies tool lifecycle (proposed -> pending -> approved -> revoked/disabled), versioning, rollback, and staging area.
"""
import pytest
import json
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from backend.models.entities.mcp_tool import MCPTool
from backend.models.entities.tool_version import ToolVersion
from backend.models.entities.tool_staging import ToolStaging


def test_mcp_tool_persist_all_tiers(db_session):
    """Verify MCPTool tiers (pre_approved, restricted, forbidden) persist."""
    tiers = ["pre_approved", "restricted", "forbidden"]
    for idx, tier in enumerate(tiers):
        tool = MCPTool(
            agentium_id=f"MT00{idx:02d}",
            name=f"tool_{tier}",
            description=f"Test tool for tier {tier}",
            server_url=f"http://localhost:808{idx}/mcp",
            tier=tier,
            status="pending",
        )
        db_session.add(tool)
    db_session.commit()

    for idx, tier in enumerate(tiers):
        fetched = db_session.query(MCPTool).filter_by(name=f"tool_{tier}").first()
        assert fetched is not None
        assert fetched.tier == tier


def test_mcp_tool_status_lifecycle(db_session, sample_mcp_tool):
    """Verify MCPTool status transitions: pending -> approved -> revoked."""
    assert sample_mcp_tool.status == "pending"
    assert sample_mcp_tool.approved_by_council is False

    # Approve tool
    now = datetime.now(timezone.utc)
    sample_mcp_tool.status = "approved"
    sample_mcp_tool.approved_by_council = True
    sample_mcp_tool.approved_at = now
    sample_mcp_tool.approved_by = "00001"
    db_session.commit()

    fetched = db_session.query(MCPTool).filter_by(id=sample_mcp_tool.id).first()
    assert fetched.status == "approved"
    assert fetched.approved_by_council is True
    assert fetched.approved_by == "00001"

    # Revoke tool
    revoke_now = datetime.now(timezone.utc)
    sample_mcp_tool.status = "revoked"
    sample_mcp_tool.revoked_at = revoke_now
    sample_mcp_tool.revoked_by = "00001"
    sample_mcp_tool.revocation_reason = "Security policy change"
    db_session.commit()

    refetched = db_session.query(MCPTool).filter_by(id=sample_mcp_tool.id).first()
    assert refetched.status == "revoked"
    assert refetched.revocation_reason == "Security policy change"


def test_mcp_tool_health_tracking(db_session, sample_mcp_tool):
    """Verify health status, failure count, and consecutive failure fields."""
    assert sample_mcp_tool.health_status == "unknown"
    assert sample_mcp_tool.failure_count == 0

    sample_mcp_tool.health_status = "degraded"
    sample_mcp_tool.failure_count = 3
    sample_mcp_tool.consecutive_failures = 3
    sample_mcp_tool.last_health_check_at = datetime.now(timezone.utc)
    db_session.commit()

    fetched = db_session.query(MCPTool).filter_by(id=sample_mcp_tool.id).first()
    assert fetched.health_status == "degraded"
    assert fetched.failure_count == 3
    assert fetched.consecutive_failures == 3


def test_mcp_tool_usage_stats(db_session, sample_mcp_tool):
    """Verify usage_count and last_used_at fields."""
    assert sample_mcp_tool.usage_count == 0

    now = datetime.now(timezone.utc)
    sample_mcp_tool.usage_count += 1
    sample_mcp_tool.last_used_at = now
    db_session.commit()

    fetched = db_session.query(MCPTool).filter_by(id=sample_mcp_tool.id).first()
    assert fetched.usage_count == 1
    assert fetched.last_used_at is not None


def test_tool_version_persist_and_activate(db_session):
    """Verify ToolVersion records save code snapshots and manage activation."""
    v1 = ToolVersion(
        agentium_id="TV10001",
        tool_name="file_parser",
        version_number=1,
        version_tag="v1.0.0",
        code_snapshot="def parse(f): return f.read()",
        tool_path="/tools/file_parser.py",
        authored_by_agentium_id="00001",
        is_active=False,
    )
    v2 = ToolVersion(
        agentium_id="TV10002",
        tool_name="file_parser",
        version_number=2,
        version_tag="v2.0.0",
        code_snapshot="def parse(f): return f.read().strip()",
        tool_path="/tools/file_parser.py",
        authored_by_agentium_id="00001",
        is_active=True,
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    active_v = db_session.query(ToolVersion).filter_by(tool_name="file_parser", is_active=True).first()
    assert active_v is not None
    assert active_v.version_number == 2
    assert active_v.version_tag == "v2.0.0"


def test_tool_version_rollback_flag(db_session, sample_tool_version):
    """Verify rollback flag setting on ToolVersion."""
    sample_tool_version.is_rolled_back = True
    sample_tool_version.rolled_back_from_version = 2
    db_session.commit()

    fetched = db_session.query(ToolVersion).filter_by(id=sample_tool_version.id).first()
    assert fetched.is_rolled_back is True
    assert fetched.rolled_back_from_version == 2


def test_tool_staging_lifecycle(db_session, sample_tool_staging):
    """Verify ToolStaging lifecycle: pending_approval -> approved -> activated -> deprecated."""
    assert sample_tool_staging.status == "pending_approval"

    # Approve
    sample_tool_staging.status = "approved"
    db_session.commit()

    # Activate
    sample_tool_staging.status = "activated"
    sample_tool_staging.activated_at = datetime.now(timezone.utc)
    db_session.commit()

    fetched = db_session.query(ToolStaging).filter_by(id=sample_tool_staging.id).first()
    assert fetched.status == "activated"
    assert fetched.activated_at is not None

    # Deprecate
    sample_tool_staging.status = "deprecated"
    sample_tool_staging.deprecated_at = datetime.now(timezone.utc)
    sample_tool_staging.deprecated_by_agentium_id = "00001"
    sample_tool_staging.deprecation_reason = "Replaced by v2"
    sample_tool_staging.replacement_tool_name = "staged_tool_v2"
    db_session.commit()

    refetched = db_session.query(ToolStaging).filter_by(id=sample_tool_staging.id).first()
    assert refetched.status == "deprecated"
    assert refetched.deprecation_reason == "Replaced by v2"
    assert refetched.replacement_tool_name == "staged_tool_v2"


def test_mcp_tool_unique_name_constraint(db_session, sample_mcp_tool):
    """Verify duplicate MCPTool name raises IntegrityError."""
    dup_tool = MCPTool(
        agentium_id="MT99999",
        name=sample_mcp_tool.name,  # Duplicate name
        description="Duplicate tool",
        server_url="http://localhost:9999/mcp",
    )
    db_session.add(dup_tool)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
