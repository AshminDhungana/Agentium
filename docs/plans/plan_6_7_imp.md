# Implementation Plan: Phase 6.7 MCP Server Integration

## Context

**Purpose:** Extend the existing Tool Creation Service (Phase 6.1) to support MCP servers as a tool source, with constitutional tier-based approval and audit logging on every invocation.

**Philosophy:** "Rowboat connects MCP tools directly. Agentium connects them through the Constitution."

**Why this matters:** MCP tools are powerful but risky. Without governance, agents could invoke dangerous tools. This implementation brings MCP tools into Agentium's democratic approval model.

---

## Overview

| Metric | Value |
|--------|-------|
| **Phase** | 6.7 |
| **Complexity** | Medium |
| **Key Dependencies** | Tool Creation Service (6.1), Constitutional Guard (2.3), Tool Registry |
| **New Files** | ~5 core files |
| **Database Changes** | New MCPTool entity |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              MCP TOOL REGISTRY                       │
├─────────────────────────────────────────────────────┤
│  Tier 1: Pre-Approved (Council vote to USE)        │
│  ├─ Safe read-only APIs (weather, public data)      │
│  └─ Non-destructive queries                         │
│                                                     │
│  Tier 2: Restricted (Head approval per use)        │
│  ├─ Email sending                                  │
│  ├─ File system writes                             │
│  └─ External webhooks                              │
│                                                     │
│  Tier 3: Forbidden (Constitutionally banned)       │
│  ├─ Financial transactions                         │
│  ├─ Credential/password access                    │
│  └─ Raw shell execution                            │
└─────────────────────────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Create MCP Tool Database Model

**File:** `backend/models/entities/mcp_tool.py` (new)

```python
class MCPTool(BaseEntity):
    name: str
    description: str
    server_url: str
    tier: str  # "pre_approved", "restricted", "forbidden"
    capabilities: List[str]
    constitutional_article: Optional[str]
    approved_by_council: bool = False
    approval_vote_id: Optional[str]
    usage_count: int = 0
    last_used_at: Optional[datetime]
    audit_log: List[Dict]  # Every invocation logged
    status: str  # "pending", "approved", "revoked", "disabled"
    health_status: str  # "healthy", "degraded", "down"
    failure_count: int = 0
```

**Migration:** `backend/alembic/versions/xxx_add_mcp_tools.py`

---

### Step 2: Create MCP Governance Service

**File:** `backend/services/mcp_governance.py` (new)

| Method | Description |
|--------|-------------|
| `propose_mcp_server(url, description)` | Council member proposes new MCP server |
| `approve_mcp_server(tool_id)` | Handle Council vote approval |
| `revoke_mcp_tool(tool_id, reason)` | Emergency revocation without vote |
| `get_approved_tools(agent_tier)` | Returns tools accessible to agent's tier |
| `execute_mcp_tool(tool_id, agent_id, params)` | Execute tool with audit logging |
| `check_tier_access(tool_tier, agent_tier)` | Verify agent can use tool |
| `audit_tool_invocation(tool_id, agent_id, action)` | Constitutional Guard hook |
| `get_tool_health(tool_id)` | Check MCP server health |
| `auto_disable_on_failures(tool_id)` | Disable after repeated failures |

---

### Step 3: Integrate with Constitutional Guard

**Modify:** `backend/core/constitutional_guard.py`

Add MCP-specific checks:

```python
def check_mcp_tool_access(agent_id: str, tool_tier: str) -> Verdict:
    # Tier 3: Always block
    if tool_tier == "forbidden":
        return Verdict.BLOCK

    # Tier 2: Require Head approval token
    if tool_tier == "restricted":
        has_head_approval = check_head_token(agent_id)
        if not has_head_approval:
            return Verdict.VOTE_REQUIRED

    # Tier 1: Allow if approved by Council
    return Verdict.ALLOW
```

---

### Step 4: Create MCP Client Wrapper

**File:** `backend/services/mcp_client.py` (new)

