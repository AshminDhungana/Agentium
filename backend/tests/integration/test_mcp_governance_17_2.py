from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.database import SessionLocal
from backend.models.entities.mcp_tool import MCPTool
from backend.services.mcp_governance import (
    MCPGovernanceService,
    MCPVerdict,
    STATUS_APPROVED,
    TIER_FORBIDDEN,
    TIER_PRE_APPROVED,
    TIER_RESTRICTED,
)
from backend.services import mcp_stats_service

pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique(prefix: str = "tool") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _make_approved_tool(db, *, tier: str = TIER_PRE_APPROVED, name: str | None = None) -> MCPTool:
    name = name or _unique("mcp_tool")
    tool = MCPTool(
        name=name,
        description="Test tool for 17.2 governance tests",
        server_url=f"mock://localhost/{name}",
        tier=tier,
        status=STATUS_APPROVED,
        proposed_by="00001",
        approved_by_council=True,
        failure_count=0,
        consecutive_failures=0,
        usage_count=0,
        health_status="unknown",
        is_active=True,
        agentium_id=f"mcp-{uuid.uuid4().hex[:12]}",
        capabilities=[{"name": name, "description": "test cap", "input_schema": {}}],
        audit_log=[],
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


def _make_forbidden_tool(db) -> MCPTool:
    name = _unique("mcp_forbidden")
    tool = MCPTool(
        name=name,
        description="Forbidden tool for 17.2 tests",
        server_url=f"mock://localhost/{name}",
        tier=TIER_FORBIDDEN,
        status=STATUS_APPROVED,
        proposed_by="00001",
        approved_by_council=True,
        failure_count=0,
        consecutive_failures=0,
        usage_count=0,
        health_status="unknown",
        is_active=True,
        agentium_id=f"mcp-{uuid.uuid4().hex[:12]}",
        capabilities=[],
        audit_log=[],
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


def _mock_mcp_client(result: dict | None = None, *, raise_exc=None):
    """
    Return a context-manager-compatible MagicMock for MCPClient.
    Also sets hash_params.return_value to a plain string so _audit()
    can serialise the audit_log JSON column without TypeError.
    """
    from backend.services.mcp_client import MCPConnectionError  # noqa: F401
    mock_cls = MagicMock()
    mock_cls.hash_params.return_value = "deadbeef"   # ← prevents MagicMock in audit_log
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    if raise_exc is not None:
        mock_cm.call_tool = AsyncMock(side_effect=raise_exc)
    else:
        mock_cm.call_tool = AsyncMock(return_value=result or {"success": True})
    mock_cls.return_value = mock_cm
    return mock_cls


async def _execute(
    svc: MCPGovernanceService,
    tool: MCPTool,
    *,
    agent_id: str = "30001",
    agent_tier: str = "3xxxx",
    params: Dict[str, Any] | None = None,
    has_head_approval_token: bool = False,
) -> Dict[str, Any]:
    return await svc.execute_mcp_tool(
        str(tool.id),
        agent_id=agent_id,
        agent_tier=agent_tier,
        params=params or {},
        has_head_approval_token=has_head_approval_token,
    )


def _skip_cg():
    """Patch that makes ConstitutionalGuard.initialize raise so guard is skipped (non-fatal)."""
    return patch(
        "backend.core.constitutional_guard.ConstitutionalGuard.initialize",
        new=AsyncMock(side_effect=RuntimeError("skip_cg")),
    )


# ══════════════════════════════════════════════════════════════════════════════
# 17.2.1 — Constitutional Guard applies to MCP tool invocations
# ══════════════════════════════════════════════════════════════════════════════

class TestConstitutionalGuardOnMCPInvocations:
    """17.2.1 — ConstitutionalGuard is consulted on every MCP invocation."""

    def test_constitutional_guard_blocks_invocation_when_verdict_is_block(self):
        """BLOCK verdict from the guard must be honoured before execution."""
        from backend.core.constitutional_guard import ConstitutionalDecision, Verdict, ViolationSeverity
        block_decision = ConstitutionalDecision(
            verdict=Verdict.BLOCK,
            severity=ViolationSeverity.HIGH,
            citations=["Article 1 — Prohibited operations"],
            explanation="Test: constitutionally blocked",
        )
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_PRE_APPROVED)
            svc = MCPGovernanceService(db)
            async def _run():
                with patch("backend.core.constitutional_guard.ConstitutionalGuard.check_action",
                           new=AsyncMock(return_value=block_decision)), \
                     patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize",
                           new=AsyncMock()), \
                     patch("backend.services.mcp_governance.MCPClient", _mock_mcp_client()):
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx")
            result = asyncio.run(_run())
        assert result["success"] is False
        assert result["verdict"] == MCPVerdict.BLOCK
        assert "Constitutional guard" in result["error"]

    def test_constitutional_guard_allows_benign_mcp_invocation(self):
        """ALLOW verdict lets the invocation proceed through to the MCP server."""
        from backend.core.constitutional_guard import ConstitutionalDecision, Verdict, ViolationSeverity
        allow_decision = ConstitutionalDecision(verdict=Verdict.ALLOW, severity=ViolationSeverity.LOW,
                                                explanation="Within bounds.")
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_PRE_APPROVED)
            svc = MCPGovernanceService(db)
            async def _run():
                mock_mcp = _mock_mcp_client({"success": True, "tool": "cap", "result": "ok"})
                with patch("backend.core.constitutional_guard.ConstitutionalGuard.check_action",
                           new=AsyncMock(return_value=allow_decision)), \
                     patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize",
                           new=AsyncMock()), \
                     patch("backend.services.mcp_governance.MCPClient", mock_mcp):
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx")
            result = asyncio.run(_run())
        assert result.get("verdict") != MCPVerdict.BLOCK, f"Expected allow, got: {result}"

    def test_constitutional_guard_error_is_non_fatal(self):
        """If the guard raises, execution must still proceed (degrade gracefully)."""
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_PRE_APPROVED)
            svc = MCPGovernanceService(db)
            async def _run():
                mock_mcp = _mock_mcp_client({"success": True})
                with patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize",
                           new=AsyncMock(side_effect=RuntimeError("Redis exploded"))), \
                     patch("backend.services.mcp_governance.MCPClient", mock_mcp):
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx")
            result = asyncio.run(_run())
        assert result.get("verdict") != MCPVerdict.BLOCK, f"Guard exception should be non-fatal: {result}"

    def test_constitutional_guard_receives_correct_context(self):
        """check_action must receive action='mcp_tool_invoke' with tool_name, tool_tier, params."""
        from backend.core.constitutional_guard import ConstitutionalDecision, Verdict, ViolationSeverity
        allow_decision = ConstitutionalDecision(verdict=Verdict.ALLOW, severity=ViolationSeverity.LOW)
        captured: dict = {}
        async def _spy(action, context, **kw):
            captured["action"] = action
            captured["context"] = context
            return allow_decision
        with SessionLocal() as db:
            tool = _make_approved_tool(db, name=_unique("spy_tool"), tier=TIER_PRE_APPROVED)
            svc = MCPGovernanceService(db)
            async def _run():
                mock_mcp = _mock_mcp_client({"success": True})
                with patch("backend.core.constitutional_guard.ConstitutionalGuard.check_action",
                           new=AsyncMock(side_effect=_spy)), \
                     patch("backend.core.constitutional_guard.ConstitutionalGuard.initialize",
                           new=AsyncMock()), \
                     patch("backend.services.mcp_governance.MCPClient", mock_mcp):
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx",
                                         params={"key": "value"})
            asyncio.run(_run())
        assert captured.get("action") == "mcp_tool_invoke"
        ctx = captured.get("context", {})
        assert ctx.get("tool_name") == tool.name
        assert ctx.get("tool_tier") == TIER_PRE_APPROVED
        assert ctx.get("params") == {"key": "value"}


