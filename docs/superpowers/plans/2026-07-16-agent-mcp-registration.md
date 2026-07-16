# Agent-Callable MCP Server Registration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Head or Council agent register an MCP server by calling a built-in tool that proposes it, auto-discovers its live capabilities, triggers a Council vote, and (on quorum) approves + syncs it into the live `ToolRegistry`.

**Architecture:** Two new `MCPGovernanceService` methods (`propose_mcp_server_with_vote`, `vote_on_mcp_proposal`) reuse the existing `MCPClient` discovery, `MCPTool` entity, `AmendmentVoting` governance, and `MCPToolBridge` sync. Two new built-in agent tools (`add_mcp_server`, `vote_on_mcp_server`) are registered in `tool_registry` and are invoked through the existing `ToolCreationService.execute_tool` path (which injects the caller's `agent_id`).

**Tech Stack:** Python 3.11+, FastAPI/SQLAlchemy 2, Pydantic, pytest + `@pytest.mark.integration` (fixtures: `db_session`, `client`, `redis_client` from `backend/tests/integration/conftest.py`), Alembic.

## Global Constraints

- Authorized tiers for the new tools: **`["0xxxx","1xxxx"]`** (Head + Council only).
- Capabilities are **auto-discovered live** via `MCPClient.list_tools()` at proposal time; on connection failure **no `MCPTool` row is created**.
- Head (`proposed_by` starts with `"0"`) takes the **fast-path**: propose → auto-approve → `bridge.sync_one` in one call.
- Council path creates an `AmendmentVoting` (`amendment_id` = active constitution id, `eligible_voters` = active council, `required_votes = len(eligible)`, `supermajority_threshold = 66`) opened via `start_voting()`; finalize via `conclude()` only once **all eligible voters have cast**.
- All new DB writes go through `MCPTool` / `AmendmentVoting` with full `audit_log` on the MCPTool — no new privilege subsystem.
- `MCPTool` gains one nullable column `voting_id` (String(64)) with a matching Alembic migration (`down_revision = "008_modelusage_agentium_id"`).
- Every task ends with a commit. Run backend tests from `backend/` with `pytest`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/models/entities/mcp_tool.py` | Add `voting_id` column + surface in `to_dict()` |
| `backend/alembic/versions/009_mcp_voting_id.py` | Migration adding `voting_id` to `mcp_tools` |
| `backend/services/mcp_governance.py` | Add `propose_mcp_server_with_vote` (async) and `vote_on_mcp_proposal` (sync) + `_lazy_bridge()` helper |
| `backend/tools/mcp_agent_tools.py` | New module: `add_mcp_server` (async) and `vote_on_mcp_server` (sync) wrappers |
| `backend/core/tool_registry.py` | Import the two wrappers and register them in `_initialize_tools()` |
| `backend/tests/integration/test_agent_mcp_registration.py` | Service + registry integration tests (Head fast-path, Council vote, discovery failure, duplicate, revocation) |

---

### Task 1: Add `voting_id` column to `MCPTool` + migration

**Files:**
- Modify: `backend/models/entities/mcp_tool.py` (after the `proposed_at` field, ~line 110)
- Create: `backend/alembic/versions/009_mcp_voting_id.py`
- Test: covered by Task 5 (DB migration applied by test fixtures)

**Interfaces:**
- Produces: `MCPTool.voting_id` (String(64), nullable) — read/written by Tasks 2–3.

- [ ] **Step 1: Add the column to the model**

In `backend/models/entities/mcp_tool.py`, add the field after `proposed_at`:

```python
    # ── Proposal metadata ───────────────────────────────────────────────────────
    proposed_by: Optional[str] = Column(String(64), nullable=True)  # agentium_id
    proposed_at: Optional[datetime] = Column(DateTime, nullable=True)
    # Link to the AmendmentVoting that governs this proposal's approval
    voting_id: Optional[str] = Column(String(64), nullable=True)
```

Also add `"voting_id": self.voting_id,` to the `to_dict()` return dict.

- [ ] **Step 2: Create the Alembic migration**

Create `backend/alembic/versions/009_mcp_voting_id.py`:

```python
"""add voting_id to mcp_tools

Revision ID: 009_mcp_voting_id
Revises: 008_modelusage_agentium_id
"""
from alembic import op
import sqlalchemy as sa

revision = "009_mcp_voting_id"
down_revision = "008_modelusage_agentium_id"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mcp_tools",
        sa.Column("voting_id", sa.String(64), nullable=True),
    )