| Method | Description |
|--------|-------------|
| `connect(server_url)` | Establish connection to MCP server |
| `list_tools()` | Discover available tools from server |
| `call_tool(name, params)` | Invoke tool on MCP server |
| `disconnect()` | Close connection |
| `health_check()` | Verify server is reachable |

**Dependencies:** `mcp>=1.0.0` (add to requirements.txt)

---

### Step 5: Add API Routes

**File:** `backend/api/routes/mcp_tools.py` (new)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/mcp-tools` | GET | List all MCP tools |
| `/api/v1/mcp-tools` | POST | Propose new MCP server |
| `/api/v1/mcp-tools/{id}` | GET | Get tool details |
| `/api/v1/mcp-tools/{id}/approve` | POST | Approve tool (Council) |
| `/api/v1/mcp-tools/{id}/revoke` | POST | Revoke tool (emergency) |
| `/api/v1/mcp-tools/{id}/execute` | POST | Execute tool |
| `/api/v1/mcp-tools/{id}/health` | GET | Check tool health |
| `/api/v1/mcp-tools/{id}/audit` | GET | Get audit log |

**Register router in:** `backend/main.py`

---

### Step 6: Create Frontend Components

**File:** `frontend/src/components/mcp/ToolRegistry.tsx` (new)

Features:
- Browse available MCP tools
- Filter by tier, approval status, usage stats
- "Propose new MCP server" modal → triggers Council vote
- Per-tool invocation audit log viewer

**File:** `frontend/src/pages/MCPToolsPage.tsx` (new)

---

## Files to Create/Modify

### New Files

| File | Description |
|------|-------------|
| `backend/models/entities/mcp_tool.py` | MCPTool database model |
| `backend/services/mcp_governance.py` | Core MCP governance service |
| `backend/services/mcp_client.py` | MCP server client wrapper |
| `backend/api/routes/mcp_tools.py` | REST API endpoints |
| `backend/api/schemas/mcp_tools.py` | Pydantic schemas |
| `frontend/src/components/mcp/ToolRegistry.tsx` | React component |
| `frontend/src/pages/MCPToolsPage.tsx` | Frontend page |

### Modified Files

| File | Changes |
|------|---------|
| `backend/main.py` | Register MCP router |
| `backend/core/constitutional_guard.py` | Add MCP tier checks |
| `backend/models/entities/__init__.py` | Register MCPTool |
| `backend/requirements.txt` | Add `mcp>=1.0.0` |
| `frontend/src/App.tsx` | Add MCP tools route |

---

## Integration with Existing Services

1. **Tool Creation Service (6.1):** MCP tools enter same approval pipeline as agent-generated tools
2. **Constitutional Guard (2.3):** Audits every invocation, blocks Tier 3 tools
3. **Tool Registry:** MCP tools registered after Council approval
4. **Voting Service:** Council votes on new MCP server proposals
5. **Message Bus:** Notify agents of tool status changes

---

## Acceptance Criteria

- [ ] Every MCP tool invocation logged in audit trail with agent_id, timestamp, input hash
- [ ] Tier 3 tools blocked at Constitutional Guard before reaching MCP client
- [ ] Tier 2 tools require Head approval token in request
- [ ] Council vote required to add any new MCP server
- [ ] Tool registry shows real-time usage stats per tool
- [ ] Revoked tools immediately unavailable (cache invalidation <1s)
- [ ] MCP server health monitored (auto-disable on repeated failures)

---

## Testing Strategy

1. **Unit Tests:** `backend/tests/test_mcp_governance.py`
   - Tier access validation
   - Approval/revocation workflow
   - Audit logging

2. **Integration Tests:**
   - MCP server discovery
   - Tool execution flow
   - Health check behavior

3. **Frontend Tests:**
   - Tool listing and filtering
   - Approval workflow UI

---

## Verification

Run these commands after implementation:

```bash
# Backend tests
pytest backend/tests/test_mcp_governance.py -v

# Type checking
mypy backend/services/mcp_governance.py --strict

# Linting
ruff check backend/services/mcp_governance.py

# Frontend build
cd frontend && npm run build
```
