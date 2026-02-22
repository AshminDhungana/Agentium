"""
Tools API Routes — updated for Phase 6.7 (MCP tool support)

Changes vs original:
- execute_tool is now async so it can await MCP tool coroutines natively
- Agent identity (agent_id + agent_tier) is extracted from the JWT and forwarded
  to MCP tool invocations so the governance layer can enforce tier checks and
  write the constitutional audit log
- MCP tools (identified by the "is_mcp" flag in their registry entry) receive
  agent context as kwargs; built-in sync tools receive only the user-supplied params
- list_tools response now includes MCP metadata when present
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.tool_registry import tool_registry
from backend.core.auth import get_current_agent_tier, get_current_agent_id

router = APIRouter(prefix="/tools", tags=["Tools"])


# ── Request model ──────────────────────────────────────────────────────────────

class ExecuteToolRequest(BaseModel):
    tool_name: str
    params: Dict[str, Any] = {}
    # MCP-specific optional fields — ignored for non-MCP tools
    has_head_approval_token: bool = False
    tool_name_override: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_tools(
    agent_tier: str = Depends(get_current_agent_tier),
):
    """
    List tools available to the authenticated agent.

    MCP tools include additional fields:
      - is_mcp: true
      - mcp_tier: "pre_approved" | "restricted"
      - mcp_server_url: the registered server URL
      - mcp_original_name: human-readable tool name without the mcp__ prefix
    """
    return {
        "agent_tier": agent_tier,
        "tools": tool_registry.list_tools(agent_tier),
    }


@router.post("/execute")
async def execute_tool(
    request: ExecuteToolRequest,
    agent_tier: str = Depends(get_current_agent_tier),
    agent_id: str = Depends(get_current_agent_id),
):
    """
    Execute a tool with parameters.

    For MCP tools the route transparently forwards agent identity to the
    MCPGovernanceService so tier enforcement and audit logging work correctly.

    For built-in tools (browser, file, shell) behaviour is identical to before.
    """
    tool = tool_registry.get_tool(request.tool_name)

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found")

    if agent_tier not in tool["authorized_tiers"]:
        raise HTTPException(
            status_code=403,
            detail=f"Agent tier '{agent_tier}' is not authorised to use '{request.tool_name}'",
        )

    # ── MCP tool path ──────────────────────────────────────────────────────────
    if tool.get("is_mcp"):
        # Pass full agent context so MCPGovernanceService can:
        #   1. Enforce constitutional tier checks
        #   2. Write audit log entry with agent_id + input_hash
        result = await tool_registry.execute_tool_async(
            request.tool_name,
            agent_id=agent_id,
            agent_tier=agent_tier,
            params=request.params,
            has_head_approval_token=request.has_head_approval_token,
            tool_name_override=request.tool_name_override,
        )

    # ── Built-in sync tool path ────────────────────────────────────────────────
    else:
        result = await tool_registry.execute_tool_async(
            request.tool_name,
            **request.params,
        )

    return result


@router.get("/mcp")
async def list_mcp_tools(
    agent_tier: str = Depends(get_current_agent_tier),
):
    """
    Convenience endpoint — returns only MCP tools visible to this agent.
    Useful for agents that want to discover available MCP integrations
    without parsing the full tool list.
    """
    all_tools = tool_registry.list_tools(agent_tier)
    mcp_only = {
        name: descriptor
        for name, descriptor in all_tools.items()
        if descriptor.get("is_mcp")
    }
    return {
        "agent_tier": agent_tier,
        "mcp_tools": mcp_only,
        "count": len(mcp_only),
    }