def downgrade():
    op.drop_column("mcp_tools", "voting_id")
```

- [ ] **Step 3: Verify migration applies**

Run: `cd backend && alembic upgrade head`
Expected: output shows `009_mcp_voting_id` applied with no error.

- [ ] **Step 4: Commit**

```bash
git add backend/models/entities/mcp_tool.py backend/alembic/versions/009_mcp_voting_id.py
git commit -m "feat(mcp): add voting_id column to MCPTool for proposal linkage"
```

---

### Task 2: Implement `propose_mcp_server_with_vote` (service)

**Files:**
- Modify: `backend/services/mcp_governance.py` (add method to `MCPGovernanceService`, plus imports)
- Test: `backend/tests/integration/test_agent_mcp_registration.py` (Task 5)

**Interfaces:**
- Consumes: existing `MCPClient`, `MCPTool`, `MCPConnectionError`, `TIER_*`/`STATUS_*` constants, `approve_mcp_server`, `_get_tool_or_404`, `_lazy_bridge` (added here).
- Produces:
  - `async def propose_mcp_server_with_vote(self, *, name, description, server_url, tier, proposed_by, constitutional_article=None) -> Dict[str, Any]`
  - Returns (Head): `{proposed:True, status:"approved", tool_id, registry_key:"mcp__<name>", capabilities:[...]}`
  - Returns (Council): `{proposed:True, status:"pending_vote", tool_id, voting_id, eligible_voters:[...], capabilities:[...]}`
  - Returns (connect fail): `{proposed:False, error:"..."}` — **no DB row created**

- [ ] **Step 1: Add imports at top of `mcp_governance.py`**

After the existing `from backend.services.mcp_client import MCPClient, MCPConnectionError` add:

```python
from backend.models.entities.agents import Agent
from backend.models.entities.constitution import Constitution
from backend.models.entities.voting import AmendmentVoting, AmendmentStatus
```

- [ ] **Step 2: Add `_lazy_bridge` helper + the new method**

Paste this inside the `MCPGovernanceService` class (e.g. right after `propose_mcp_server`):

```python
    def _lazy_bridge(self):
        """Return the global MCPToolBridge singleton, or None if not initialised."""
        try:
            from backend.services.mcp_tool_bridge import mcp_bridge
            return mcp_bridge
        except ImportError:
            return None

    async def propose_mcp_server_with_vote(
        self,
        *,
        name: str,
        description: str,
        server_url: str,
        tier: str,
        proposed_by: str,
        constitutional_article: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Agent-callable MCP server proposal with live capability discovery
        and an automatic Council vote (mirrors tool_creation_service).

        - Head (proposed_by starts with '0'): propose -> auto-approve -> sync.
        - Council: propose (pending) -> open AmendmentVoting -> return voting_id.
        - Connection failure: return error, create NO MCPTool row.
        """
        if tier not in (TIER_PRE_APPROVED, TIER_RESTRICTED, TIER_FORBIDDEN):
            raise ValueError(
                f"Invalid tier '{tier}'. Must be pre_approved, restricted, or forbidden."
            )

        existing = self.db.query(MCPTool).filter_by(server_url=server_url).first()
        if existing:
            raise ValueError(
                f"MCP server '{server_url}' is already registered as '{existing.name}'."
            )

        # ── Live capability discovery ──────────────────────────────────────────
        try:
            async with MCPClient(server_url) as client:
                discovered = await client.list_tools()
        except MCPConnectionError as exc:
            logger.warning(
                "[MCPGovernance] Discovery failed for %s: %s", server_url, exc
            )
            return {
                "proposed": False,
                "error": f"Could not connect to MCP server: {exc}",
            }

        capabilities = [
            t.get("name")
            for t in discovered
            if isinstance(t, dict) and t.get("name")
        ]

        tool = MCPTool(
            name=name,
            description=description,
            server_url=server_url,
            tier=tier,
            constitutional_article=constitutional_article,
            capabilities=capabilities,
            status=STATUS_PENDING,
            proposed_by=proposed_by,
            proposed_at=datetime.utcnow(),
            audit_log=[],
            approved_by_council=False,
            failure_count=0,
            consecutive_failures=0,
            usage_count=0,
            health_status="unknown",
            is_active=True,
            agentium_id=f"mcp-{uuid.uuid4().hex[:12]}",
            voting_id=None,
        )
        self.db.add(tool)
        self.db.commit()
        self.db.refresh(tool)

        # ── Head fast-path: auto-approve + sync immediately ─────────────────────
        if proposed_by.startswith("0"):
            approved = self.approve_mcp_server(
                str(tool.id), approved_by=proposed_by, vote_id=None
            )
            bridge = self._lazy_bridge()
            if bridge:
                bridge.sync_one(approved)
            return {
                "proposed": True,
                "status": STATUS_APPROVED,
                "tool_id": str(tool.id),
                "registry_key": f"mcp__{tool.name}",
                "capabilities": capabilities,
            }

        # ── Council path: open a governance vote ────────────────────────────────
        constitution = (
            self.db.query(Constitution).filter_by(is_active=True).first()
        )
        if not constitution:
            raise ValueError("No active constitution found; cannot open a Council vote.")

        council = (
            self.db.query(Agent)
            .filter(Agent.agent_type == "council_member", Agent.status == "active")
            .all()
        )
        eligible = [c.agentium_id for c in council]

        voting = AmendmentVoting(
            amendment_id=constitution.id,
            eligible_voters=eligible,
            required_votes=max(1, len(eligible)),
            supermajority_threshold=66,
            status=AmendmentStatus.PROPOSED,
            proposed_by_agentium_id=proposed_by,
            proposed_changes=f"MCP Server: {name}",
            rationale=description,
        )
        self.db.add(voting)
        self.db.commit()
        self.db.refresh(voting)
        voting.start_voting()  # PROPOSED -> VOTING so votes can be cast

        tool.voting_id = str(voting.id)
        self.db.commit()

        logger.info(
            "[MCPGovernance] MCP proposal %s opened Council vote %s",
            tool.name, voting.id,
        )
        return {
            "proposed": True,
            "status": "pending_vote",
            "tool_id": str(tool.id),
            "voting_id": str(voting.id),
            "eligible_voters": eligible,
            "capabilities": capabilities,
        }
```

- [ ] **Step 3: Sanity import check**

Run: `cd backend && python -c "from backend.services.mcp_governance import MCPGovernanceService; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/services/mcp_governance.py
git commit -m "feat(mcp): add propose_mcp_server_with_vote with live discovery + council vote"
```

---

### Task 3: Implement `vote_on_mcp_proposal` (service)

**Files:**
- Modify: `backend/services/mcp_governance.py` (add method to `MCPGovernanceService`)
- Test: `backend/tests/integration/test_agent_mcp_registration.py` (Task 5)

**Interfaces:**
- Consumes: `MCPTool.voting_id`, `AmendmentVoting.cast_vote` / `conclude`, `VoteType`, `AmendmentStatus`, `approve_mcp_server`, `_lazy_bridge`, `_get_tool_or_404`.
- Produces:
  - `def vote_on_mcp_proposal(self, tool_id, voter_agentium_id, vote) -> Dict[str, Any]`
  - Returns (vote counted, not final): `{voted:True, approved:False, tool_id, tally:{for,against,abstain}}`
  - Returns (finalised + passed): `{voted:True, approved:True, tool_id, registry_key:"mcp__<name>", result:{...}}`
  - Returns (finalised + rejected): `{voted:True, approved:False, tool_id, result:{...}, status:"rejected"}`

- [ ] **Step 1: Add the method**

Paste inside `MCPGovernanceService` (after `propose_mcp_server_with_vote`):

```python
    def vote_on_mcp_proposal(
        self, tool_id: str, voter_agentium_id: str, vote: str
    ) -> Dict[str, Any]:
        """
        Cast a Council vote on a pending MCP proposal. Finalises (conclude())
        once every eligible voter has cast; on PASS, approves + syncs live.
        """
        from backend.models.entities.voting import VoteType

        tool = self._get_tool_or_404(tool_id)
        if not tool.voting_id:
            raise ValueError("This MCP tool has no open Council vote.")

        voting = (
            self.db.query(AmendmentVoting).filter_by(id=tool.voting_id).first()
        )
        if not voting:
            raise ValueError("Linked AmendmentVoting not found.")
        if voting.status != AmendmentStatus.VOTING:
            raise ValueError(f"Voting is not open (status={voting.status.value}).")

        try:
            vt = VoteType(vote)
        except ValueError:
            raise ValueError("vote must be 'for', 'against', or 'abstain'.")

        voting.cast_vote(voter_agentium_id, vt)
        self.db.commit()

        total = voting.votes_for + voting.votes_against + voting.votes_abstain
        if total < len(voting.eligible_voters):
            return {
                "voted": True,
                "approved": False,
                "tool_id": tool_id,
                "tally": {
                    "for": voting.votes_for,
                    "against": voting.votes_against,
                    "abstain": voting.votes_abstain,
                },
            }

        result = voting.conclude()  # sets status PASSED / REJECTED
        self.db.commit()

        if voting.status == AmendmentStatus.PASSED:
            approved = self.approve_mcp_server(
                tool_id, approved_by=voter_agentium_id, vote_id=str(voting.id)
            )
            bridge = self._lazy_bridge()
            if bridge:
                bridge.sync_one(approved)
            return {
                "voted": True,
                "approved": True,
                "tool_id": tool_id,
                "registry_key": f"mcp__{tool.name}",
                "result": result,
            }

        return {
            "voted": True,
            "approved": False,
            "tool_id": tool_id,
            "result": result,
            "status": voting.status.value,
        }
```

- [ ] **Step 2: Sanity import check**

Run: `cd backend && python -c "from backend.services.mcp_governance import MCPGovernanceService; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/services/mcp_governance.py
git commit -m "feat(mcp): add vote_on_mcp_proposal with quorum finalisation + live sync"
```

---

### Task 4: Register the two agent tools in `tool_registry`

**Files:**
- Create: `backend/tools/mcp_agent_tools.py`
- Modify: `backend/core/tool_registry.py` (import + two `register_tool` calls in `_initialize_tools`)

**Interfaces:**
- Consumes: `MCPGovernanceService` (Tasks 2–3), `SessionLocal` from `backend.models.database`.
- Produces: `add_mcp_server(name, description, server_url, tier, agent_id, constitutional_article=None)` (async) and `vote_on_mcp_server(tool_id, vote, agent_id)` (sync) registered as `tool_registry` entries with `authorized_tiers=["0xxxx","1xxxx"]`. The orchestrator injects `agent_id` automatically via `ToolCreationService.execute_tool`.

- [ ] **Step 1: Create `backend/tools/mcp_agent_tools.py`**

```python
"""
Agent-callable MCP server registration tools.
Invoked by agents through ToolCreationService.execute_tool, which injects
`agent_id` into the function signature.
"""
from typing import Any, Dict, Optional

from backend.models.database import SessionLocal
from backend.services.mcp_governance import MCPGovernanceService


async def add_mcp_server(
    name: str,
    description: str,
    server_url: str,
    tier: str,
    agent_id: str,
    constitutional_article: Optional[str] = None,
) -> Dict[str, Any]:
    """Propose a new MCP server, auto-discover its capabilities, and open a Council vote."""
    db = SessionLocal()
    try:
        svc = MCPGovernanceService(db)
        return await svc.propose_mcp_server_with_vote(
            name=name,
            description=description,
            server_url=server_url,
            tier=tier,
            proposed_by=agent_id,
            constitutional_article=constitutional_article,
        )
    finally:
        db.close()


def vote_on_mcp_server(
    tool_id: str,
    vote: str,
    agent_id: str,
) -> Dict[str, Any]:
    """Cast a Council vote on a pending MCP server proposal."""
    db = SessionLocal()
    try:
        svc = MCPGovernanceService(db)
        return svc.vote_on_mcp_proposal(tool_id, agent_id, vote)
    finally:
        db.close()
```

- [ ] **Step 2: Register the tools**

In `backend/core/tool_registry.py`, add the import near the other tool imports (after line ~26):

```python
from backend.tools.mcp_agent_tools import add_mcp_server, vote_on_mcp_server
```

Then, inside `_initialize_tools(self)` (append at the end, before the method closes):

```python
        # ══════════════════════════════════════════════════════════════════════
        # AGENT-CALLABLE MCP SERVER REGISTRATION
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="add_mcp_server",
            description=(
                "Propose and register a new MCP server. Connects to the server, "
                "auto-discovers its available tools (capabilities), and opens a "
                "Council vote. Head agents auto-approve immediately; Council agents "
                "queue the proposal for a vote. Tier must be pre_approved, "
                "restricted, or forbidden."
            ),
            function=add_mcp_server,
            parameters={
                "name": {"type": "string", "description": "Unique MCP server name"},
                "description": {"type": "string", "description": "Human-readable description"},
                "server_url": {
                    "type": "string",
                    "description": "MCP server connection string / stdio command",
                },
                "tier": {
                    "type": "string",
                    "description": "Constitutional tier: pre_approved | restricted | forbidden",
                    "enum": ["pre_approved", "restricted", "forbidden"],
                },
                "constitutional_article": {
                    "type": "string",
                    "description": "Optional Constitution article governing this tool",
                    "optional": True,
                },
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )

        self.register_tool(
            name="vote_on_mcp_server",
            description=(
                "Cast a Council vote (for | against | abstain) on a pending MCP "
                "server proposal created via add_mcp_server. On quorum approval the "
                "server is registered live as mcp__<name>."
            ),
            function=vote_on_mcp_server,
            parameters={
                "tool_id": {"type": "string", "description": "MCPTool id from add_mcp_server"},
                "vote": {
                    "type": "string",
                    "description": "for | against | abstain",
                    "enum": ["for", "against", "abstain"],
                },
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
```

- [ ] **Step 3: Verify the tools are registered**

Run: `cd backend && python -c "from backend.core.tool_registry import tool_registry as r; print('add_mcp_server' in r.tools, 'vote_on_mcp_server' in r.tools); print(r.tools['add_mcp_server']['authorized_tiers'])"`
Expected: `True True` then `['0xxxx', '1xxxx']`

- [ ] **Step 4: Commit**

```bash
git add backend/tools/mcp_agent_tools.py backend/core/tool_registry.py
git commit -m "feat(mcp): register add_mcp_server and vote_on_mcp_server agent tools"
```

---

### Task 5: Integration tests (service + live registry sync)

**Files:**
- Create: `backend/tests/integration/test_agent_mcp_registration.py`

**Interfaces:**
- Consumes: `MCPGovernanceService`, `MCPClient`, `MCPConnectionError`, `tool_registry`, `init_bridge` (from `backend.services.mcp_tool_bridge`), `SessionLocal`, `Agent` model, fixtures `db_session`, `client` from `backend/tests/integration/conftest.py`.

- [ ] **Step 1: Write the test module**

```python
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
from backend.core.tool_registry import tool_registry
from backend.services.mcp_governance import (
    MCPGovernanceService,
    MCPConnectionError,
)
from backend.services.mcp_tool_bridge import init_bridge


@pytest.fixture(scope="module")
def bridge():
    """Initialise the live bridge so sync_one registers into tool_registry."""
    return init_bridge(tool_registry, SessionLocal)


def _make_council(db, n=2):
    members = []
    for i in range(n):
        a = Agent(
            agent_type=AgentType.COUNCIL_MEMBER,
            agentium_id=f"1{i:04d}",
            status=AgentStatus.ACTIVE,
            name=f"Council{i}",
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
    for v in voters:
        svc = MCPGovernanceService(db_session)
        res = svc.vote_on_mcp_proposal(tool_id, v, "for")
        if v == voters[-1]:  # final vote finalises
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
    remaining = (
        db_session.query(__import__("backend.models.entities.mcp_tool", fromlist=["MCPTool"]).MCPTool)
        .filter_by(name="deadserver").first()
    )
    assert remaining is None


def test_duplicate_server_url_rejected(bridge, db_session):
    _make_council(db_session)
    kw = dict(
        name="duptool", description="d", server_url="dup_cmd",
        tier="pre_approved", proposed_by="00001",
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
```

- [ ] **Step 2: Run the tests**

Run: `cd backend && pytest tests/integration/test_agent_mcp_registration.py -v -m integration`
Expected: all 5 tests PASS.

(If the suite needs the DB migrated, ensure `alembic upgrade head` ran in Task 1; the test fixtures auto-create tables from metadata.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_agent_mcp_registration.py
git commit -m "test(mcp): integration tests for agent-callable MCP registration"
```

---

## Self-Review Notes (already applied)

- **Spec coverage:** autonomy (Head fast-path / Council vote) ✓ Task 2–3; authorized tiers ✓ Task 4 (`["0xxxx","1xxxx"]`); live discovery ✓ Task 2; no row on failure ✓ Task 2 + test; revocation unchanged ✓ Task 5 test; `voting_id` linkage ✓ Task 1.
- **Placeholder scan:** no TBD/TODO; every code step shows full implementation.
- **Type consistency:** `propose_mcp_server_with_vote` → returns `tool_id`/`voting_id`; `vote_on_mcp_proposal(tool_id, voter, vote)` consumes them; registry keys use `f"mcp__{name}"` consistently; `MCPTool.voting_id` typed `Optional[str]`.
