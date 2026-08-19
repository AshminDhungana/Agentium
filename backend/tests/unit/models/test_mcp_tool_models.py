"""
Unit tests for MCP Tool models.
Tests MCPTool, ToolVersion, and ToolStaging models.
"""
import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4

try:
    from backend.models.entities.mcp_tool import MCPTool
    from backend.models.entities.tool_version import ToolVersion
    from backend.models.entities.tool_staging import ToolStaging
except ImportError:
    from models.entities.mcp_tool import MCPTool
    from models.entities.tool_version import ToolVersion
    from models.entities.tool_staging import ToolStaging


class TestMCPTool:
    """Tests for MCPTool model."""

    def test_mcp_tool_creation(self, db_session):
        """MCPTool creates with all required fields."""
        tool = MCPTool(
            agentium_id="MT00000001",  # Required
            name="github_search",
            description="Search GitHub repositories via MCP",
            server_url="stdio://github-mcp-server",
            tier="pre_approved",
            constitutional_article="article_5",
            status="approved",
            capabilities=["search_repos", "get_file", "list_branches"],
            health_status="healthy",
            proposed_by="00001",
            voting_id="vote-abc-123",
        )
        db_session.add(tool)
        db_session.commit()
        db_session.refresh(tool)

        assert tool.name == "github_search"
        assert tool.description == "Search GitHub repositories via MCP"
        assert tool.server_url == "stdio://github-mcp-server"
        assert tool.tier == "pre_approved"
        assert tool.constitutional_article == "article_5"
        assert tool.status == "approved"
        assert tool.capabilities == ["search_repos", "get_file", "list_branches"]
        assert tool.health_status == "healthy"
        assert tool.proposed_by == "00001"
        assert tool.voting_id == "vote-abc-123"
        assert tool.agentium_id == "MT00000001"

    def test_mcp_tool_defaults(self, db_session):
        """MCPTool defaults are correct."""
        tool = MCPTool(
            agentium_id="MT00000002",
            name="test_tool",
            description="Test tool",
            server_url="stdio://test-server",
        )
        db_session.add(tool)
        db_session.commit()

        assert tool.tier == "restricted"
        assert tool.constitutional_article is None
        assert tool.status == "pending"
        assert tool.approved_by_council is False
        assert tool.approval_vote_id is None
        assert tool.approved_at is None
        assert tool.approved_by is None
        assert tool.revoked_at is None
        assert tool.revoked_by is None
        assert tool.revocation_reason is None
        assert tool.capabilities == []
        assert tool.health_status == "unknown"
        assert tool.last_health_check_at is None
        assert tool.failure_count == 0
        assert tool.consecutive_failures == 0
        assert tool.usage_count == 0
        assert tool.last_used_at is None
        assert tool.audit_log == []
        assert tool.proposed_by is None
        assert tool.proposed_at is None
        assert tool.voting_id is None

    def test_mcp_tool_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        tool = MCPTool(
            agentium_id="MT00000003",
            name="jira_tool",
            description="Jira integration",
            server_url="stdio://jira-mcp",
            tier="restricted",
            constitutional_article="article_3",
            status="approved",
            approved_by_council=True,
            approval_vote_id="vote-123",
            approved_at=datetime.now(timezone.utc),
            approved_by="10001",
            capabilities=["create_issue", "search_issues", "update_issue"],
            health_status="healthy",
            failure_count=2,
            consecutive_failures=0,
            usage_count=150,
            last_used_at=datetime.now(timezone.utc),
            proposed_by="00001",
            proposed_at=datetime.now(timezone.utc),
            voting_id="vote-456",
        )
        db_session.add(tool)
        db_session.commit()

        data = tool.to_dict()
        assert data["name"] == "jira_tool"
        assert data["description"] == "Jira integration"
        assert data["server_url"] == "stdio://jira-mcp"
        assert data["tier"] == "restricted"
        assert data["constitutional_article"] == "article_3"
        assert data["status"] == "approved"
        assert data["approved_by_council"] is True
        assert data["approval_vote_id"] == "vote-123"
        assert data["approved_by"] == "10001"
        assert data["capabilities"] == ["create_issue", "search_issues", "update_issue"]
        assert data["health_status"] == "healthy"
        assert data["failure_count"] == 2
        assert data["consecutive_failures"] == 0
        assert data["usage_count"] == 150
        assert "created_at" in data
        assert "updated_at" in data

    def test_mcp_tool_tier_validation(self, db_session):
        """MCPTool accepts all valid tier values."""
        for tier in ["pre_approved", "restricted", "forbidden"]:
            tool = MCPTool(
                agentium_id=f"MT{tier[:8].upper()}",
                name=f"tool_{tier}",
                description="Test",
                server_url="stdio://test",
                tier=tier,
            )
            db_session.add(tool)
            db_session.commit()
            assert tool.tier == tier
            db_session.delete(tool)
            db_session.commit()

    def test_mcp_tool_status_values(self, db_session):
        """MCPTool accepts all valid status values."""
        for status in ["pending", "approved", "rejected", "revoked", "disabled"]:
            tool = MCPTool(
                agentium_id=f"MT{status[:8].upper()}",
                name=f"tool_{status}",
                description="Test",
                server_url="stdio://test",
                status=status,
            )
            db_session.add(tool)
            db_session.commit()
            assert tool.status == status
            db_session.delete(tool)
            db_session.commit()

    def test_mcp_tool_audit_log_append(self, db_session):
        """audit_log can append entries correctly."""
        from sqlalchemy.orm.attributes import flag_modified

        tool = MCPTool(
            agentium_id="MT00000004",
            name="audit_test",
            description="Test",
            server_url="stdio://test",
        )
        db_session.add(tool)
        db_session.commit()

        # Append audit entry - need to flag as modified for JSON list
        tool.audit_log.append({
            "agent_id": "agent-123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_hash": "abc123",
            "result": "success"
        })
        flag_modified(tool, "audit_log")
        db_session.commit()
        db_session.refresh(tool)

        assert len(tool.audit_log) == 1
        assert tool.audit_log[0]["agent_id"] == "agent-123"
        assert tool.audit_log[0]["result"] == "success"


