"""
MCP API Integration Tests — Phase 17.3
======================================
Verifies:
  - 17.3.1: GET /api/v1/mcp/tools lists available MCP tools with filtering
  - 17.3.2: POST /api/v1/mcp/tools/invoke executes MCP tools with governance
  - 17.3.3: MCP tool configuration (server URL, auth) works
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.models.entities.mcp_tool import MCPTool
from backend.services.mcp_governance import (
    STATUS_APPROVED,
    STATUS_PENDING,
    TIER_PRE_APPROVED,
    TIER_RESTRICTED,
    TIER_FORBIDDEN,
)

pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique(prefix: str = "tool") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _make_tool(
    db,
    *,
    tier: str = TIER_PRE_APPROVED,
    status: str = STATUS_APPROVED,
    name: str | None = None,
    server_url: str | None = None,
    config: dict | None = None,
) -> MCPTool:
    name = name or _unique("mcp")
    server_url = server_url or f"mock://localhost/{name}"
    tool = MCPTool(
        name=name,
        description=f"Description for {name}",
        server_url=server_url,
        tier=tier,
        status=status,
        proposed_by="00001",
        approved_by_council=(status == STATUS_APPROVED),
        failure_count=0,
        consecutive_failures=0,
        usage_count=0,
        health_status="unknown",
        is_active=True,
        agentium_id=f"mcp-{uuid.uuid4().hex[:12]}",
        capabilities=[{"name": name, "description": "test cap", "input_schema": {}}],
        audit_log=[],
    )
    if config:
        tool.set_config(config)
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


def _configure_mock_mcp(mock_cls, result: dict | None = None, *, raise_exc=None):
    mock_cls.hash_params.return_value = "param_hash_123"
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    if raise_exc is not None:
        mock_cm.call_tool = AsyncMock(side_effect=raise_exc)
    else:
        mock_cm.call_tool = AsyncMock(
            return_value=result or {
                "success": True,
                "tool": "mock_tool",
                "result": [{"type": "text", "text": "executed successfully"}],
            }
        )
    mock_cm.health_check = AsyncMock(
        return_value={"healthy": True, "latency_ms": 12.5, "tool_count": 1, "error": None}
    )
    mock_cls.return_value = mock_cm
    mock_cls.side_effect = None
    return mock_cm


# ══════════════════════════════════════════════════════════════════════════════
# 17.3.1: GET /api/v1/mcp/tools lists available MCP tools
# ══════════════════════════════════════════════════════════════════════════════

class TestMCPToolListAPI:

    def test_list_tools_endpoint_success(self, client, auth_headers, db_session):
        """GET /api/v1/mcp/tools returns 200 with list of tools."""
        t1 = _make_tool(db_session, name=_unique("list_t1"))
        t2 = _make_tool(db_session, name=_unique("list_t2"))

        resp = client.get("/api/v1/mcp/tools", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert "total" in data
        tool_names = [t["name"] for t in data["tools"]]
        assert t1.name in tool_names
        assert t2.name in tool_names

    def test_list_tools_filtering_by_status(self, client, auth_headers, db_session):
        """Filtering by ?status=approved vs ?status=pending works."""
        approved = _make_tool(db_session, status=STATUS_APPROVED, name=_unique("appr"))
        pending = _make_tool(db_session, status=STATUS_PENDING, name=_unique("pend"))

        r_appr = client.get("/api/v1/mcp/tools?status=approved", headers=auth_headers)
        assert r_appr.status_code == 200
        appr_names = [t["name"] for t in r_appr.json()["tools"]]
        assert approved.name in appr_names
        assert pending.name not in appr_names

        r_pend = client.get("/api/v1/mcp/tools?status=pending", headers=auth_headers)
        assert r_pend.status_code == 200
        pend_names = [t["name"] for t in r_pend.json()["tools"]]
        assert pending.name in pend_names
        assert approved.name not in pend_names

    def test_list_tools_filtering_by_tier(self, client, auth_headers, db_session):
        """Filtering by ?tier=pre_approved vs ?tier=restricted works."""
        pre = _make_tool(db_session, tier=TIER_PRE_APPROVED, name=_unique("pre"))
        restr = _make_tool(db_session, tier=TIER_RESTRICTED, name=_unique("restr"))

        resp = client.get("/api/v1/mcp/tools?tier=pre_approved", headers=auth_headers)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()["tools"]]
        assert pre.name in names
        assert restr.name not in names

    def test_list_tools_agent_tier_visibility_filter(self, client, auth_headers, db_session):
        """Filtering by ?agent_tier=3xxxx restricts view to pre_approved tools."""
        pre = _make_tool(db_session, tier=TIER_PRE_APPROVED, name=_unique("vis_pre"))
        restr = _make_tool(db_session, tier=TIER_RESTRICTED, name=_unique("vis_restr"))

        resp = client.get("/api/v1/mcp/tools?agent_tier=3xxxx", headers=auth_headers)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()["tools"]]
        assert pre.name in names
        assert restr.name not in names

    def test_list_tools_legacy_parity(self, client, auth_headers, db_session):
        """Parity check: /api/v1/mcp/tools and /api/v1/mcp-tools return identical schemas."""
        _make_tool(db_session, name=_unique("parity"))

        r1 = client.get("/api/v1/mcp/tools", headers=auth_headers)
        r2 = client.get("/api/v1/mcp-tools", headers=auth_headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert set(r1.json().keys()) == set(r2.json().keys())


# ══════════════════════════════════════════════════════════════════════════════
# 17.3.2: POST /api/v1/mcp/tools/invoke executes MCP tool
# ══════════════════════════════════════════════════════════════════════════════

class TestMCPToolInvocationAPI:

    @patch("backend.services.mcp_governance.MCPClient")
    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invoke_tool_by_name_success(self, mock_client_cls, client, auth_headers, db_session):
        """Invoking by tool_name succeeds and returns result."""
        tool = _make_tool(db_session, tier=TIER_PRE_APPROVED, name=_unique("invoke_name"))
        _configure_mock_mcp(mock_client_cls, {"success": True, "tool": tool.name, "result": "ok"})

        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={"tool_name": tool.name, "params": {"query": "hello"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["tool"] == tool.name

    @patch("backend.services.mcp_governance.MCPClient")
    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invoke_tool_by_id_success(self, mock_client_cls, client, auth_headers, db_session):
        """Invoking by tool_id succeeds and returns result."""
        tool = _make_tool(db_session, tier=TIER_PRE_APPROVED, name=_unique("invoke_id"))
        _configure_mock_mcp(mock_client_cls, {"success": True, "tool": tool.name, "result": "done"})

        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={"tool_id": str(tool.id), "params": {"action": "ping"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["tool"] == tool.name

    def test_invoke_tool_missing_identifier(self, client, auth_headers):
        """Invoking without tool_id or tool_name returns 400."""
        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={"params": {"x": 1}},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_invoke_tool_not_found(self, client, auth_headers):
        """Invoking a non-existent tool returns 404."""
        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={"tool_name": "non_existent_tool_xyz_999"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invoke_revoked_tool_blocked(self, client, auth_headers, db_session, redis_client):
        """Invoking a revoked tool returns success=False with block message."""
        tool = _make_tool(db_session, tier=TIER_PRE_APPROVED, name=_unique("rev_inv"))
        redis_client.sadd("agentium:mcp:revoked", str(tool.id))

        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={"tool_id": str(tool.id), "params": {}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "revoked" in data["error"].lower()

    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invoke_forbidden_tool_blocked(self, client, auth_headers, db_session):
        """Invoking a forbidden tool returns success=False with constitutional block."""
        tool = _make_tool(db_session, tier=TIER_FORBIDDEN, name=_unique("forb_inv"))

        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={"tool_name": tool.name, "params": {}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "blocked" in data["error"].lower() or data["verdict"] == "block"

    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invoke_restricted_tool_requires_head_token(self, client, auth_headers, db_session):
        """Restricted tool without head approval token returns verdict=head_required."""
        tool = _make_tool(db_session, tier=TIER_RESTRICTED, name=_unique("restr_token"))

        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={
                "tool_name": tool.name,
                "agent_id": "00001",
                "agent_tier": "0xxxx",
                "has_head_approval_token": False,
                "params": {},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["verdict"] == "head_required"

    @patch("backend.services.mcp_governance.MCPClient")
    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invoke_restricted_tool_with_head_token_succeeds(self, mock_client_cls, client, auth_headers, db_session):
        """Restricted tool with head approval token and tier-0 agent executes successfully."""
        tool = _make_tool(db_session, tier=TIER_RESTRICTED, name=_unique("restr_ok"))
        _configure_mock_mcp(mock_client_cls, {"success": True, "tool": tool.name, "result": "allowed"})

        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={
                "tool_name": tool.name,
                "agent_id": "00001",
                "agent_tier": "0xxxx",
                "has_head_approval_token": True,
                "params": {},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("backend.services.mcp_governance.MCPClient")
    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invoke_tool_legacy_route_parity(self, mock_client_cls, client, auth_headers, db_session):
        """POST /api/v1/mcp-tools/invoke works identically to /api/v1/mcp/tools/invoke."""
        tool = _make_tool(db_session, tier=TIER_PRE_APPROVED, name=_unique("legacy_inv"))
        _configure_mock_mcp(mock_client_cls, {"success": True, "tool": tool.name, "result": "legacy ok"})

        resp = client.post(
            "/api/v1/mcp-tools/invoke",
            json={"tool_name": tool.name, "params": {}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 17.3.3: MCP tool configuration (server URL, auth) works
# ══════════════════════════════════════════════════════════════════════════════

class TestMCPToolConfigurationAPI:

    def test_propose_tool_with_server_url_and_auth(self, client, auth_headers):
        """Proposing a tool with server_url, auth_token, headers, env stores configuration."""
        name = _unique("cfg_prop")
        server_url = "https://mcp.external-api.com/v1"

        resp = client.post(
            "/api/v1/mcp/tools",
            json={
                "name": name,
                "description": "External server with auth token",
                "server_url": server_url,
                "tier": "pre_approved",
                "auth_token": "secret_bearer_token_123",
                "headers": {"X-Api-Key": "my-key-abc"},
                "env": {"MCP_DEBUG": "1"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == name
        assert data["server_url"] == server_url
        assert data["has_auth"] is True
        assert data["config"]["auth_token"] == "***"

    def test_get_tool_config_endpoint(self, client, auth_headers, db_session):
        """GET /api/v1/mcp/tools/{id}/config returns configuration metadata."""
        tool = _make_tool(
            db_session,
            name=_unique("cfg_get"),
            server_url="https://api.example.com",
            config={
                "auth_token": "sec_abc_456",
                "headers": {"Authorization": "Bearer sec_abc_456"},
                "env": {"API_MODE": "prod"},
            },
        )

        resp = client.get(f"/api/v1/mcp/tools/{tool.id}/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_id"] == str(tool.id)
        assert data["tool_name"] == tool.name
        assert data["server_url"] == "https://api.example.com"
        assert data["has_auth"] is True
        assert data["auth_type"] == "bearer"
        assert "API_MODE" in data["env_keys"]

    def test_update_tool_config_put(self, client, auth_headers, db_session):
        """PUT /api/v1/mcp/tools/{id}/config updates server_url and auth credentials."""
        tool = _make_tool(db_session, name=_unique("cfg_upd"), server_url="http://old-url.com")

        new_url = "https://new-url.service.com/mcp"
        resp = client.put(
            f"/api/v1/mcp/tools/{tool.id}/config",
            json={
                "server_url": new_url,
                "auth_token": "new_secret_jwt",
                "headers": {"X-Custom-Header": "custom_val"},
                "env": {"MCP_ENV": "stage"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["server_url"] == new_url
        assert data["has_auth"] is True

        # Verify via GET config endpoint
        cfg_resp = client.get(f"/api/v1/mcp/tools/{tool.id}/config", headers=auth_headers)
        assert cfg_resp.status_code == 200
        cfg_data = cfg_resp.json()
        assert cfg_data["server_url"] == new_url
        assert cfg_data["has_auth"] is True
        assert "MCP_ENV" in cfg_data["env_keys"]

    @patch("backend.services.mcp_governance.MCPClient")
    def test_test_connection_endpoint(self, mock_client_cls, client, auth_headers, db_session):
        """POST /api/v1/mcp/tools/{id}/test-connection checks reachability with configured auth."""
        tool = _make_tool(
            db_session,
            name=_unique("cfg_conn"),
            server_url="https://api.vendor.com",
            config={"auth_token": "test_token"},
        )
        mock_client_cls.side_effect = None
        _configure_mock_mcp(mock_client_cls)

        resp = client.post(
            f"/api/v1/mcp/tools/{tool.id}/test-connection",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert data["tool_id"] == str(tool.id)

    @patch("backend.services.mcp_governance.MCPClient")
    @patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize", new=AsyncMock(side_effect=RuntimeError("skip")))
    def test_invocation_forwards_configured_auth(self, mock_client_cls, client, auth_headers, db_session):
        """Tool execution passes configured server_url, auth_token, headers, and env to MCPClient."""
        tool = _make_tool(
            db_session,
            name=_unique("cfg_fwd"),
            server_url="https://secure.mcp.io",
            config={
                "auth_token": "jwt_token_999",
                "headers": {"X-Tenant": "tenant_1"},
                "env": {"EXEC_MODE": "safe"},
            },
        )
        _configure_mock_mcp(mock_client_cls, {"success": True, "tool": tool.name})

        resp = client.post(
            "/api/v1/mcp/tools/invoke",
            json={"tool_id": str(tool.id), "params": {}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert mock_client_cls.call_count >= 1
        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs.get("auth_token") == "jwt_token_999"
        assert call_kwargs.get("headers") == {"X-Tenant": "tenant_1"}
        assert call_kwargs.get("env") == {"EXEC_MODE": "safe"}
