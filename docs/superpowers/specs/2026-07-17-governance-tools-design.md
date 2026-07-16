# Governance Tools for Agent Chat Control — Design

**Date:** 2026-07-17
**Status:** Approved (pending spec review)

## Problem

The Head of Council (agent `00001`) — and other authority-bearing agents —
cannot perform basic governance operations when instructed through chat. When
asked to spawn agents, create/dispatch tasks, or run a Council vote, the Head
correctly reports that it *lacks the tools*.

Root cause: the Head's chat tool-calling loop (`generate_with_tools`) only
exposes generic tools (`web_search`, `http_api`, `code_analyze`, etc.). All the
governance operations already exist as **services**
(`ReincarnationService`, `AmendmentService`, task dispatch via the orchestrator),
but **none are registered as LLM-callable tools** in `tool_registry.py`. The only
chat path to them is the brittle keyword parser `GovernanceCommandService`, which
matches rigid phrases like "spawn a task agent" and does not cover liquidation,
dispatch, completion, or voting.

The reported web/networking gap is already covered: `http_api`, `http_api_batch`,
and `web_search` are registered for all tiers.

## Goal

Register the missing governance operations as first-class, capability-checked
LLM tools so authority-bearing agents can perform them from chat, and align every
tier's tool access with a least-privilege model (while keeping the architecture's
execution-safety boundary intact).

## Non-Goals

- No new governance business logic. Tools are thin wrappers over existing services.
- No changes to `ReincarnationService`, `AmendmentService`, task state machine,
  orchestrator, or chat flow internals.
- The `GovernanceCommandService` keyword parser stays as a fast-path fallback.
- No broad refactoring beyond the tier-access matrix below.

## Approach

**Approach A — Governance tools module + registry wiring.**

Create one new module `backend/tools/governance_tool.py` containing thin wrapper
functions, one per governance operation. Register each in
`tool_registry.py::_initialize_tools()` with the correct `authorized_tiers`.
Add the new tool names to the `db`/`agent_id` injection list in
`tool_creation_service.py::execute_tool` (the same injection already used for
`deep_think`).

Because the Head already runs `generate_with_tools`, newly registered tier-0
tools appear to it automatically — no chat-flow changes required.

### Why not the alternatives

- **Extend `GovernanceCommandService`** — coupled to regex parsing, doesn't cover
  voting/liquidation/dispatch; would bolt on a lot.
- **MCP-style dynamic governance tools** — heaviest; overkill for internal
  built-in ops, adds DB round-trips.

## Component Design

### New module: `backend/tools/governance_tool.py`

Each wrapper function:

1. Receives injected `agent_id` and `db`.
2. Resolves the calling `Agent`, checks the required `Capability` via
   `CapabilityRegistry.can_agent(...)`. On denial returns
   `{"success": false, "data": null, "error": "not authorized: <detail>"}`.
3. Delegates to the canonical service. No new business logic.
4. Returns a uniform result dict: `{"success": bool, "data": {...}, "error": str|null}`.

Defence-in-depth: the underlying services also enforce authority, and the
registry's `authorized_tiers` controls which tiers even see the tool.

### Tool contracts

**Lifecycle**

- `spawn_agent(agent_type, name, description, capabilities?)`
  - `agent_type` ∈ `council | lead | task`.
  - Capability gate: `council` → `SPAWN_COUNCIL` (Head only), `lead` → `SPAWN_LEAD`,
    `task` → `SPAWN_TASK_AGENT`.
  - Delegates: `council` → `spawn_council_member` wrapper (calls entity
    `Agent.spawn_child` if no dedicated service method exists);
    `lead` → `ReincarnationService.spawn_lead_agent`;
    `task` → `ReincarnationService.spawn_task_agent`.
  - Returns: new agent id, type, name.

- `liquidate_agent(target_agentium_id, reason)`
  - Capability gate: `LIQUIDATE_ANY` (Head) or `LIQUIDATE_TASK_AGENT` (Lead, own Task).
  - Delegates: `ReincarnationService.liquidate_agent`. Protects `00001`.
  - Returns: liquidation status.

**Tasks**

- `create_task(title, description, priority?)`
  - Capability gate: `DELEGATE_WORK`. Creates a `Task`. Returns task id/status.

- `dispatch_task(task_id, target_agentium_id?)`
  - Capability gate: `DELEGATE_WORK`.
  - Delegates: orchestrator `delegate_to_task` (auto-picks an available Task if no
    target). **This triggers the ephemeral critic-review lifecycle** (accepted).
  - Returns: dispatch status.

- `complete_task(task_id, result_summary)`
  - Capability gate: `EXECUTE_TASK`.
  - Delegates: task state machine → completed. Returns final status.

**Voting**

- `propose_amendment(title, description, proposed_text)`
  - Capability gate: `PROPOSE_AMENDMENT`. Delegates: `AmendmentService` create.
    Returns amendment id.

- `open_vote(amendment_id)`
  - Capability gate: `AMEND_CONSTITUTION` (Head) or `PROPOSE_AMENDMENT`.
    Delegates: `AmendmentService.start_voting`.

- `cast_vote(amendment_id, vote, rationale?)`
  - `vote` ∈ `for | against | abstain`. Capability gate: `VOTE_ON_AMENDMENT`.
    Delegates: `AmendmentService.cast_vote`. Returns running tally.

- `conclude_vote(amendment_id)`
  - Capability gate: `AMEND_CONSTITUTION`. Delegates: `AmendmentService.conclude_voting`
    (ratify/rollback; 60% quorum enforced by the service). Returns outcome.