class TestToolVersion:
    """Tests for ToolVersion model."""

    def test_tool_version_creation(self, db_session):
        """ToolVersion creates with all required fields."""
        version = ToolVersion(
            tool_name="github_search",
            version_number=1,
            version_tag="v1.0.0",
            code_snapshot="def search():\n    pass",
            tool_path="/tools/github_search.py",
            authored_by_agentium_id="00001",
            change_summary="Initial version",
            approved_by_voting_id="vote-123",
            approved_at=datetime.now(timezone.utc),
            is_active=True,
            is_rolled_back=False,
        )
        db_session.add(version)
        db_session.commit()
        db_session.refresh(version)

        assert version.tool_name == "github_search"
        assert version.version_number == 1
        assert version.version_tag == "v1.0.0"
        assert version.code_snapshot == "def search():\n    pass"
        assert version.tool_path == "/tools/github_search.py"
        assert version.authored_by_agentium_id == "00001"
        assert version.change_summary == "Initial version"
        assert version.approved_by_voting_id == "vote-123"
        assert version.is_active is True
        assert version.is_rolled_back is False
        assert version.rolled_back_from_version is None

    def test_tool_version_defaults(self, db_session):
        """ToolVersion defaults are correct."""
        version = ToolVersion(
            tool_name="test_tool",
            version_number=2,
            version_tag="v2.0.0",
            code_snapshot="def test():\n    pass",
            tool_path="/tools/test_tool.py",
            authored_by_agentium_id="10001",
        )
        db_session.add(version)
        db_session.commit()

        assert version.change_summary is None
        assert version.approved_by_voting_id is None
        assert version.approved_at is None
        assert version.is_active is False
        assert version.is_rolled_back is False
        assert version.rolled_back_from_version is None
        assert version.agentium_id is None  # Not used for tool tables

    def test_tool_version_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        version = ToolVersion(
            tool_name="jira_tool",
            version_number=3,
            version_tag="v3.0.0",
            code_snapshot="def create():\n    pass",
            tool_path="/tools/jira_tool.py",
            authored_by_agentium_id="10001",
            change_summary="Added create_issue",
            approved_by_voting_id="vote-456",
            approved_at=datetime.now(timezone.utc),
            is_active=True,
            is_rolled_back=False,
            rolled_back_from_version=2,
        )
        db_session.add(version)
        db_session.commit()

        data = version.to_dict()
        assert data["tool_name"] == "jira_tool"
        assert data["version_number"] == 3
        assert data["version_tag"] == "v3.0.0"
        assert data["authored_by"] == "10001"
        assert data["change_summary"] == "Added create_issue"
        assert data["approved_by_voting_id"] == "vote-456"
        assert data["is_active"] is True
        assert data["is_rolled_back"] is False
        assert data["rolled_back_from_version"] == 2
        assert "created_at" in data

    def test_tool_version_multiple_versions_same_tool(self, db_session):
        """Multiple versions for same tool are independent records."""
        v1 = ToolVersion(
            tool_name="shared_tool",
            version_number=1,
            version_tag="v1.0.0",
            code_snapshot="def v1():\n    pass",
            tool_path="/tools/shared_tool.py",
            authored_by_agentium_id="00001",
            is_active=True,
        )
        v2 = ToolVersion(
            tool_name="shared_tool",
            version_number=2,
            version_tag="v2.0.0",
            code_snapshot="def v2():\n    pass",
            tool_path="/tools/shared_tool.py",
            authored_by_agentium_id="10001",
            is_active=False,
        )
        db_session.add_all([v1, v2])
        db_session.commit()

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v1.is_active is True
        assert v2.is_active is False
        assert v1.id != v2.id


