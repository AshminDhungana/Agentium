"""
MCP Tools API Routes 
"""
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.core.auth import get_current_active_user
from backend.services.mcp_governance import MCPGovernanceService
from backend.api.schemas.mcp_schemas import (
    ProposeMCPServerRequest,
    ApproveMCPToolRequest,
    RevokeMCPToolRequest,
    ExecuteMCPToolRequest,
    MCPToolResponse,
    MCPToolListResponse,
    MCPExecutionResponse,
    MCPHealthResponse,
    MCPAuditResponse,
)

router = APIRouter(prefix="/api/v1/mcp-tools", tags=["MCP Tools"])


def _governance(db: Session) -> MCPGovernanceService:
    return MCPGovernanceService(db)


def _bridge():
    """Lazily import bridge singleton — safe before init_bridge() is called."""
    try:
        from backend.services.mcp_tool_bridge import mcp_bridge
        return mcp_bridge
    except ImportError:
        return None


# ── Existing routes (unchanged) ────────────────────────────────────────────────

@router.get("", response_model=MCPToolListResponse)
async def list_mcp_tools(
    status_filter: Optional[str] = Query(None, alias="status"),
    tier_filter: Optional[str] = Query(None, alias="tier"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    svc = _governance(db)
    if current_user.get("is_admin") or current_user.get("role") == "sovereign":
        tools = svc.list_all_tools(status=status_filter, tier=tier_filter)
    else:
        tools = svc.get_approved_tools()
    return MCPToolListResponse(
        tools=[MCPToolResponse(**t.to_dict()) for t in tools],
        total=len(tools),
        filters={"status": status_filter, "tier": tier_filter},
    )


@router.post("", response_model=MCPToolResponse, status_code=status.HTTP_201_CREATED)
async def propose_mcp_server(
    req: ProposeMCPServerRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    svc = _governance(db)
    try:
        tool = svc.propose_mcp_server(
            name=req.name,
            description=req.description,
            server_url=req.server_url,
            tier=req.tier,
            proposed_by=current_user.get("agentium_id", current_user.get("username", "unknown")),
            constitutional_article=req.constitutional_article,
            capabilities=req.capabilities or [],
        )
        return MCPToolResponse(**tool.to_dict())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── Phase 15.2: Stats routes (placed BEFORE /{tool_id} to avoid routing conflicts) ──

@router.get("/stats", tags=["MCP Tools", "Phase 15.2"])
async def get_all_mcp_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
) -> List[Dict[str, Any]]:
    """
    Return real-time invocation stats for all MCP tools from Redis.
    Response time target: <50 ms (pure Redis read, no DB query).

    Each item contains:
      tool_id, invocation_count, error_count, avg_latency_ms, error_rate, last_used_ts
    """
    try:
        from backend.services import mcp_stats_service
        stats = mcp_stats_service.get_all_stats()
        return stats
    except Exception as exc:
        # Non-fatal — return empty list rather than 500
        return []


@router.get("/stats/health", tags=["MCP Tools", "Phase 15.2"])
async def get_stats_health(
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Check connectivity and health of the Redis stats layer."""
    try:
        from backend.services import mcp_stats_service
        return mcp_stats_service.redis_health()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


@router.get("/revoked", tags=["MCP Tools", "Phase 15.2"])
async def get_revoked_tools(
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Return the list of tool IDs currently in the Redis revocation SET.
    Admin / Sovereign only.
    """
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(status_code=403, detail="Admin or Sovereign privileges required.")
    try:
        from backend.services import mcp_stats_service
        revoked = mcp_stats_service.get_revoked_ids()
        return {"revoked_tool_ids": revoked, "count": len(revoked)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Existing /{tool_id} routes (unchanged) ─────────────────────────────────────

@router.get("/{tool_id}", response_model=MCPToolResponse)
async def get_mcp_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    from backend.models.entities.mcp_tool import MCPTool
    tool = db.query(MCPTool).filter(MCPTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail=f"MCP tool '{tool_id}' not found.")
    return MCPToolResponse(**tool.to_dict())


@router.get("/{tool_id}/stats", tags=["MCP Tools", "Phase 15.2"])
async def get_tool_stats(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Return real-time invocation stats for a single MCP tool.
    Reads from Redis — no DB query.
    """
    # Verify tool exists first
    from backend.models.entities.mcp_tool import MCPTool
    tool = db.query(MCPTool).filter(MCPTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail=f"MCP tool '{tool_id}' not found.")

    try:
        from backend.services import mcp_stats_service
        stats = mcp_stats_service.get_tool_stats(tool_id)
        if stats is None:
            # Tool exists but has never been invoked
            return {
                "tool_id":          tool_id,
                "tool_name":        tool.name,
                "invocation_count": 0,
                "error_count":      0,
                "avg_latency_ms":   0.0,
                "error_rate":       0.0,
                "last_used_ts":     None,
            }
        return {**stats, "tool_name": tool.name}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{tool_id}/approve", response_model=MCPToolResponse)
async def approve_mcp_tool(
    tool_id: str,
    req: ApproveMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Approve a pending MCP tool.
    Immediately registers it into the live ToolRegistry so agents can use it.
    Phase 15.2: also removes tool from the Redis revocation SET if present.
    """
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(status_code=403, detail="Admin or Sovereign privileges required.")

    svc = _governance(db)
    try:
        tool = svc.approve_mcp_server(tool_id, approved_by=req.approved_by, vote_id=req.vote_id)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    bridge = _bridge()
    if bridge:
        bridge.sync_one(tool)

    return MCPToolResponse(**tool.to_dict())


@router.post("/{tool_id}/revoke", response_model=MCPToolResponse)
async def revoke_mcp_tool(
    tool_id: str,
    req: RevokeMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Emergency revocation — removes tool from live ToolRegistry in < 1s.
    Phase 15.2: also writes to Redis revocation SET for immediate enforcement.
    Agents attempting to use a revoked tool receive 404/block immediately.
    """
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(status_code=403, detail="Admin or Sovereign privileges required.")

    svc = _governance(db)
    try:
        tool = svc.revoke_mcp_tool(tool_id, revoked_by=req.revoked_by, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    bridge = _bridge()
    if bridge:
        bridge.deregister(tool)

    return MCPToolResponse(**tool.to_dict())


@router.post("/{tool_id}/execute", response_model=MCPExecutionResponse)
async def execute_mcp_tool(
    tool_id: str,
    req: ExecuteMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Admin/direct execution path. Agents should use /tools/execute instead."""
    svc = _governance(db)
    try:
        result = await svc.execute_mcp_tool(
            tool_id,
            agent_id=req.agent_id,
            agent_tier=req.agent_tier,
            params=req.params,
            has_head_approval_token=req.has_head_approval_token,
            tool_name=req.tool_name,
        )
        return MCPExecutionResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{tool_id}/health", response_model=MCPHealthResponse)
async def check_tool_health(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    svc = _governance(db)
    try:
        health = await svc.get_tool_health(tool_id)
        return MCPHealthResponse(**health)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{tool_id}/audit", response_model=MCPAuditResponse)
async def get_tool_audit_log(
    tool_id: str,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(status_code=403, detail="Admin or Sovereign privileges required.")

    svc = _governance(db)
    try:
        entries = svc.get_tool_audit_log(tool_id, limit=limit)
        from backend.models.entities.mcp_tool import MCPTool
        tool = db.query(MCPTool).filter(MCPTool.id == tool_id).first()
        return MCPAuditResponse(
            tool_id=tool_id,
            tool_name=tool.name if tool else "unknown",
            entries=entries,
            total_entries=len(tool.audit_log or []) if tool else 0,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))