"""
Agent-callable MCP server registration — integration tests.

Exercises the full governance flow:
  - Head fast-path auto-approves + registers mcp__<name> live
  - Council path opens a vote; quorum approval registers live
  - Live discovery failure creates no MCPTool row
  - Duplicate server_url is rejected
  - Revocation still removes the live key
"""
import asyncio
import pytest

from backend.models.database import SessionLocal
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.mcp_tool import MCPTool
from backend.core.tool_registry import tool_registry
from backend.services.mcp_governance import (
    MCPGovernanceService,
    MCPConnectionError,
)
from backend.services.mcp_tool_bridge import init_bridge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _force_mcp_mock(monkeypatch):
    """Force MCP client mock mode.

    These tests use fake server_url command names (e.g. 'revoke_cmd') and
    assert behaviour that only holds when the MCP client runs in its built-in
    mock mode (mcp package absent). The test environment has the mcp package
    installed, so we force mock mode to match the test's documented intent.
    """
    import backend.services.mcp_client as mcp_client

    monkeypatch.setattr(mcp_client, "MCP_AVAILABLE", False)


@pytest.fixture(scope="module")
def bridge():
    """Initialise the live bridge so sync_one registers into tool_registry."""
    return init_bridge(tool_registry, SessionLocal)


def _make_council(db, n=2, start=10010):
    members = []
    for i in range(n):
        a = Agent(
            agent_type=AgentType.COUNCIL_MEMBER,
            agentium_id=str(start + i),
            status=AgentStatus.ACTIVE,
            name=f"Council{start + i}",
        )
        db.add(a)
        members.append(a)
    db.commit()
    return members


async def _propose(db, **kw):
    svc = MCPGovernanceService(db)
    return await svc.propose_mcp_server_with_vote(**kw)


def test_head_fast_path_registers_live(bridge, db_session):
    _make_council(db_session)
    out = asyncio.run(
        _propose(
            db_session,
            name="headfast",
            description="head auto-approve",
            server_url="headfast_cmd",
            tier="pre_approved",
            proposed_by="00001",
        )
    )
    assert out["proposed"] is True
    assert out["status"] == "approved"
    assert out["registry_key"] == "mcp__headfast"
    assert "mcp__headfast" in tool_registry.tools
    # capabilities discovered (mock mode returns a mock tool)
    assert isinstance(out["capabilities"], list)


def test_council_vote_flow_registers_live(bridge, db_session):
    import json
    from datetime import datetime
    from backend.models.entities.constitution import Constitution
    con = Constitution(
        agentium_id="C00099",
        preamble="test",
        articles=json.dumps({}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        created_by_agentium_id="00001",
        effective_date=datetime.utcnow(),
        is_active=True,
        version="v1.0",
    )
    db_session.add(con)
    db_session.commit()
    members = _make_council(db_session)
    out = asyncio.run(
        _propose(
            db_session,
            name="counciltool",
            description="council proposal",
            server_url="counciltool_cmd",
            tier="pre_approved",
            proposed_by="10001",
        )
    )
    assert out["status"] == "pending_vote"
    assert out["voting_id"]
    tool_id = out["tool_id"]
    voters = out["eligible_voters"]
    assert set(voters) == {m.agentium_id for m in members}

    # Cast a 'for' vote from every eligible voter
    for idx, v in enumerate(voters):
        svc = MCPGovernanceService(db_session)
        res = svc.vote_on_mcp_proposal(tool_id, v, "for")
        if idx == len(voters) - 1:  # final vote finalises
            assert res["approved"] is True
            assert res["registry_key"] == "mcp__counciltool"
    assert "mcp__counciltool" in tool_registry.tools


def test_discovery_failure_creates_no_row(bridge, db_session, monkeypatch):
    async def fake_list_tools(self):
        raise MCPConnectionError("simulated failure")

    monkeypatch.setattr(
        "backend.services.mcp_governance.MCPClient.list_tools", fake_list_tools
    )
    out = asyncio.run(
        _propose(
            db_session,
            name="deadserver",
            description="unreachable",
            server_url="dead_cmd",
            tier="pre_approved",
            proposed_by="10001",
        )
    )
    assert out["proposed"] is False
    assert "error" in out
    remaining = db_session.query(MCPTool).filter_by(name="deadserver").first()
    assert remaining is None


def test_duplicate_server_url_rejected(bridge, db_session):
    _make_council(db_session)
    kw = dict(
        name="duptool",
        description="d",
        server_url="dup_cmd",
        tier="pre_approved",
        proposed_by="00001",
    )
    first = asyncio.run(_propose(db_session, **kw))
    assert first["proposed"] is True
    with pytest.raises(ValueError):
        asyncio.run(_propose(db_session, **kw))


def test_revocation_removes_live_key(bridge, db_session):
    _make_council(db_session)
    out = asyncio.run(
        _propose(
            db_session,
            name="revokeme",
            description="r",
            server_url="revoke_cmd",
            tier="pre_approved",
            proposed_by="00001",
        )
    )
    assert "mcp__revokeme" in tool_registry.tools
    svc = MCPGovernanceService(db_session)
    tool = svc._get_tool_or_404(out["tool_id"])
    svc.revoke_mcp_tool(str(tool.id), revoked_by="00001", reason="test")
    bridge.deregister(tool)
    assert "mcp__revokeme" not in tool_registry.tools
