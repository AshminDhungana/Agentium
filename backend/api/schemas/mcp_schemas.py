"""
Pydantic Schemas for MCP Tools API — Phase 6.7
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl


# ── Request schemas ────────────────────────────────────────────────────────────

class ProposeMCPServerRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=128, description="Human-readable tool name")
    description: str = Field(..., min_length=10, description="What this MCP server does")
    server_url: str = Field(..., description="MCP server URL or command path")
    tier: str = Field(..., description="pre_approved | restricted | forbidden")
    constitutional_article: Optional[str] = Field(None, description="Governing Constitution article")
    capabilities: Optional[List[str]] = Field(default=[], description="Known capability names")


class ApproveMCPToolRequest(BaseModel):
    approved_by: str = Field(..., description="agentium_id of the approving Council member")
    vote_id: Optional[str] = Field(None, description="Voting record ID")


class RevokeMCPToolRequest(BaseModel):
    revoked_by: str = Field(..., description="agentium_id performing emergency revocation")
    reason: str = Field(..., min_length=10, description="Justification for revocation")


class ExecuteMCPToolRequest(BaseModel):
    agent_id: str = Field(..., description="agentium_id of the executing agent")
    agent_tier: str = Field(..., description="Tier prefix e.g. 0xxxx, 1xxxx, 2xxxx, 3xxxx")
    params: Dict[str, Any] = Field(default={}, description="Tool parameters")
    tool_name: Optional[str] = Field(None, description="Specific tool name on the MCP server")
    has_head_approval_token: bool = Field(False, description="Whether Head approval is present")


# ── Response schemas ───────────────────────────────────────────────────────────

class MCPToolResponse(BaseModel):
    id: str
    name: str
    description: str
    server_url: str
    tier: str
    constitutional_article: Optional[str]
    status: str
    approved_by_council: bool
    approval_vote_id: Optional[str]
    approved_at: Optional[str]
    approved_by: Optional[str]
    revoked_at: Optional[str]
    revoked_by: Optional[str]
    revocation_reason: Optional[str]
    capabilities: List[str]
    health_status: str
    last_health_check_at: Optional[str]
    failure_count: int
    consecutive_failures: int
    usage_count: int
    last_used_at: Optional[str]
    proposed_by: Optional[str]
    proposed_at: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class MCPToolListResponse(BaseModel):
    tools: List[MCPToolResponse]
    total: int
    filters: Dict[str, Optional[str]]


class MCPExecutionResponse(BaseModel):
    success: bool
    tool: str
    result: Optional[Any] = None
    error: Optional[str] = None
    verdict: Optional[str] = None
    timestamp: Optional[str] = None
    mock: Optional[bool] = None


class MCPHealthResponse(BaseModel):
    tool_id: str
    tool_name: str
    healthy: bool
    latency_ms: float
    tool_count: Optional[int] = None
    error: Optional[str] = None


class MCPAuditResponse(BaseModel):
    tool_id: str
    tool_name: str
    entries: List[Dict[str, Any]]
    total_entries: int