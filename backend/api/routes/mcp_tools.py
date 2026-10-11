"""
MCP Tools API Routes — Phase 6.7 / Phase 15.2 / Phase 17.3
==========================================================
Provides endpoints under both:
  - `/api/v1/mcp-tools` (legacy & frontend registry endpoints)
  - `/api/v1/mcp/tools` (17.3 standard REST specification)
"""
import logging
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.exceptions import (
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
    TooLargeError,
    RateLimitError,
    InternalServerError,
    ServiceUnavailableError,
)
from backend.models.database import get_db
from backend.core.auth import get_current_active_user
from backend.services.mcp_governance import MCPGovernanceService
from backend.api.schemas.mcp_schemas import (
    ProposeMCPServerRequest,
    ApproveMCPToolRequest,
    RevokeMCPToolRequest,
    ExecuteMCPToolRequest,
    InvokeMCPToolRequest,
    ConfigureMCPToolRequest,
    MCPToolResponse,
    MCPToolConfigResponse,
    MCPToolListResponse,
    MCPExecutionResponse,
    MCPHealthResponse,
    MCPAuditResponse,
)
from backend.api.schemas.examples import build_responses

logger = logging.getLogger(__name__)

# Legacy / standard dashboard router
router = APIRouter(prefix="/api/v1/mcp-tools", tags=["MCP Tools"])

# 17.3 REST router
mcp_router = APIRouter(prefix="/api/v1/mcp", tags=["MCP Tools"])


def _governance(db: Session) -> MCPGovernanceService:
    return MCPGovernanceService(db)


def _bridge():
    """Lazily import bridge singleton — safe before init_bridge() is called."""
    try:
        from backend.services.mcp_tool_bridge import mcp_bridge
        return mcp_bridge
    except ImportError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# REUSABLE CORE HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

def _list_mcp_tools_core(
    status_filter: Optional[str],
    tier_filter: Optional[str],
    agent_tier_filter: Optional[str],
    db: Session,
    current_user: dict,
) -> MCPToolListResponse:
    svc = _governance(db)
    if current_user.get("is_admin") or current_user.get("role") == "sovereign":
        tools = svc.list_all_tools(status=status_filter, tier=tier_filter)
        if agent_tier_filter and (agent_tier_filter.startswith("2") or agent_tier_filter.startswith("3")):
            tools = [t for t in tools if t.tier == "pre_approved"]
    else:
        agent_tier = agent_tier_filter or "3xxxx"
        tools = svc.get_approved_tools(agent_tier=agent_tier)
        if tier_filter:
            tools = [t for t in tools if t.tier == tier_filter]
        if status_filter and status_filter != "approved":
            tools = []

    return MCPToolListResponse(
        tools=[MCPToolResponse(**t.to_dict()) for t in tools],
        total=len(tools),
        filters={"status": status_filter, "tier": tier_filter},
    )


async def _invoke_mcp_tool_core(
    req: InvokeMCPToolRequest,
    db: Session,
    current_user: dict,
) -> MCPExecutionResponse:
    identifier = req.tool_id or req.tool_name or req.name
    if not identifier:
        raise BadRequestError(
            error="Either tool_id or tool_name must be provided.",
            code="MISSING_TOOL_IDENTIFIER",
        )

    svc = _governance(db)
    try:
        tool = svc.get_tool_by_identifier(identifier)
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="MCP_TOOL_NOT_FOUND")

    agent_id = req.agent_id or current_user.get("agentium_id") or current_user.get("username") or "user"
    if req.agent_tier:
        agent_tier = req.agent_tier
    elif current_user.get("is_admin") or current_user.get("role") == "sovereign":
        agent_tier = "0xxxx"
    else:
        agent_tier = "3xxxx"

    try:
        result = await svc.execute_mcp_tool(
            str(tool.id),
            agent_id=agent_id,
            agent_tier=agent_tier,
            params=req.params or {},
            has_head_approval_token=req.has_head_approval_token,
            tool_name=req.sub_tool,
            async_callback_url=req.async_callback_url,
        )
        return MCPExecutionResponse(**result)
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="MCP_TOOL_NOT_FOUND")
    except Exception as exc:
        raise InternalServerError(error=str(exc), code="STREXC")


def _get_tool_config_core(
    tool_id: str,
    db: Session,
    current_user: dict,
) -> MCPToolConfigResponse:
    svc = _governance(db)
    try:
        cfg = svc.get_tool_config(tool_id)
        return MCPToolConfigResponse(**cfg)
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="MCP_TOOL_NOT_FOUND")


