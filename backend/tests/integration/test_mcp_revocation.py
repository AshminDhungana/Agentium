"""
MCP Sub-Second Revocation Integration Tests
==============================================
Phase 18.2 -- Feature Verification & Regression Testing

Verifies that revoking an MCP tool via POST /api/v1/mcp-tools/{id}/revoke
propagates to Redis in under one second and that subsequent invocations are
blocked without needing a PostgreSQL query.

Uses existing fixtures: client, redis_client, auth_headers, seeded_db.
"""

import pytest
import time


@pytest.mark.integration
class TestMCPSubSecondRevocation:
    """End-to-end tests for the Redis-based sub-second revocation path."""

    # ---- Helpers ----------------------------------------------------------------

    @staticmethod
    def _propose_tool(client, auth_headers, name: str, server_url: str) -> str:
        """Propose a new MCP tool and return its id."""
        r = client.post(
            "/api/v1/mcp-tools",
            json={
                "name": name,
                "description": f"Auto-generated test tool: {name}",
                "server_url": server_url,
                "tier": "pre_approved",
                "capabilities": [],
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, f"Propose failed: {r.text}"
        return r.json()["id"]

    @staticmethod
    def _approve_tool(client, auth_headers, tool_id: str):
        r = client.post(
            f"/api/v1/mcp-tools/{tool_id}/approve",
            json={"approved_by": "admin"},
            headers=auth_headers,
        )
        assert r.status_code == 200, f"Approve failed: {r.text}"

    @staticmethod
    def _revoke_tool(client, auth_headers, tool_id: str):
        r = client.post(
            f"/api/v1/mcp-tools/{tool_id}/revoke",
            json={"revoked_by": "admin", "reason": f"Revocation test for {tool_id}"},
            headers=auth_headers,
        )
        assert r.status_code == 200, f"Revoke failed: {r.text}"
        return r

    # ---- Task 1: Sub-Second Redis Propagation ----------------------------------

    def test_revoke_endpoint_adds_tool_to_redis_set(self, client, redis_client, auth_headers, seeded_db):
        """
        After POST /api/v1/mcp-tools/{id}/revoke, the tool_id must appear
        in the Redis SET 'agentium:mcp:revoked' within one second.
        """
        tool_id = self._propose_tool(client, auth_headers, "test-revoke-1", "http://localhost:9999/test-mcp")
        self._approve_tool(client, auth_headers, tool_id)

        start = time.monotonic()
        self._revoke_tool(client, auth_headers, tool_id)
        duration = time.monotonic() - start

        assert duration < 1.0, f"Revocation round-trip took {duration:.4f}s, must be <1s"
        assert redis_client.sismember("agentium:mcp:revoked", tool_id), (
            "Tool should have been added to Redis revocation SET instantly"
        )

    # ---- Task 2: Execution Blocked After Revocation ----------------------------

    def test_execution_blocked_after_revocation(self, client, redis_client, auth_headers, seeded_db):
        """
        Invoking a revoked tool via POST /api/v1/mcp-tools/{id}/execute must
        return success=False with a revocation/block message before any actual
        MCP client connection is attempted.
        """
        tool_id = self._propose_tool(client, auth_headers, "test-revoke-2", "http://localhost:9999/test-mcp-2")
        self._approve_tool(client, auth_headers, tool_id)
        self._revoke_tool(client, auth_headers, tool_id)

        # Verify it is in Redis
        assert redis_client.sismember("agentium:mcp:revoked", tool_id)

        r = client.post(
            f"/api/v1/mcp-tools/{tool_id}/execute",
            json={
                "agent_id": "admin",
                "agent_tier": "3xxxx",
                "params": {},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        error = data.get("error", "").lower()
        assert "revoked" in error or "blocked" in error, (
            f"Expected blocked/revoked error, got: {data}"
        )

    # ---- Task 3: Re-Approval Clears Redis Revocation ---------------------------

    def test_re_approval_clears_redis_revocation(self, client, redis_client, auth_headers, seeded_db):
        """
        When approve_mcp_server is called it internally calls
        mcp_stats_service.remove_from_revoked, so the tool is removed
        from the Redis SET.  We seed the SET directly before approval,
        prove the tool is present, approve, then assert it is gone.
        """
        tool_id = self._propose_tool(client, auth_headers, "test-revoke-3", "http://localhost:9999/test-mcp-3")

        # Seed Redis revocation SET directly (simulating a prior revocation)
        redis_client.sadd("agentium:mcp:revoked", tool_id)
        assert redis_client.sismember("agentium:mcp:revoked", tool_id)

        # Normal approval should clean up the stale Redis entry
        self._approve_tool(client, auth_headers, tool_id)

        assert not redis_client.sismember("agentium:mcp:revoked", tool_id), (
            "Approval did not remove the tool from the Redis revocation SET"
        )

    # ---- Task 4: Revoked Tools Endpoint -----------------------------------------

    def test_revoked_tools_endpoint(self, client, redis_client, auth_headers, seeded_db):
        """
        GET /api/v1/mcp-tools/revoked must list all tool IDs currently in the
        Redis revocation SET.
        """
        tool_id = self._propose_tool(client, auth_headers, "test-revoke-4", "http://localhost:9999/test-mcp-4")
        self._approve_tool(client, auth_headers, tool_id)
        self._revoke_tool(client, auth_headers, tool_id)

        r = client.get("/api/v1/mcp-tools/revoked", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert tool_id in data["revoked_tool_ids"], (
            f"Expected {tool_id} in revoked list, got {data}"
        )