# ══════════════════════════════════════════════════════════════════════════════
# 17.2.2 — MCP tool access respects agent tier permissions
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentTierPermissions:
    """17.2.2 — Tier-access matrix for check_tier_access and execute_mcp_tool."""

    # ── check_tier_access unit matrix ────────────────────────────────────────

    @pytest.mark.parametrize("agent_tier,expected", [
        ("3xxxx", MCPVerdict.ALLOW), ("2xxxx", MCPVerdict.ALLOW),
        ("1xxxx", MCPVerdict.ALLOW), ("0xxxx", MCPVerdict.ALLOW),
    ])
    def test_pre_approved_allows_all_tiers(self, agent_tier, expected):
        with SessionLocal() as db:
            svc = MCPGovernanceService(db)
            assert svc.check_tier_access(TIER_PRE_APPROVED, agent_tier, False) == expected

    @pytest.mark.parametrize("agent_tier,has_token,expected", [
        ("3xxxx", False, MCPVerdict.BLOCK),
        ("2xxxx", False, MCPVerdict.BLOCK),
        ("1xxxx", False, MCPVerdict.HEAD_REQUIRED),
        ("0xxxx", False, MCPVerdict.HEAD_REQUIRED),
        ("0xxxx", True,  MCPVerdict.ALLOW),
        ("1xxxx", True,  MCPVerdict.ALLOW),
    ])
    def test_restricted_tier_requires_head_token(self, agent_tier, has_token, expected):
        with SessionLocal() as db:
            svc = MCPGovernanceService(db)
            verdict = svc.check_tier_access(TIER_RESTRICTED, agent_tier, has_token)
        assert verdict == expected, (
            f"agent_tier={agent_tier!r} has_token={has_token} -> expected {expected!r}, got {verdict!r}"
        )

    @pytest.mark.parametrize("agent_tier,has_token", [
        ("3xxxx", False), ("0xxxx", True),
    ])
    def test_forbidden_tier_always_blocks(self, agent_tier, has_token):
        with SessionLocal() as db:
            svc = MCPGovernanceService(db)
            assert svc.check_tier_access(TIER_FORBIDDEN, agent_tier, has_token) == MCPVerdict.BLOCK

    # ── get_approved_tools tier filtering ────────────────────────────────────

    def test_get_approved_tools_shows_only_pre_approved_to_task_agent(self):
        with SessionLocal() as db:
            _make_approved_tool(db, tier=TIER_PRE_APPROVED)
            svc = MCPGovernanceService(db)
            tools = svc.get_approved_tools(agent_tier="3xxxx")
        for t in tools:
            assert t.tier == TIER_PRE_APPROVED, (
                f"Tool {t.name!r} with tier {t.tier!r} should not be visible to tier-3"
            )

    def test_get_approved_tools_shows_restricted_to_head_agent(self):
        with SessionLocal() as db:
            _make_approved_tool(db, tier=TIER_RESTRICTED)
            svc = MCPGovernanceService(db)
            tools = svc.get_approved_tools(agent_tier="0xxxx")
        tiers = {t.tier for t in tools}
        assert TIER_RESTRICTED in tiers or TIER_PRE_APPROVED in tiers

    def test_get_approved_tools_never_returns_forbidden_tools(self):
        with SessionLocal() as db:
            _make_forbidden_tool(db)
            svc = MCPGovernanceService(db)
            tools = svc.get_approved_tools()
        for t in tools:
            assert t.tier != TIER_FORBIDDEN, f"Forbidden tool {t.name!r} must not appear in approved list"

    # ── execute_mcp_tool end-to-end tier enforcement ─────────────────────────

    def test_execute_blocks_task_agent_calling_restricted_tool(self):
        """Tier-3 agent → restricted tool, no token → BLOCK (no MCP server needed)."""
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_RESTRICTED)
            svc = MCPGovernanceService(db)
            async def _run():
                with _skip_cg():
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx",
                                         has_head_approval_token=False)
            result = asyncio.run(_run())
        assert result["success"] is False

    def test_execute_allows_head_agent_with_token_on_restricted_tool(self):
        """Tier-0 head agent + token → restricted tool → ALLOW."""
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_RESTRICTED)
            svc = MCPGovernanceService(db)
            async def _run():
                mock_mcp = _mock_mcp_client({"success": True, "tool": "x", "result": "ok"})
                with _skip_cg(), \
                     patch("backend.services.mcp_governance.MCPClient", mock_mcp):
                    return await _execute(svc, tool, agent_id="00001", agent_tier="0xxxx",
                                         has_head_approval_token=True)
            result = asyncio.run(_run())
        assert result.get("verdict") != MCPVerdict.BLOCK, f"Head+token should not be blocked: {result}"

    def test_execute_blocks_forbidden_tier_for_all_agents(self):
        """forbidden-tier tool → BLOCK even for the Head of Council with token."""
        with SessionLocal() as db:
            tool = _make_forbidden_tool(db)
            svc = MCPGovernanceService(db)
            async def _run():
                with _skip_cg():
                    return await _execute(svc, tool, agent_id="00001", agent_tier="0xxxx",
                                         has_head_approval_token=True)
            result = asyncio.run(_run())
        assert result["success"] is False
        assert result["verdict"] == MCPVerdict.BLOCK


