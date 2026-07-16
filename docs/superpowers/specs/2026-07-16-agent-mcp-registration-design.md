# Design: Agent-Callable MCP Server Registration

**Date:** 2026-07-16
**Status:** Approved (design), pending implementation plan
**Domain:** project (Agentium MCP governance)

## Problem

Today, registering an MCP server is a **user/admin-only** operation:

- `POST /api/v1/mcp-tools` → `MCPGovernanceService.propose_mcp_server` creates a `pending` `MCPTool`.
- An admin/Head approves via `POST /api/v1/mcp-tools/{id}/approve` → `approve_mcp_server` → `MCPToolBridge.sync_one` registers it as `mcp__<name>` in the live `ToolRegistry`.

Agents have **no callable path** to register an MCP server (the "CATEGORY 5 — NOT AVAILABLE" gap). Built-in Python *tool creation* already has an agent path (`tool_creation_service`, council-voted), but MCP server registration does not. This design closes that gap with an agent-facing tool that proposes an MCP server, auto-discovers its capabilities, and triggers a Council vote that — on quorum — approves and syncs it live.

## Goals

1. Give authorized agents a tool to register MCP servers without a human in the loop for the *proposal*.
2. Preserve the constitutional governance model: proposals still require Council approval (or Head auto-ratification) before becoming live.
3. Reuse existing machinery (`MCPGovernanceService`, `MCPToolBridge`, `AmendmentVoting`, `MCPClient`) — no new privilege or approval subsystem.

## Non-Goals (YAGNI)

- No change to the user-facing `/api/v1/mcp-tools` routes (they stay as-is).
- No new MCP-server transport types; we only support what `MCPClient` already supports.
- No agent capability to *edit/delete* MCP servers beyond what governance already allows (revoke remains admin/Head).

## Decisions (from brainstorming)

| Decision | Choice |
|----------|--------|
| Autonomy level | Propose + auto-trigger Council vote (mirrors `tool_creation_service`) |
| Authorized tiers | Head (`0xxxx`) + Council (`1xxxx`) only |
| Capability discovery | Live connect + `MCPClient.list_tools()` at proposal time |
| Council voting transport | New agent-callable `vote_on_mcp_server` tool (full agent-driven flow) |

## Architecture

### New built-in agent tools (registered in `backend/core/tool_registry.py::_initialize_tools`)

**`add_mcp_server`** — `authorized_tiers=["0xxxx","1xxxx"]`
- Params: `name` (str), `description` (str), `server_url` (str), `tier` (`pre_approved` | `restricted` | `forbidden`), `constitutional_article` (str, optional).
- Function calls `MCPGovernanceService.propose_mcp_server_with_vote(...)`.

**`vote_on_mcp_server`** — `authorized_tiers=["0xxxx","1xxxx"]`
- Params: `tool_id` (str), `vote` (`for` | `against` | `abstain`).
- Function calls `MCPGovernanceService.vote_on_mcp_proposal(...)`.

### New service methods (`backend/services/mcp_governance.py`)

**`propose_mcp_server_with_vote(self, *, name, description, server_url, tier, proposed_by, constitutional_article=None) -> dict`**
1. Validate `tier` ∈ {pre_approved, restricted, forbidden}; reject otherwise.
2. Check `server_url` uniqueness (reuse existing query) → `ValueError` if duplicate.
3. **Live discovery:** `async with MCPClient(server_url) as client: caps = await client.list_tools()`.
   - On `MCPConnectionError` (or `mcp` package absent), return `{proposed: False, error: <reason>}` and create **no** DB row.
4. Create `MCPTool` row (`status="pending"`, `capabilities=caps`, `proposed_by`, `voting_id=None` initially).
5. Create `AmendmentVoting` (`proposed_changes=f"MCP Server: {name}"`, `proposed_by_agentium_id=proposed_by`, `status=PROPOSED`, `votes_required=len(council)`), link its id back onto `MCPTool.voting_id`.
6. **Head fast-path:** if `proposed_by` starts with `"0"`, auto-approve + `bridge.sync_one(tool)` and return `{proposed: True, status: "approved", registry_key: "mcp__<name>", capabilities: caps}`.
7. Otherwise return `{proposed: True, status: "pending_vote", voting_id: <id>, capabilities: caps}`.

