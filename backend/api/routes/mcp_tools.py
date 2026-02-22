"""
MCP Tools API Routes — Phase 6.7
Updated: bridge sync called after approve / revoke so agents see changes instantly.
"""
from typing import Optional

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
    """
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(status_code=403, detail="Admin or Sovereign privileges required.")

    svc = _governance(db)
    try:
        tool = svc.approve_mcp_server(tool_id, approved_by=req.approved_by, vote_id=req.vote_id)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Sync into live registry immediately — agents can now call this tool
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
    Agents attempting to use a revoked tool will receive 404 immediately.
    """
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise HTTPException(status_code=403, detail="Admin or Sovereign privileges required.")

    svc = _governance(db)
    try:
        tool = svc.revoke_mcp_tool(tool_id, revoked_by=req.revoked_by, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Deregister from live registry immediately
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