def _configure_tool_core(
    tool_id: str,
    req: ConfigureMCPToolRequest,
    db: Session,
    current_user: dict,
) -> MCPToolResponse:
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise ForbiddenError(
            error="Admin or Sovereign privileges required to configure MCP tools.",
            code="FORBIDDEN",
        )
    svc = _governance(db)
    try:
        tool = svc.configure_mcp_tool(
            tool_id,
            server_url=req.server_url,
            auth_token=req.auth_token,
            headers=req.headers,
            env=req.env,
            tier=req.tier,
            constitutional_article=req.constitutional_article,
            config=req.config,
        )
        bridge = _bridge()
        if bridge and tool.status == "approved":
            bridge.sync_one(tool)
        return MCPToolResponse(**tool.to_dict())
    except ValueError as exc:
        raise BadRequestError(error=str(exc), code="INVALID_CONFIG")


# ══════════════════════════════════════════════════════════════════════════════
# 17.3 — MCP API ROUTES (Prefix: /api/v1/mcp)
# ══════════════════════════════════════════════════════════════════════════════

@mcp_router.get(
    "/tools",
    response_model=MCPToolListResponse,
    summary="List MCP Tools (17.3.1)",
    description="List available MCP tools. Filterable by status and tier.",
    responses=build_responses(None),
)
async def mcp_list_tools(
    status_filter: Optional[str] = Query(None, alias="status"),
    tier_filter: Optional[str] = Query(None, alias="tier"),
    agent_tier_filter: Optional[str] = Query(None, alias="agent_tier"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """17.3.1: GET /api/v1/mcp/tools lists available MCP tools."""
    return _list_mcp_tools_core(status_filter, tier_filter, agent_tier_filter, db, current_user)


@mcp_router.post(
    "/tools/invoke",
    response_model=MCPExecutionResponse,
    summary="Invoke MCP Tool (17.3.2)",
    description="Execute an MCP tool by tool_name or tool_id with governance and parameters.",
    responses=build_responses(None),
)
async def mcp_invoke_tool(
    req: InvokeMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """17.3.2: POST /api/v1/mcp/tools/invoke executes MCP tool."""
    return await _invoke_mcp_tool_core(req, db, current_user)


@mcp_router.post(
    "/tools",
    response_model=MCPToolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose / Register MCP Server (17.3.3)",
    description="Register or propose an MCP server with server URL, auth, and constitutional classification.",
    responses=build_responses(None),
)
async def mcp_propose_tool(
    req: ProposeMCPServerRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """17.3.3: MCP tool configuration (server URL, auth)."""
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
            auth_token=req.auth_token,
            headers=req.headers,
            env=req.env,
            config=req.config,
        )
        return MCPToolResponse(**tool.to_dict())
    except ValueError as exc:
        raise BadRequestError(error=str(exc), code="STREXC")


@mcp_router.get(
    "/tools/{tool_id}",
    response_model=MCPToolResponse,
    summary="Get MCP Tool",
    description="Retrieve details for a single MCP tool.",
    responses=build_responses(None),
)
async def mcp_get_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    svc = _governance(db)
    try:
        tool = svc.get_tool_by_identifier(tool_id)
        return MCPToolResponse(**tool.to_dict())
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="MCP_TOOL_NOT_FOUND")


@mcp_router.get(
    "/tools/{tool_id}/config",
    response_model=MCPToolConfigResponse,
    summary="Get MCP Tool Configuration (17.3.3)",
    description="Retrieve server URL and authentication status for an MCP tool.",
    responses=build_responses(None),
)
async def mcp_get_tool_config(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """17.3.3: MCP tool configuration (server URL, auth) query."""
    return _get_tool_config_core(tool_id, db, current_user)


@mcp_router.put(
    "/tools/{tool_id}/config",
    response_model=MCPToolResponse,
    summary="Update MCP Tool Configuration (17.3.3)",
    description="Update server URL, auth token, headers, or environment variables.",
    responses=build_responses(None),
)
async def mcp_update_tool_config_put(
    tool_id: str,
    req: ConfigureMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """17.3.3: Update MCP tool configuration (server URL, auth)."""
    return _configure_tool_core(tool_id, req, db, current_user)


@mcp_router.patch(
    "/tools/{tool_id}/config",
    response_model=MCPToolResponse,
    summary="Patch MCP Tool Configuration (17.3.3)",
    description="Patch server URL, auth token, headers, or environment variables.",
    responses=build_responses(None),
)
async def mcp_update_tool_config_patch(
    tool_id: str,
    req: ConfigureMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    return _configure_tool_core(tool_id, req, db, current_user)


@mcp_router.post(
    "/tools/{tool_id}/test-connection",
    response_model=MCPHealthResponse,
    summary="Test Connection to MCP Server",
    description="Verifies reachability and auth configuration against the target MCP server.",
    responses=build_responses(None),
)
async def mcp_test_tool_connection(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    svc = _governance(db)
    try:
        health = await svc.get_tool_health(tool_id)
        return MCPHealthResponse(**health)
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="MCP_TOOL_NOT_FOUND")


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY & EXTENDED ROUTES (Prefix: /api/v1/mcp-tools)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=MCPToolListResponse,
    summary="List Mcp Tools",
    description="Perform the list mcp tools operation.",
    responses=build_responses(None),
)
async def list_mcp_tools(
    status_filter: Optional[str] = Query(None, alias="status"),
    tier_filter: Optional[str] = Query(None, alias="tier"),
    agent_tier_filter: Optional[str] = Query(None, alias="agent_tier"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    return _list_mcp_tools_core(status_filter, tier_filter, agent_tier_filter, db, current_user)


@router.post(
    "",
    response_model=MCPToolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose Mcp Server",
    description="Perform the propose mcp server operation.",
    responses=build_responses(None),
)
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
            auth_token=req.auth_token,
            headers=req.headers,
            env=req.env,
            config=req.config,
        )
        return MCPToolResponse(**tool.to_dict())
    except ValueError as exc:
        raise BadRequestError(error=str(exc), code="STREXC")


@router.post(
    "/invoke",
    response_model=MCPExecutionResponse,
    summary="Invoke Mcp Tool via /mcp-tools",
    description="Unified invocation path.",
    responses=build_responses(None),
)
async def invoke_mcp_tool_legacy_route(
    req: InvokeMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    return await _invoke_mcp_tool_core(req, db, current_user)


# ── Phase 15.2: Stats routes (placed BEFORE /{tool_id} to avoid routing conflicts) ──

@router.get(
    "/stats",
    tags=["MCP Tools", "Phase 15.2"],
    summary="Get All Mcp Stats",
    description="Return real-time invocation stats for all MCP tools from Redis.",
    responses=build_responses(None),
)
async def get_all_mcp_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
) -> List[Dict[str, Any]]:
    try:
        from backend.services import mcp_stats_service
        return mcp_stats_service.get_all_stats()
    except Exception:
        return []


@router.get(
    "/stats/health",
    tags=["MCP Tools", "Phase 15.2"],
    summary="Get Stats Health",
    description="Check connectivity and health of the Redis stats layer.",
    responses=build_responses(None),
)
async def get_stats_health(
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    try:
        from backend.services import mcp_stats_service
        return mcp_stats_service.redis_health()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


@router.get(
    "/revoked",
    tags=["MCP Tools", "Phase 15.2"],
    summary="Get Revoked Tools",
    description="Return the list of tool IDs currently in the Redis revocation SET. Admin / Sovereign only.",
    responses=build_responses(None),
)
async def get_revoked_tools(
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise ForbiddenError(error="Admin or Sovereign privileges required.", code="ADMIN_OR_SOVEREIGN_PRIVILEGES_REQUIRED")
    try:
        from backend.services import mcp_stats_service
        revoked = mcp_stats_service.get_revoked_ids()
        return {"revoked_tool_ids": revoked, "count": len(revoked)}
    except Exception as exc:
        raise InternalServerError(error=str(exc), code="STREXC")


# ── Existing /{tool_id} routes ────────────────────────────────────────────────

@router.get(
    "/{tool_id}",
    response_model=MCPToolResponse,
    summary="Get Mcp Tool",
    description="Perform the get mcp tool operation.",
    responses=build_responses(None),
)
async def get_mcp_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    svc = _governance(db)
    try:
        tool = svc.get_tool_by_identifier(tool_id)
        return MCPToolResponse(**tool.to_dict())
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="MCP_TOOL_NOT_FOUND")


@router.get(
    "/{tool_id}/config",
    response_model=MCPToolConfigResponse,
    summary="Get Tool Configuration",
    description="Return configuration details for the tool.",
    responses=build_responses(None),
)
async def get_tool_config_legacy(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    return _get_tool_config_core(tool_id, db, current_user)


@router.put(
    "/{tool_id}/config",
    response_model=MCPToolResponse,
    summary="Update Tool Configuration",
    description="Update server URL and auth configuration.",
    responses=build_responses(None),
)
async def update_tool_config_legacy(
    tool_id: str,
    req: ConfigureMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    return _configure_tool_core(tool_id, req, db, current_user)


@router.get(
    "/{tool_id}/stats",
    tags=["MCP Tools", "Phase 15.2"],
    summary="Get Tool Stats",
    description="Return real-time invocation stats for a single MCP tool.",
    responses=build_responses(None),
)
async def get_tool_stats(
    tool_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    svc = _governance(db)
    try:
        tool = svc.get_tool_by_identifier(tool_id)
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="MCP_TOOL_NOT_FOUND")

    try:
        from backend.services import mcp_stats_service
        stats = mcp_stats_service.get_tool_stats(str(tool.id))
        if stats is None:
            return {
                "tool_id":          str(tool.id),
                "tool_name":        tool.name,
                "invocation_count": 0,
                "error_count":      0,
                "avg_latency_ms":   0.0,
                "error_rate":       0.0,
                "last_used_ts":     None,
            }
        return {**stats, "tool_name": tool.name}
    except Exception as exc:
        raise InternalServerError(error=str(exc), code="STREXC")


@router.post(
    "/{tool_id}/approve",
    response_model=MCPToolResponse,
    summary="Approve Mcp Tool",
    description="Approve a pending MCP tool. Immediately registers it into the live ToolRegistry.",
    responses=build_responses(None),
)
async def approve_mcp_tool(
    tool_id: str,
    req: ApproveMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise ForbiddenError(error="Admin or Sovereign privileges required.", code="ADMIN_OR_SOVEREIGN_PRIVILEGES_REQUIRED")

    svc = _governance(db)
    try:
        tool = svc.approve_mcp_server(tool_id, approved_by=req.approved_by, vote_id=req.vote_id)
    except (ValueError, PermissionError) as exc:
        raise BadRequestError(error=str(exc), code="STREXC")

    bridge = _bridge()
    if bridge:
        bridge.sync_one(tool)

    return MCPToolResponse(**tool.to_dict())


@router.post(
    "/{tool_id}/revoke",
    response_model=MCPToolResponse,
    summary="Revoke Mcp Tool",
    description="Emergency revocation — removes tool from live ToolRegistry and adds to Redis revocation SET.",
    responses=build_responses(None),
)
async def revoke_mcp_tool(
    tool_id: str,
    req: RevokeMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise ForbiddenError(error="Admin or Sovereign privileges required.", code="ADMIN_OR_SOVEREIGN_PRIVILEGES_REQUIRED")

    svc = _governance(db)
    try:
        tool = svc.revoke_mcp_tool(tool_id, revoked_by=req.revoked_by, reason=req.reason)
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="STREXC")

    bridge = _bridge()
    if bridge:
        bridge.deregister(tool)

    # Broadcast revocation to WebSocket clients
    try:
        from backend.api.routes.websocket import manager
        await manager.emit_mcp_tool_revoked(
            tool_id=str(tool.id),
            tool_name=tool.name,
            reason=req.reason,
            revoked_by=req.revoked_by,
        )
    except Exception as exc:
        logger.warning(f"[MCPTools] WebSocket revocation broadcast failed: {exc}")

    return MCPToolResponse(**tool.to_dict())


@router.post(
    "/{tool_id}/execute",
    response_model=MCPExecutionResponse,
    summary="Execute Mcp Tool",
    description="Direct execution path by tool ID.",
    responses=build_responses(None),
)
async def execute_mcp_tool(
    tool_id: str,
    req: ExecuteMCPToolRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
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
        raise NotFoundError(error=str(exc), code="STREXC")
    except Exception as exc:
        raise InternalServerError(error=str(exc), code="STREXC")


@router.get(
    "/{tool_id}/health",
    response_model=MCPHealthResponse,
    summary="Check Tool Health",
    description="Perform the check tool health operation.",
    responses=build_responses(None),
)
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
        raise NotFoundError(error=str(exc), code="STREXC")


@router.get(
    "/{tool_id}/audit",
    response_model=MCPAuditResponse,
    summary="Get Tool Audit Log",
    description="Perform the get tool audit log operation.",
    responses=build_responses(None),
)
async def get_tool_audit_log(
    tool_id: str,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    if not current_user.get("is_admin") and current_user.get("role") != "sovereign":
        raise ForbiddenError(error="Admin or Sovereign privileges required.", code="ADMIN_OR_SOVEREIGN_PRIVILEGES_REQUIRED")

    svc = _governance(db)
    try:
        entries = svc.get_tool_audit_log(tool_id, limit=limit)
        tool = svc.get_tool_by_identifier(tool_id)
        return MCPAuditResponse(
            tool_id=str(tool.id),
            tool_name=tool.name if tool else "unknown",
            entries=entries,
            total_entries=len(tool.audit_log or []) if tool else 0,
        )
    except ValueError as exc:
        raise NotFoundError(error=str(exc), code="STREXC")