class TestToolStaging:
    """Tests for ToolStaging model."""

    def test_tool_staging_creation(self, db_session):
        """ToolStaging creates with all fields."""
        request_json = json.dumps({
            "tool_name": "slack_notify",
            "description": "Send Slack notifications",
            "input_schema": {"message": {"type": "string"}},
            "code_template": "def notify(message): ..."
        })
        staging = ToolStaging(
            tool_name="slack_notify",
            proposed_by_agentium_id="20001",
            tool_path="/tools/staging/slack_notify.py",
            request_json=request_json,
            requires_vote=True,
            voting_id="vote-789",
            status="pending_approval",
            current_version=1,
        )
        db_session.add(staging)
        db_session.commit()
        db_session.refresh(staging)

        assert staging.tool_name == "slack_notify"
        assert staging.proposed_by_agentium_id == "20001"
        assert staging.tool_path == "/tools/staging/slack_notify.py"
        assert staging.request_json == request_json
        assert staging.requires_vote is True
        assert staging.voting_id == "vote-789"
        assert staging.status == "pending_approval"
        assert staging.current_version == 1
        assert staging.activated_at is None
        assert staging.deprecated_at is None
        assert staging.sunset_at is None
        assert staging.deprecated_by_agentium_id is None
        assert staging.deprecation_reason is None
        assert staging.replacement_tool_name is None

    def test_tool_staging_defaults(self, db_session):
        """ToolStaging defaults are correct."""
        staging = ToolStaging(
            tool_name="default_test",
            proposed_by_agentium_id="30001",
            tool_path="/tools/default_test.py",
            request_json="{}",
        )
        db_session.add(staging)
        db_session.commit()

        assert staging.requires_vote is True
        assert staging.voting_id is None
        assert staging.status == "pending_approval"
        assert staging.current_version == 1
        assert staging.activated_at is None
        assert staging.deprecated_at is None
        assert staging.sunset_at is None
        assert staging.agentium_id is None  # Not used for tool tables

    def test_tool_staging_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        staging = ToolStaging(
            tool_name="email_sender",
            proposed_by_agentium_id="10001",
            tool_path="/tools/email_sender.py",
            request_json='{"tool_name": "email_sender"}',
            requires_vote=False,
            status="activated",
            current_version=2,
            activated_at=datetime.now(timezone.utc),
            deprecated_at=None,
            sunset_at=None,
            deprecated_by_agentium_id=None,
            deprecation_reason=None,
            replacement_tool_name=None,
        )
        db_session.add(staging)
        db_session.commit()

        data = staging.to_dict()
        assert data["tool_name"] == "email_sender"
        assert data["proposed_by"] == "10001"
        assert data["tool_path"] == "/tools/email_sender.py"
        assert data["status"] == "activated"
        assert data["requires_vote"] is False
        assert data["current_version"] == 2
        assert "created_at" in data
        assert data["activated_at"] is not None
        assert data["deprecated_at"] is None

    def test_tool_staging_lifecycle_statuses(self, db_session):
        """ToolStaging accepts all valid lifecycle status values."""
        for status in ["pending_approval", "approved", "activated", "rejected", "deprecated", "sunset"]:
            staging = ToolStaging(
                tool_name=f"tool_{status}",
                proposed_by_agentium_id="00001",
                tool_path=f"/tools/{status}.py",
                request_json="{}",
                status=status,
            )
            db_session.add(staging)
            db_session.commit()
            assert staging.status == status
            db_session.delete(staging)
            db_session.commit()

    def test_tool_staging_unique_tool_name(self, db_session):
        """tool_name is unique."""
        staging1 = ToolStaging(
            tool_name="unique_tool",
            proposed_by_agentium_id="00001",
            tool_path="/tools/unique.py",
            request_json="{}",
        )
        db_session.add(staging1)
        db_session.commit()

        # Second with same name should fail
        staging2 = ToolStaging(
            tool_name="unique_tool",
            proposed_by_agentium_id="10001",
            tool_path="/tools/unique2.py",
            request_json="{}",
        )
        db_session.add(staging2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
        db_session.rollback()


class TestMCPToolIntegration:
    """Integration tests for MCP Tool workflows."""

    def test_mcp_tool_with_versions_and_staging(self, db_session):
        """Full workflow: staging → tool → versions."""
        # 1. Create staging proposal
        request_json = json.dumps({
            "tool_name": "calculator",
            "description": "Basic math operations",
            "input_schema": {"a": {"type": "number"}, "b": {"type": "number"}}
        })
        proposed_at = datetime.now(timezone.utc)
        staging = ToolStaging(
            tool_name="calculator",
            proposed_by_agentium_id="00001",
            tool_path="/tools/calculator.py",
            request_json=request_json,
            requires_vote=True,
            status="pending_approval",
        )
        db_session.add(staging)
        db_session.commit()

        # 2. Approve and activate
        staging.status = "approved"
        staging.voting_id = "vote-abc"
        db_session.commit()

        staging.status = "activated"
        staging.activated_at = datetime.now(timezone.utc)
        db_session.commit()

        # 3. Create MCPTool record
        tool = MCPTool(
            agentium_id="MT00000005",
            name="calculator",
            description="Basic math operations",
            server_url="stdio://calculator-mcp",
            tier="pre_approved",
            status="approved",
            approved_by_council=True,
            approval_vote_id="vote-abc",
            approved_at=datetime.now(timezone.utc),
            approved_by="00001",
            capabilities=["add", "subtract", "multiply", "divide"],
            proposed_by="00001",
            proposed_at=proposed_at,
            voting_id="vote-abc",
        )
        db_session.add(tool)
        db_session.commit()

        # 4. Create ToolVersion
        version = ToolVersion(
            tool_name="calculator",
            version_number=1,
            version_tag="v1.0.0",
            code_snapshot="def add(a,b): return a+b",
            tool_path="/tools/calculator.py",
            authored_by_agentium_id="00001",
            change_summary="Initial release",
            approved_by_voting_id="vote-abc",
            approved_at=datetime.now(timezone.utc),
            is_active=True,
        )
        db_session.add(version)
        db_session.commit()

        # Verify workflow
        assert staging.status == "activated"
        assert staging.voting_id == "vote-abc"
        assert tool.name == "calculator"
        assert tool.status == "approved"
        assert tool.approved_by_council is True
        assert tool.capabilities == ["add", "subtract", "multiply", "divide"]
        assert version.tool_name == "calculator"
        assert version.version_number == 1
        assert version.is_active is True

    def test_mcp_tool_health_update(self, db_session):
        """Health status updates work correctly."""
        tool = MCPTool(
            agentium_id="MT00000006",
            name="health_test",
            description="Test",
            server_url="stdio://health",
        )
        db_session.add(tool)
        db_session.commit()

        # Initial state
        assert tool.health_status == "unknown"
        assert tool.failure_count == 0
        assert tool.consecutive_failures == 0

        # Mark healthy
        tool.health_status = "healthy"
        tool.last_health_check_at = datetime.now(timezone.utc)
        tool.consecutive_failures = 0
        db_session.commit()
        assert tool.health_status == "healthy"
        assert tool.consecutive_failures == 0

        # Mark degraded
        tool.health_status = "degraded"
        tool.failure_count += 1
        tool.consecutive_failures = 1
        db_session.commit()
        assert tool.health_status == "degraded"
        assert tool.failure_count == 1
        assert tool.consecutive_failures == 1

        # Mark down
        tool.health_status = "down"
        tool.consecutive_failures = 5
        db_session.commit()
        assert tool.health_status == "down"
        assert tool.consecutive_failures == 5

    def test_mcp_tool_revocation(self, db_session):
        """Tool revocation workflow."""
        tool = MCPTool(
            agentium_id="MT00000007",
            name="revocable_tool",
            description="Test",
            server_url="stdio://revoke",
            status="approved",
            approved_by_council=True,
            approved_at=datetime.now(timezone.utc),
            approved_by="00001",
        )
        db_session.add(tool)
        db_session.commit()

        # Revoke
        tool.status = "revoked"
        tool.revoked_at = datetime.now(timezone.utc)
        tool.revoked_by = "00001"
        tool.revocation_reason = "Security vulnerability"
        db_session.commit()
        db_session.refresh(tool)

        assert tool.status == "revoked"
        assert tool.revoked_at is not None
        assert tool.revoked_by == "00001"
        assert tool.revocation_reason == "Security vulnerability"