### New capability

Add `SPAWN_COUNCIL = "spawn_council"` to the `Capability` enum and include it in
`TIER_CAPABILITIES["0"]` (Head only). No other capabilities are new — the enum
already covers spawn/liquidate/task/voting operations.

## Tier Access Matrix

### New governance tools — `authorized_tiers`

| Tool | 0 | 1 | 2 | 3 | Capability gate |
|---|---|---|---|---|---|
| `spawn_agent` | ✅ | ✅ | ✅ | ❌ | council→`SPAWN_COUNCIL`(Head), lead→`SPAWN_LEAD`, task→`SPAWN_TASK_AGENT` |
| `liquidate_agent` | ✅ | ❌ | ✅ | ❌ | `LIQUIDATE_ANY` / `LIQUIDATE_TASK_AGENT` |
| `create_task` | ✅ | ✅ | ✅ | ❌ | `DELEGATE_WORK` |
| `dispatch_task` | ✅ | ✅ | ✅ | ❌ | `DELEGATE_WORK` |
| `complete_task` | ✅ | ✅ | ✅ | ✅ | `EXECUTE_TASK` |
| `propose_amendment` | ✅ | ✅ | ❌ | ❌ | `PROPOSE_AMENDMENT` |
| `open_vote` | ✅ | ✅ | ❌ | ❌ | `AMEND_CONSTITUTION`/`PROPOSE_AMENDMENT` |
| `cast_vote` | ✅ | ✅ | ❌ | ❌ | `VOTE_ON_AMENDMENT` |
| `conclude_vote` | ✅ | ❌ | ❌ | ❌ | `AMEND_CONSTITUTION` |

Tier gates control *visibility*; the capability check inside each tool is the real
authority. (E.g. `spawn_agent` is visible to Council but the cap check restricts
them to `lead` spawning.)

### Existing tools — least-privilege changes

| Tool | Current `authorized_tiers` | Proposed |
|---|---|---|
| `read_file` | 0,1,2 | 0,1,2,3,4,5,6 |
| `write_file` | 0 | 0,1,2,3,4,5,6 |
| `text_editor` | 0,1,2,3 | 0,1,2,3,4,5,6 |
| `execute_command` | 0,1 | 0,1,2 |

Rationale: Task agents (prefixes 3–6) do the actual code writing/editing/reading
and need full file access. `execute_command` stays restricted to 0–2 —
**Task tiers use the sandboxed Docker executor, not raw host shell**, preserving
the architecture's Execution Safety boundary.

### Unchanged (already correct)

- `http_api`, `http_api_batch`, `web_search`, `code_analyze`, `data_transform`,
  `embedding` — all tiers 0–6.
- `git` — 0,1,2 (excludes Task by design).
- `browser_*`, `nodriver_*` — 0,1.
- `host_*` — 0,1,2 (and 0,1 for `host_smart_execute`).
- `desktop_*` — 0,1,2 (0,1 for `desktop_delete_file`, `desktop_browser_execute_js`).
- `deep_think`, `preference_*` — as-is.
- MCP tools (`add_mcp_server`, `vote_on_mcp_server`) — 0,1.

## Data Flow

1. User sends a chat instruction to the Head (`00001`).
2. `chat_service.process_message` → `LLMClient.generate_with_tools` (tier `0xxxx`).
3. Registry exports tier-0 tools (now including governance tools) to the model.
4. Model emits a tool call (e.g. `spawn_agent`).
5. `ModelService.generate_with_agent_tools` → `ToolCreationService.execute_tool`
   injects `agent_id` + `db`, runs the wrapper.
6. Wrapper checks capability → delegates to the service → returns result dict.
7. Result is fed back into the agentic loop; the Head relays outcome to the user.

## Error Handling

- **Unauthorized:** wrapper returns `{"success": false, "error": "not authorized: ..."}`.
  The LLM relays a clear refusal; no exception surfaces to the user.
- **Invalid args** (bad `agent_type`, unknown `task_id`/`amendment_id`): wrapper
  returns `success: false` with a descriptive error.
- **Service exceptions** (e.g. quorum not met, protected agent `00001`): caught and
  returned as structured errors rather than raised.
- **Defence-in-depth:** underlying services still raise/enforce; the tool wrapper is
  the first line, not the only one.

## Testing

- **Unit:** one test per wrapper — authorized happy path (mock service call) and
  unauthorized refusal (capability denied). Verify uniform result shape.
- **Registry:** assert each governance tool is registered with the exact
  `authorized_tiers` from the matrix; assert the four existing-tool tier changes.
- **Injection:** assert the new tool names are in the `execute_tool` injection list
  (receive `db`/`agent_id`).
- **Integration:** chat instruction to the Head that spawns a Task agent end-to-end
  (mirrors existing `tests/integration/test_agent_mcp_registration.py` pattern);
  a Council `cast_vote` flow; a `dispatch_task` that exercises the critic-review
  lifecycle.
- Respect existing coverage thresholds (`pytest --cov-fail-under`).

## Files Touched

- **New:** `backend/tools/governance_tool.py`
- **Edit:** `backend/core/tool_registry.py` (register new tools; adjust four
  existing tools' `authorized_tiers`)
- **Edit:** `backend/services/tool_creation_service.py` (add governance tool names
  to `db`/`agent_id` injection list)
- **Edit:** `backend/services/capability_registry.py` (add `SPAWN_COUNCIL` to enum
  and `TIER_CAPABILITIES["0"]`)
- **New (tests):** unit tests for `governance_tool`, registry-matrix assertions,
  and integration coverage.