**`vote_on_mcp_proposal(self, tool_id, voter_agentium_id, vote) -> dict`**
1. Load `MCPTool` by `tool_id`; resolve its `voting_id`.
2. Cast vote via `AmendmentVoting.cast_vote(vote, voter_agentium_id)`; commit.
3. If `voting.check_quorum()` → `finalize_voting()`.
4. If finalized `status == APPROVED`: call `approve_mcp_server(tool_id, approved_by=voter_agentium_id, vote_id=voting_id)`, then `bridge.sync_one(tool)`. Return `{voted: True, approved: True, registry_key: "mcp__<name>"}`.
5. Else return current tally `{voted: True, approved: False, for: x, against: y, abstain: z}`.

### Schema change

Add column `voting_id: Optional[str]` (String(64), nullable) to `MCPTool` (`backend/models/entities/mcp_tool.py`) + Alembic migration. This links a proposal to its `AmendmentVoting` (mirrors `ToolStaging.voting_id`).

### Bridge integration

Both new methods call the existing `mcp_bridge` singleton (lazy import, same pattern as `mcp_tools.py::_bridge()`) so approved servers appear in the live registry in < 1s with no restart.

## Data Flow

```
Head agent (0xxxx):
  add_mcp_server(params)
    → discover caps (live list_tools)
    → create pending MCPTool + AmendmentVoting
    → auto-approve + bridge.sync_one
    → returns live registry_key "mcp__<name>"

Council agent (1xxxx):
  add_mcp_server(params)
    → discover caps
    → create pending MCPTool + AmendmentVoting
    → returns voting_id (status pending_vote)
  ... Council members each call ...
  vote_on_mcp_server(tool_id, vote)
    → cast vote
    → on quorum: approve_mcp_server + bridge.sync_one
    → returns registry_key once approved
```

## Error Handling & Governance

- **Live connect fails** → no proposal created; tool returns error dict (non-fatal to the caller).
- **Duplicate `server_url`** → existing `ValueError` surfaced as tool error.
- **Invalid tier** → rejected before any connection.
- **Forbidden-tier proposal** → still creatable as `pending` but `approve_mcp_server` already blocks forbidden (no registry entry ever). This matches current behavior.
- **Audit trail:** append to `MCPTool.audit_log` on propose / approve / sync (reuse existing append pattern in `mcp_governance.py`).
- **Revocation:** unchanged — `revoke_mcp_tool` + `bridge.deregister` still removes the live `mcp__<name>` key.

## Testing

- **Unit** (`backend/tests/`):
  - `propose_mcp_server_with_vote` creates a `pending` `MCPTool` + `AmendmentVoting` and returns `voting_id`.
  - Head fast-path auto-approves and the tool appears in `tool_registry` under `mcp__<name>`.
  - Live `list_tools` failure rolls back (no `MCPTool` row).
  - Duplicate `server_url` raises/returns error.
- **Integration** (extend `backend/tests/integration/test_mcp_revocation.py` style):
  - After quorum vote, `mcp__<name>` present in registry; while `pending`, absent.
  - Revoke after approval removes the key within < 1s.

## Files Touched

| File | Change |
|------|--------|
| `backend/models/entities/mcp_tool.py` | Add `voting_id` column |
| `backend/alembic/versions/*.py` | New migration for `voting_id` |
| `backend/services/mcp_governance.py` | Add `propose_mcp_server_with_vote`, `vote_on_mcp_proposal` |
| `backend/core/tool_registry.py` | Register `add_mcp_server`, `vote_on_mcp_server` |
| `backend/tests/**` | Unit + integration tests |

## Acceptance Criteria

1. A Head or Council agent can call `add_mcp_server` and either auto-activate (Head) or queue a Council vote (Council).
2. Capabilities are auto-discovered from the live server at proposal time.
3. On quorum approval, `mcp__<name>` is registered in the live `ToolRegistry` without restart.
4. No proposal row is created if the server is unreachable.
5. All existing user/admin MCP routes and revocation behavior are unchanged.