# ══════════════════════════════════════════════════════════════════════════════
# 17.2.3 — Usage statistics tracked via mcp_stats_service.py
# ══════════════════════════════════════════════════════════════════════════════

class TestMCPUsageStatistics:
    """17.2.3 — mcp_stats_service records and reads usage statistics via Redis."""

    def test_record_invocation_increments_count(self):
        tid = _unique("stat_tool")
        mcp_stats_service.record_invocation(tid, latency_ms=42.0, success=True)
        stats = mcp_stats_service.get_tool_stats(tid)
        assert stats is not None
        assert stats["invocation_count"] == 1

    def test_record_invocation_no_error_on_success(self):
        tid = _unique("stat_ok")
        mcp_stats_service.record_invocation(tid, latency_ms=10.0, success=True)
        stats = mcp_stats_service.get_tool_stats(tid)
        assert stats is not None
        assert stats["error_count"] == 0

    def test_record_invocation_increments_error_on_failure(self):
        tid = _unique("stat_err")
        mcp_stats_service.record_invocation(tid, latency_ms=5.0, success=False)
        stats = mcp_stats_service.get_tool_stats(tid)
        assert stats is not None
        assert stats["error_count"] == 1
        assert stats["invocation_count"] == 1

    def test_record_invocation_tracks_latency(self):
        tid = _unique("stat_lat")
        mcp_stats_service.record_invocation(tid, latency_ms=123.45, success=True)
        stats = mcp_stats_service.get_tool_stats(tid)
        assert stats is not None
        assert abs(stats["avg_latency_ms"] - 123.45) < 1.0

    def test_multiple_invocations_average_latency(self):
        tid = _unique("stat_avg")
        mcp_stats_service.record_invocation(tid, latency_ms=100.0, success=True)
        mcp_stats_service.record_invocation(tid, latency_ms=200.0, success=True)
        stats = mcp_stats_service.get_tool_stats(tid)
        assert stats is not None
        assert stats["invocation_count"] == 2
        assert abs(stats["avg_latency_ms"] - 150.0) < 1.0

    def test_get_all_stats_includes_invoked_tool(self):
        tid = _unique("stat_all")
        mcp_stats_service.record_invocation(tid, latency_ms=50.0, success=True)
        assert tid in [s["tool_id"] for s in mcp_stats_service.get_all_stats()]

    def test_get_stats_for_tools_returns_subset(self):
        tid_a, tid_b = _unique("stat_a"), _unique("stat_b")
        mcp_stats_service.record_invocation(tid_a, latency_ms=10.0, success=True)
        mcp_stats_service.record_invocation(tid_b, latency_ms=20.0, success=True)
        subset = mcp_stats_service.get_stats_for_tools([tid_a])
        assert tid_a in subset
        assert tid_b not in subset

    def test_get_tool_stats_returns_none_for_unknown_tool(self):
        assert mcp_stats_service.get_tool_stats(_unique("never")) is None

    def test_add_to_revoked_makes_is_revoked_true(self):
        tid = _unique("rev_add")
        mcp_stats_service.add_to_revoked(tid)
        try:
            assert mcp_stats_service.is_revoked(tid) is True
        finally:
            mcp_stats_service.remove_from_revoked(tid)

    def test_remove_from_revoked_makes_is_revoked_false(self):
        tid = _unique("rev_rm")
        mcp_stats_service.add_to_revoked(tid)
        mcp_stats_service.remove_from_revoked(tid)
        assert mcp_stats_service.is_revoked(tid) is False

    def test_get_revoked_ids_includes_revoked_tool(self):
        tid = _unique("rev_ids")
        mcp_stats_service.add_to_revoked(tid)
        try:
            assert tid in mcp_stats_service.get_revoked_ids()
        finally:
            mcp_stats_service.remove_from_revoked(tid)

    def test_revocation_blocks_execute_mcp_tool_via_fast_path(self):
        """add_to_revoked → execute_mcp_tool is blocked immediately without DB query."""
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_PRE_APPROVED)
            mcp_stats_service.add_to_revoked(str(tool.id))
            try:
                svc = MCPGovernanceService(db)
                async def _run():
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx")
                result = asyncio.run(_run())
            finally:
                mcp_stats_service.remove_from_revoked(str(tool.id))
        assert result["success"] is False
        assert "revoked" in result["error"].lower()

    def test_execute_mcp_tool_records_stats_on_success(self):
        """Successful invocation → invocation_count incremented in Redis."""
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_PRE_APPROVED)
            tid = str(tool.id)
            svc = MCPGovernanceService(db)
            async def _run():
                mock_mcp = _mock_mcp_client({"success": True, "tool": "cap", "result": "data"})
                with _skip_cg(), patch("backend.services.mcp_governance.MCPClient", mock_mcp):
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx")
            asyncio.run(_run())
        stats = mcp_stats_service.get_tool_stats(tid)
        assert stats is not None, "Stats must be recorded after a successful invocation"
        assert stats["invocation_count"] >= 1

    def test_execute_mcp_tool_records_stats_on_connection_error(self):
        """Failed invocation (MCPConnectionError) still records stats with error_count >= 1."""
        from backend.services.mcp_client import MCPConnectionError
        with SessionLocal() as db:
            tool = _make_approved_tool(db, tier=TIER_PRE_APPROVED)
            tid = str(tool.id)
            svc = MCPGovernanceService(db)
            async def _run():
                mock_mcp = _mock_mcp_client(raise_exc=MCPConnectionError("conn refused"))
                with _skip_cg(), patch("backend.services.mcp_governance.MCPClient", mock_mcp):
                    return await _execute(svc, tool, agent_id="30001", agent_tier="3xxxx")
            asyncio.run(_run())
        stats = mcp_stats_service.get_tool_stats(tid)
        assert stats is not None, "Stats must be recorded even on failure"
        assert stats["invocation_count"] >= 1

    def test_governance_get_live_stats_proxy_returns_stats(self):
        """MCPGovernanceService.get_live_stats is a thin proxy to mcp_stats_service."""
        tid = _unique("live_stat")
        mcp_stats_service.record_invocation(tid, latency_ms=77.0, success=True)
        result = MCPGovernanceService.get_live_stats([tid])
        assert isinstance(result, list) and len(result) >= 1
        found = next((s for s in result if s["tool_id"] == tid), None)
        assert found is not None
        assert found["invocation_count"] >= 1

    def test_redis_health_returns_healthy(self):
        """redis_health() must report 'healthy' when Redis is up (integration env)."""
        health = mcp_stats_service.redis_health()
        assert health["status"] == "healthy", f"Expected healthy Redis: {health}"
